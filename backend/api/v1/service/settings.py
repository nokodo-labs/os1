"""settings service."""

from collections.abc import Mapping

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.database.post_commit import run_post_commit_actions_safely
from api.models.event import Event, EventScope
from api.models.event_types import EventType
from api.models.setting import SettingsDocument
from api.permissions import ResourceType
from api.redis import publish_invalidation
from api.runtime import SETTINGS_INVALIDATION_SIGNAL, apply_settings_change
from api.settings import Settings, check_writable, settings
from api.v1.schemas.settings import SettingsPatch, SettingsVersions
from api.v1.service.authorization import (
	changed_default_access_resource_types,
	invalidate_accessible_users_for_resource_types,
)
from api.v1.service.events import (
	persist_and_fanout_event,
)
from api.v1.service.threads import purge_thread_content_vectors
from nokodo_ai.utils.dicts import deep_merge
from nokodo_ai.utils.typeid import TypeID


class VersionConflictError(Exception):
	def __init__(self, section: str, expected: int, actual: int) -> None:
		self.section = section
		self.expected = expected
		self.actual = actual


async def _get_doc(db: AsyncSession, section: str) -> SettingsDocument | None:
	stmt = select(SettingsDocument).where(SettingsDocument.namespace == section)
	return (await db.execute(stmt)).scalar_one_or_none()


async def get_versions(db: AsyncSession) -> SettingsVersions:
	"""return per-section optimistic lock versions."""
	values: dict[str, int] = {}
	for section in Settings.model_fields:
		doc = await _get_doc(db, section)
		values[section] = doc.version if doc else 0
	return SettingsVersions.model_validate(values)


async def update(
	db: AsyncSession,
	patch: SettingsPatch,
	expected_versions: SettingsVersions | None = None,
	changed_by_id: TypeID | None = None,
	origin_session_id: str | None = None,
) -> SettingsVersions:
	"""apply patch to db overrides, return new versions.

	commits, reloads the settings snapshot in this process, signals every other
	process to do the same, then drops derived state belonging to features the
	patch turned off.
	"""
	# exclude_unset=True: only include fields present in the request body.
	# this lets callers explicitly send null to clear a nullable field,
	# while omitted fields stay default (None) and are excluded.
	raw_updates = patch.model_dump(exclude_unset=True)
	affected_access_types: list[ResourceType] = []
	patched_default_permissions = settings.default_permissions
	default_permissions_update = raw_updates.get("default_permissions")
	if isinstance(default_permissions_update, Mapping):
		patched_default_permissions = type(settings.default_permissions).model_validate(
			deep_merge(
				settings.default_permissions.model_dump(mode="json"),
				default_permissions_update,
			)
		)
		affected_access_types = changed_default_access_resource_types(
			settings.default_permissions.resource_access,
			patched_default_permissions.resource_access,
		)
		if (
			settings.default_permissions.action_permissions
			!= patched_default_permissions.action_permissions
		):
			affected_access_types = list(ResourceType)
	updates: dict[str, dict[str, object]] = {}
	for section, fields in raw_updates.items():
		if not isinstance(section, str) or not isinstance(fields, dict) or not fields:
			continue
		normalized_fields: dict[str, object] = {}
		for field_name, value in fields.items():
			if isinstance(field_name, str):
				normalized_fields[field_name] = value
		if normalized_fields:
			updates[section] = normalized_fields

	expected = expected_versions.model_dump() if expected_versions else {}
	new_versions: dict[str, int] = {}

	for section, fields in updates.items():
		section_info = Settings.model_fields.get(section)
		if not section_info:
			raise ValueError(f"unknown section: {section}")

		annotation = section_info.annotation
		if not isinstance(annotation, type) or not issubclass(annotation, BaseModel):
			raise ValueError(f"invalid section: {section}")

		# validate all fields are writable (defense in depth)
		check_writable(annotation, fields, section)

		doc = await _get_doc(db, section)
		if doc is None:
			doc = SettingsDocument(
				namespace=section,
				data=fields,
				version=1,
				updated_by_id=changed_by_id,
			)
			db.add(doc)
		else:
			if section in expected and doc.version != expected[section]:
				raise VersionConflictError(section, expected[section], doc.version)
			doc.data = deep_merge(doc.data, fields)
			doc.version += 1
			doc.updated_by_id = changed_by_id

		new_versions[section] = doc.version

	# fill unchanged sections
	for section in Settings.model_fields:
		if section not in new_versions:
			doc = await _get_doc(db, section)
			new_versions[section] = doc.version if doc else 0

	versions_out = SettingsVersions.model_validate(new_versions)
	event = Event(
		scope=EventScope.SYSTEM,
		type=EventType.SETTINGS_UPDATED,
		data={
			"updated_sections": list(updates.keys()),
			"versions": new_versions,
			"updated_by_id": changed_by_id,
		},
	)
	await persist_and_fanout_event(db, event=event, origin_session_id=origin_session_id)
	if affected_access_types:
		await invalidate_accessible_users_for_resource_types(affected_access_types)
		await persist_and_fanout_event(
			db,
			Event(
				scope=EventScope.SYSTEM,
				type=EventType.ACCESS_DEFAULTS_CHANGED,
				data={
					"resource_types": [
						resource_type.value for resource_type in affected_access_types
					]
				},
				user_id=changed_by_id,
			),
			origin_session_id=origin_session_id,
		)

	await db.commit()
	await run_post_commit_actions_safely(db)
	# apply locally, then signal every other process to do the same
	await apply_settings_change()
	await publish_invalidation(SETTINGS_INVALIDATION_SIGNAL)

	if not settings.assets.thread_passages.enabled:
		# no stale rows, vectors, or reconcile stamps may survive the toggle.
		await purge_thread_content_vectors(db)
		await db.commit()

	return versions_out
