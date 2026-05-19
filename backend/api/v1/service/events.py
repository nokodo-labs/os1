"""event service helpers.

this module centralizes event persistence and websocket fanout.

resource events (note.*, thread.*, file.*, etc.) are automatically routed
to all users with at least READER access to the affected resource.
non-resource events route by scope: user scope targets scope_id, and system
scope broadcasts globally.

task lifecycle events are intentionally user-scoped instead of resource-routed.
the task API currently defines task visibility as owner/admin only, and task
create events are emitted before the creating transaction has committed the
Task row. routing those events through ResourceType.TASK can cache an empty
recipient set and suppress later live updates for the same task.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable, Coroutine, Iterable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated, Any

from fastapi import Header, HTTPException, WebSocket, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import async_session_local
from api.local_tasks import create_background_task
from api.models.event import Event, EventScope
from api.models.event_types import EventType
from api.permissions import ResourceType
from api.schemas.event import EventCreate, EventListFilters
from api.v1.service import event_bus
from api.v1.service.auth import Principal
from api.v1.service.authorization import list_accessible_user_ids, require_permission
from nokodo_ai.utils.typeid import TypeID, new_typeid


logger = logging.getLogger(__name__)

# shared annotated type - add to any router param that mutates resources.
# FastAPI maps the parameter name x_session_id -> header X-Session-ID.
SessionId = Annotated[str | None, Header()]


if TYPE_CHECKING:
	from api.models.event import Event as EventModel


@dataclass(frozen=True)
class _EventResourceTarget:
	resource_type: ResourceType
	data_keys: tuple[str, ...]


def _event_target(
	resource_type: ResourceType,
	data_keys: tuple[str, ...],
) -> _EventResourceTarget:
	return _EventResourceTarget(
		resource_type=resource_type,
		data_keys=data_keys,
	)


_EVENT_ROUTING_TARGETS: dict[str, _EventResourceTarget] = {
	EventType.NOTE_CREATED: _event_target(ResourceType.NOTE, ("id",)),
	EventType.NOTE_UPDATED: _event_target(ResourceType.NOTE, ("id",)),
	EventType.NOTE_DELETED: _event_target(ResourceType.NOTE, ("id",)),
	EventType.THREAD_CREATED: _event_target(ResourceType.THREAD, ("id",)),
	EventType.THREAD_UPDATED: _event_target(ResourceType.THREAD, ("id",)),
	EventType.THREAD_DELETED: _event_target(ResourceType.THREAD, ("id",)),
	EventType.THREAD_READ: _event_target(ResourceType.THREAD, ("thread_id", "id")),
	EventType.MESSAGE_CREATED: _event_target(ResourceType.THREAD, ("thread_id",)),
	EventType.MESSAGE_UPDATED: _event_target(ResourceType.THREAD, ("thread_id",)),
	EventType.MESSAGE_DELETED: _event_target(ResourceType.THREAD, ("thread_id",)),
	EventType.FILE_CREATED: _event_target(ResourceType.FILE, ("id",)),
	EventType.FILE_UPDATED: _event_target(ResourceType.FILE, ("id",)),
	EventType.FILE_DELETED: _event_target(ResourceType.FILE, ("id",)),
	EventType.FILE_PROCESSING: _event_target(ResourceType.FILE, ("id",)),
	EventType.FILE_READY: _event_target(ResourceType.FILE, ("id",)),
	EventType.AGENT_CREATED: _event_target(ResourceType.AGENT, ("id",)),
	EventType.AGENT_UPDATED: _event_target(ResourceType.AGENT, ("id",)),
	EventType.AGENT_DELETED: _event_target(ResourceType.AGENT, ("id",)),
	EventType.PROJECT_CREATED: _event_target(ResourceType.PROJECT, ("id",)),
	EventType.PROJECT_UPDATED: _event_target(ResourceType.PROJECT, ("id",)),
	EventType.PROJECT_DELETED: _event_target(ResourceType.PROJECT, ("id",)),
	EventType.MEMORY_CREATED: _event_target(ResourceType.MEMORY, ("id",)),
	EventType.MEMORY_UPDATED: _event_target(ResourceType.MEMORY, ("id",)),
	EventType.MEMORY_DELETED: _event_target(ResourceType.MEMORY, ("id",)),
	EventType.REMINDER_LIST_CREATED: _event_target(
		ResourceType.REMINDER_LIST,
		("id",),
	),
	EventType.REMINDER_LIST_UPDATED: _event_target(
		ResourceType.REMINDER_LIST,
		("id",),
	),
	EventType.REMINDER_LIST_DELETED: _event_target(
		ResourceType.REMINDER_LIST,
		("id",),
	),
	EventType.REMINDER_CREATED: _event_target(ResourceType.REMINDER_LIST, ("list_id",)),
	EventType.REMINDER_UPDATED: _event_target(ResourceType.REMINDER_LIST, ("list_id",)),
	EventType.REMINDER_COMPLETED: _event_target(
		ResourceType.REMINDER_LIST,
		("list_id",),
	),
	EventType.REMINDER_DELETED: _event_target(ResourceType.REMINDER_LIST, ("list_id",)),
	EventType.CALENDAR_CREATED: _event_target(ResourceType.CALENDAR, ("id",)),
	EventType.CALENDAR_UPDATED: _event_target(ResourceType.CALENDAR, ("id",)),
	EventType.CALENDAR_DELETED: _event_target(ResourceType.CALENDAR, ("id",)),
	EventType.CALENDAR_EVENT_CREATED: _event_target(
		ResourceType.CALENDAR,
		("calendar_id",),
	),
	EventType.CALENDAR_EVENT_UPDATED: _event_target(
		ResourceType.CALENDAR,
		("calendar_id",),
	),
	EventType.CALENDAR_EVENT_DELETED: _event_target(
		ResourceType.CALENDAR,
		("calendar_id",),
	),
	EventType.GROUP_CREATED: _event_target(ResourceType.GROUP, ("id",)),
	EventType.GROUP_UPDATED: _event_target(ResourceType.GROUP, ("id",)),
	EventType.GROUP_DELETED: _event_target(ResourceType.GROUP, ("id",)),
	EventType.GROUP_MEMBER_ADDED: _event_target(ResourceType.GROUP, ("group_id",)),
	EventType.GROUP_MEMBER_REMOVED: _event_target(ResourceType.GROUP, ("group_id",)),
	EventType.RUN_STARTED: _event_target(ResourceType.THREAD, ("thread_id",)),
	EventType.RUN_COMPLETED: _event_target(ResourceType.THREAD, ("thread_id",)),
	EventType.RUN_ERROR: _event_target(ResourceType.THREAD, ("thread_id",)),
	EventType.RUN_STEERING_QUEUED: _event_target(
		ResourceType.THREAD,
		("thread_id",),
	),
	EventType.RUN_STEERING_INJECTED: _event_target(
		ResourceType.THREAD,
		("thread_id",),
	),
	EventType.RUN_STEERING_DROPPED: _event_target(
		ResourceType.THREAD,
		("thread_id",),
	),
	EventType.TOOL_PROGRESS: _event_target(ResourceType.THREAD, ("thread_id",)),
	EventType.TOOL_CUSTOM: _event_target(ResourceType.THREAD, ("thread_id",)),
	EventType.TOOL_NOTIFICATION: _event_target(ResourceType.THREAD, ("thread_id",)),
	EventType.CITATION_SOURCES: _event_target(ResourceType.THREAD, ("thread_id",)),
}


def _resource_id_from_data(
	data: Mapping[str, object],
	keys: tuple[str, ...],
) -> TypeID | None:
	for key in keys:
		value = data.get(key)
		if value is not None:
			return TypeID(str(value))
	return None


def _resolve_routing(event: Event) -> tuple[ResourceType, TypeID] | None:
	"""resolve the resource type and ID for access-based fan-out.

	returns None for events that should use the legacy routing path
	(owner-only or broadcast).
	"""
	target = _EVENT_ROUTING_TARGETS.get(event.type)
	if target is None:
		return None
	resource_type = target.resource_type
	resource_id = (
		_resource_id_from_data(event.data, target.data_keys) if event.data else None
	)
	if not resource_id and resource_type == ResourceType.THREAD and event.thread_id:
		resource_id = event.thread_id
	if not resource_id and resource_type == ResourceType.TASK and event.task_id:
		resource_id = event.task_id
	if not resource_id:
		return None
	return (resource_type, resource_id)


def _event_scope(event: Event) -> str:
	if isinstance(event.scope, EventScope):
		return event.scope.value
	return str(event.scope)


def _scope_user_recipient_id(event: Event) -> TypeID | None:
	"""resolve the direct-user recipient from event scope."""
	if _event_scope(event) == EventScope.USER.value and event.scope_id is not None:
		return TypeID(str(event.scope_id))
	return None


def _scope_broadcasts(event: Event) -> bool:
	return _event_scope(event) == EventScope.SYSTEM.value


def _build_event_data(
	event: EventModel,
	origin_session_id: str | None = None,
) -> dict[str, Any]:
	"""serialize an event model into a JSON-safe dict for WS transmission."""
	return {
		"id": str(event.id),
		"type": event.type,
		"scope": _event_scope(event),
		"scope_id": str(event.scope_id) if event.scope_id else None,
		"data": event.data,
		"version": event.version,
		"user_id": str(event.user_id) if event.user_id else None,
		"thread_id": str(event.thread_id) if event.thread_id else None,
		"message_id": str(event.message_id) if event.message_id else None,
		"task_id": str(event.task_id) if event.task_id else None,
		"project_id": str(event.project_id) if event.project_id else None,
		"calendar_id": str(event.calendar_id) if event.calendar_id else None,
		"calendar_event_id": str(event.calendar_event_id)
		if event.calendar_event_id
		else None,
		"reminder_list_id": str(event.reminder_list_id)
		if event.reminder_list_id
		else None,
		"reminder_id": str(event.reminder_id) if event.reminder_id else None,
		"created_at": event.created_at.isoformat() if event.created_at else None,
		"origin_session_id": origin_session_id,
	}


def _affected_project_ids(event: Event) -> list[TypeID]:
	if not event.data:
		return []
	value = event.data.get("affected_project_ids")
	if not isinstance(value, Iterable) or isinstance(value, (str, bytes)):
		return []
	project_ids: list[TypeID] = []
	for raw_project_id in value:
		if raw_project_id is None:
			continue
		project_ids.append(TypeID(str(raw_project_id)))
	return _unique_recipient_ids(project_ids)


async def _resolve_event_recipient_ids(
	event: Event,
) -> list[TypeID] | None:
	"""resolve all user IDs that should receive this event.

	uses a fresh read-only session because the caller's session may already
	be closed by the time recipients are needed (persist_and_fanout_event commits
	before resolving so newly-created rows are visible to the lookup).
	resource events carrying affected_project_ids are also routed to users who
	can read those projects, so moved resources reach old and new project viewers.
	returns None when the event has no resource route; scope routing handles
	direct-user or system broadcast delivery.
	"""
	routing = _resolve_routing(event)
	if not routing:
		return None
	resource_type, resource_id = routing
	async with async_session_local() as session:
		recipients = await list_accessible_user_ids(
			resource_type,
			resource_id,
			session,
		)
		project_ids = _affected_project_ids(event)
		if project_ids:
			recipients.extend(
				await _resolve_project_recipient_ids(project_ids, session)
			)
		return _unique_recipient_ids(recipients)


def _unique_recipient_ids(values: Iterable[TypeID]) -> list[TypeID]:
	result: list[TypeID] = []
	seen: set[str] = set()
	for value in values:
		key = str(value)
		if key in seen:
			continue
		seen.add(key)
		result.append(TypeID(key))
	return result


async def _resolve_project_recipient_ids(
	project_ids: Iterable[TypeID],
	session: AsyncSession,
) -> list[TypeID]:
	"""return users who can currently read any of the given projects."""
	recipients: list[TypeID] = []
	for project_id in project_ids:
		recipients.extend(
			await list_accessible_user_ids(
				ResourceType.PROJECT,
				project_id,
				session,
			)
		)
	return _unique_recipient_ids(recipients)


async def _send_live_payload_locally(
	stream_payload: dict[str, Any],
	recipient_ids: list[TypeID] | None,
	user_id: TypeID | str | None,
	broadcast: bool,
	exclude_user_id: TypeID | str | None = None,
) -> None:
	if recipient_ids is not None:
		if recipient_ids:
			exclude = TypeID(str(exclude_user_id)) if exclude_user_id else None
			await event_connections.send_to_users(
				recipient_ids,
				stream_payload,
				exclude_user_id=exclude,
			)
		return
	if user_id:
		await event_connections.send_to_user(TypeID(str(user_id)), stream_payload)
	elif broadcast:
		await event_connections.send_to_all(stream_payload)


async def fanout_live_payload(
	stream_payload: dict[str, Any],
	recipient_ids: list[TypeID] | None,
	user_id: TypeID | str | None,
	broadcast: bool,
	exclude_user_id: TypeID | str | None = None,
) -> None:
	"""deliver a websocket payload locally and relay it to other API workers."""
	if recipient_ids is not None and not recipient_ids:
		return
	if recipient_ids is None and user_id is None and not broadcast:
		logger.debug(
			"live payload has no delivery target: %s",
			stream_payload.get("type"),
		)
		return
	await _send_live_payload_locally(
		stream_payload,
		recipient_ids,
		user_id,
		broadcast,
		exclude_user_id,
	)
	await event_bus.publish_remote_fanout(
		stream_payload,
		recipient_ids=recipient_ids,
		user_id=user_id,
		broadcast=broadcast,
		exclude_user_id=exclude_user_id,
	)


async def _fanout_event_scope(
	event: Event,
	stream_payload: dict[str, Any],
) -> None:
	user_id = _scope_user_recipient_id(event)
	if user_id is not None:
		await fanout_live_payload(stream_payload, None, user_id, False)
	elif _scope_broadcasts(event):
		await fanout_live_payload(stream_payload, None, None, True)
	else:
		logger.debug(
			"event has no live delivery target: type=%s scope=%s",
			event.type,
			_event_scope(event),
		)


async def start_remote_fanout_relay() -> asyncio.Task[None]:
	"""start the redis listener that sends remote websocket payloads locally."""
	return await event_bus.start_remote_fanout_listener(_send_live_payload_locally)


class ConnectionManager:
	"""manages process-local websocket connections per user."""

	def __init__(self) -> None:
		self._connections: dict[TypeID, set[WebSocket]] = defaultdict(set)
		self._lock = asyncio.Lock()

	async def connect(self, user_id: TypeID, websocket: WebSocket) -> None:
		await websocket.accept()
		async with self._lock:
			self._connections[user_id].add(websocket)
		logger.debug("websocket connected for user %s", user_id)

	async def disconnect(self, user_id: TypeID, websocket: WebSocket) -> None:
		async with self._lock:
			self._connections[user_id].discard(websocket)
			if not self._connections[user_id]:
				del self._connections[user_id]
		logger.debug("websocket disconnected for user %s", user_id)

	async def send_to_user(self, user_id: TypeID, data: dict[str, Any]) -> None:
		async with self._lock:
			connections = list(self._connections.get(user_id, []))

		for websocket in connections:
			try:
				await websocket.send_json(data)
			except Exception:
				logger.debug("failed to send to websocket for user %s", user_id)

	async def send_to_users(
		self,
		user_ids: list[TypeID],
		data: dict[str, Any],
		exclude_user_id: TypeID | None = None,
	) -> None:
		"""send to all sessions of multiple users concurrently."""
		targets = (uid for uid in user_ids if uid != exclude_user_id)
		await asyncio.gather(*(self.send_to_user(uid, data) for uid in targets))

	async def send_to_all(self, data: dict[str, Any]) -> None:
		async with self._lock:
			all_connections = [
				(user_id, ws)
				for user_id, sockets in self._connections.items()
				for ws in sockets
			]

		for user_id, websocket in all_connections:
			try:
				await websocket.send_json(data)
			except Exception:
				logger.debug("failed to broadcast to user %s", user_id)


event_connections = ConnectionManager()

EventEmitter = Callable[[Event], Awaitable[None]]


def build_live_persisting_event_emitter(
	message_id_provider: Callable[[], str | None] | None = None,
	before_persist: Callable[[Event], Awaitable[None]] | None = None,
) -> EventEmitter:
	"""create a non-blocking emitter that fanouts immediately and persists async.

	This is the "core" behavior: tools/filters should never be able to emit events
	that vanish (no no-op emitter). Persistence happens in a separate session.

	recipient lists are resolved on first use per resource and cached for the
	lifetime of this emitter (a single agent run).
	"""
	_recipient_cache: dict[str, list[TypeID]] = {}

	async def _fanout_with_cached_route(event: Event) -> None:
		"""fanout an event with access-based routing cached per resource."""
		event_data = _build_event_data(event)
		routing = _resolve_routing(event)
		if routing:
			resource_type, resource_id = routing
			cache_key = f"{resource_type.value}:{resource_id}"
			if cache_key not in _recipient_cache:
				async with async_session_local() as read_session:
					_recipient_cache[cache_key] = await list_accessible_user_ids(
						resource_type,
						resource_id,
						read_session,
					)
			user_ids = _recipient_cache[cache_key]
			await fanout_live_payload(event_data, user_ids, None, False)
			return
		await _fanout_event_scope(event, event_data)

	def _track(name: str, coro: Coroutine[object, object, object]) -> None:
		create_background_task(coro, name=name)

	async def emit(event: Event) -> None:
		# ensure stable id for correlation
		if not event.id:
			event.id = TypeID(new_typeid("event"))

		# attach message correlation if available
		if event.message_id is None and message_id_provider:
			msg_id = message_id_provider()
			if msg_id:
				event.message_id = TypeID(msg_id)

		# fanout immediately with access-based routing
		_track(
			"event_fanout",
			_fanout_with_cached_route(event),
		)

		# persist in background (without broadcasting again)
		async def _persist() -> None:
			if before_persist is not None:
				await before_persist(event)
			copy = Event(
				id=event.id,
				scope=event.scope,
				scope_id=event.scope_id,
				type=event.type,
				data=event.data,
				expires_at=event.expires_at,
				version=event.version,
				user_id=event.user_id,
				thread_id=event.thread_id,
				message_id=event.message_id,
				task_id=event.task_id,
				project_id=event.project_id,
				calendar_id=event.calendar_id,
				calendar_event_id=event.calendar_event_id,
				reminder_list_id=event.reminder_list_id,
				reminder_id=event.reminder_id,
				metadata_=event.metadata_,
			)
			async with async_session_local() as bg_session:
				bg_session.add(copy)
				await bg_session.commit()

		_track("event_persist", _persist())

	return emit


async def fanout_event(
	event: Event,
	origin_session_id: str | None = None,
	recipient_ids: list[TypeID] | None = None,
) -> None:
	"""deliver an already-built event through websocket fanout without persisting."""
	resolved_recipient_ids = recipient_ids
	if resolved_recipient_ids is None:
		resolved_recipient_ids = await _resolve_event_recipient_ids(event)

	stream_payload = _build_event_data(event, origin_session_id)
	await _fanout_event_with_recipients(event, stream_payload, resolved_recipient_ids)


async def _fanout_event_with_recipients(
	event: Event,
	stream_payload: dict[str, Any],
	recipient_ids: list[TypeID] | None,
) -> None:
	if recipient_ids is not None:
		await fanout_live_payload(stream_payload, recipient_ids, None, False)
	else:
		await _fanout_event_scope(event, stream_payload)


async def persist_and_fanout_event(
	session: AsyncSession,
	event: Event,
	origin_session_id: str | None = None,
	recipient_ids: list[TypeID] | None = None,
) -> Event:
	"""persist an event and deliver it through its resolved websocket route.

	explicit recipients override route resolution. otherwise, resource events are
	sent to users with access. non-resource events route by scope: user scope
	targets scope_id, system scope broadcasts, and other unroutable scopes are
	persisted without live delivery.

	the event is committed before recipients are resolved so newly-created
	resource rows (e.g. THREAD_CREATED) are visible to the recipient lookup
	and to the cache it populates. callers that hard-delete a resource and
	still need to notify users beyond superusers must pass ``recipient_ids``
	explicitly, since the row is gone after commit.
	"""
	session.add(event)
	await session.commit()

	resolved_recipient_ids = recipient_ids
	if resolved_recipient_ids is None:
		resolved_recipient_ids = await _resolve_event_recipient_ids(event)

	await _fanout_event_with_recipients(
		event,
		_build_event_data(event, origin_session_id),
		resolved_recipient_ids,
	)

	return event


async def create_event_from_request(
	event_in: EventCreate,
	session: AsyncSession,
	principal: Principal,
) -> Event:
	"""validate an event create request, persist it, and fanout live updates."""
	require_permission(principal, "events:manage")
	if event_in.user_id is not None and not principal.is_admin:
		if event_in.user_id != principal.user_id:
			raise HTTPException(
				status_code=status.HTTP_403_FORBIDDEN,
				detail="forbidden",
			)
	if (
		event_in.scope == EventScope.USER
		and event_in.scope_id is not None
		and not principal.is_admin
		and event_in.scope_id != principal.user_id
	):
		raise HTTPException(
			status_code=status.HTTP_403_FORBIDDEN,
			detail="forbidden",
		)
	event = Event(**event_in.model_dump(by_alias=True))
	return await persist_and_fanout_event(session, event=event)


async def list_events(
	session: AsyncSession,
	principal: Principal,
	filters: EventListFilters | None = None,
) -> list[Event]:
	require_permission(principal, "events:manage")
	event_filters = filters or EventListFilters()
	stmt = select(Event).order_by(Event.created_at.desc())

	if event_filters.scope is not None:
		stmt = stmt.where(Event.scope == event_filters.scope)
	if event_filters.thread_id is not None:
		stmt = stmt.where(Event.thread_id == event_filters.thread_id)
	if event_filters.task_id is not None:
		stmt = stmt.where(Event.task_id == event_filters.task_id)
	if event_filters.user_id is not None:
		stmt = stmt.where(Event.user_id == event_filters.user_id)
	if event_filters.since is not None:
		stmt = stmt.where(Event.created_at >= event_filters.since)

	result = await session.execute(stmt.limit(200))
	return list(result.scalars().all())
