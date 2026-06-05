"""message/file provenance helpers."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.access_rule import AccessLevel
from api.models.event import Event, EventScope
from api.models.event_types import EventType
from api.models.file import File
from api.permissions import ResourceType
from api.schemas.message import ContentPart, FileContent, ImageContent
from api.v1.service import events as event_service
from api.v1.service.auth import Principal
from api.v1.service.authorization import (
	invalidate_accessible_users_for_resource,
	resource_access_predicate,
)
from api.v1.service.resource_payload_cache import invalidate_resource_payload_cache
from nokodo_ai.utils.typeid import TypeID


def _content_file_ids(content: Sequence[ContentPart]) -> list[TypeID]:
	file_ids: list[TypeID] = []
	seen: set[str] = set()
	for content_part in content:
		if not isinstance(content_part, ImageContent | FileContent):
			continue
		metadata = content_part.metadata
		if not metadata:
			continue
		file_id_value = metadata.get("file_id")
		if not isinstance(file_id_value, str) or not file_id_value.startswith("file_"):
			continue
		try:
			file_id = TypeID(file_id_value)
		except ValueError:
			continue
		file_id_key = str(file_id)
		if file_id_key in seen:
			continue
		seen.add(file_id_key)
		file_ids.append(file_id)
	return file_ids


async def link_message_content_files(
	session: AsyncSession,
	content: Sequence[ContentPart],
	message_id: TypeID,
	principal: Principal,
) -> list[TypeID]:
	"""claim unlinked file references for the first message that stores them."""
	file_ids = _content_file_ids(content)
	if not file_ids:
		return []
	result = await session.execute(
		update(File)
		.where(
			File.id.in_(file_ids),
			File.message_id.is_(None),
			resource_access_predicate(
				principal,
				ResourceType.FILE,
				required_level=AccessLevel.READER,
			),
		)
		.values(message_id=message_id)
		.returning(File.id)
	)
	return [TypeID(str(file_id)) for file_id in result.scalars().all()]


async def invalidate_message_file_link_caches(
	session: AsyncSession,
	file_ids: Sequence[TypeID],
) -> None:
	"""invalidate file resource caches after message provenance updates."""
	for file_id in file_ids:
		await invalidate_resource_payload_cache(ResourceType.FILE, file_id)
		await invalidate_accessible_users_for_resource(
			ResourceType.FILE,
			file_id,
			session,
		)


async def fanout_message_file_link_updates(
	session: AsyncSession,
	file_ids: Sequence[TypeID],
	user_id: TypeID,
	origin_session_id: str | None = None,
) -> None:
	"""fan out file updates after message provenance changes."""
	for file_id in file_ids:
		await event_service.persist_and_fanout_event(
			session,
			event=Event(
				scope=EventScope.USER,
				scope_id=user_id,
				type=EventType.FILE_UPDATED,
				data={"id": str(file_id)},
				user_id=user_id,
			),
			origin_session_id=origin_session_id,
		)
