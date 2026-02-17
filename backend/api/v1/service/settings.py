"""settings service."""

from __future__ import annotations

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.event import Event, EventScope
from api.models.event_types import EventType
from api.models.setting import SettingsDocument
from api.settings import Settings, check_writable
from api.v1.schemas.settings import SettingsPatch, SettingsVersions
from api.v1.service import events as event_service
from nokodo_ai.utils.dicts import deep_merge


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
	*,
	expected_versions: SettingsVersions | None = None,
	changed_by_id: str | None = None,
	origin_session_id: str | None = None,
) -> SettingsVersions:
	"""apply patch to db overrides, return new versions."""
	updates = {
		section: fields
		for section, fields in patch.model_dump(exclude_none=True).items()
		if isinstance(fields, dict) and fields
	}

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

	# emit settings.updated event
	event = Event(
		scope=EventScope.SYSTEM,
		type=EventType.SETTINGS_UPDATED,
		data={
			"updated_sections": list(updates.keys()),
			"versions": new_versions,
		},
		user_id=changed_by_id,
	)
	await event_service.publish_event(
		db, event=event, origin_session_id=origin_session_id
	)

	return versions_out
