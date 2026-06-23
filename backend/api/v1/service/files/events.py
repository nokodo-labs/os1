"""file lifecycle event emission.

shared by both the CRUD service (service.py) and the background processing
service (processing.py). it lives in its own leaf module so neither of those
modules has to import the other: service.py enqueues background work via the
tasks layer, and the tasks layer wires into processing.py, so a direct
service <-> processing event dependency would form an import cycle.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from api.models.event import Event, EventScope
from api.models.event_types import EventType
from api.v1.service import events as event_service
from nokodo_ai.utils.typeid import TypeID


async def emit_file_event(
	session: AsyncSession,
	event_type: EventType,
	file_id: TypeID,
	user_id: TypeID,
	filename: str | None = None,
	project_ids: list[TypeID] | None = None,
	affected_project_ids: set[TypeID] | None = None,
	origin_session_id: str | None = None,
	recipient_ids: list[TypeID] | None = None,
) -> None:
	"""persist and fanout a file lifecycle event."""
	data: dict[str, object] = {"id": str(file_id)}
	if filename is not None:
		data["filename"] = filename
	if project_ids is not None:
		data["project_ids"] = [str(project_id) for project_id in project_ids]
	if affected_project_ids:
		data["affected_project_ids"] = [
			str(project_id) for project_id in affected_project_ids
		]
	event = Event(
		scope=EventScope.USER,
		scope_id=user_id,
		type=event_type,
		data=data,
		user_id=user_id,
	)
	await event_service.persist_and_fanout_event(
		session,
		event=event,
		origin_session_id=origin_session_id,
		recipient_ids=recipient_ids,
	)
