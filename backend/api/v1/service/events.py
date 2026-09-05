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

import asyncio
import copy
import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated, Any

from fastapi import Header, WebSocket
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import async_session_local
from api.database.post_commit import run_post_commit_actions_safely
from api.local_tasks import create_background_task
from api.models.event import Event, EventScope
from api.models.event_types import EventType
from api.permissions import ActionPermission, ResourceType
from api.schemas.event import EventCreate, EventListFilters
from api.v1.service.authentication import Principal
from api.v1.service.authorization import (
	apply_metadata_write,
	list_accessible_user_ids_for_resources,
	require_permission,
)
from api.v1.service.event_bus import (
	dispatch_server_event,
	publish_remote_fanout,
	publish_socket_kill,
	start_remote_fanout_listener,
	start_socket_kill_listener,
)
from nokodo_ai.utils.typeid import TypeID, is_typeid, new_typeid


logger = logging.getLogger(__name__)

SessionId = Annotated[str | None, Header()]
"""the client session behind a mutating request, from ``X-Session-ID``.

add to any router param that mutates resources: it is what lets the originating
client be excluded from its own fanout. FastAPI derives the header name from the
parameter, so it must be declared as ``x_session_id``.
"""


if TYPE_CHECKING:
	from api.models.event import Event as EventModel


@dataclass(frozen=True)
class _EventResourceTarget:
	"""which resource governs who receives one kind of event."""

	resource_type: ResourceType
	"""the resource whose access list decides the recipients."""
	data_keys: tuple[str, ...]
	"""where to find that resource's id in the event payload, in order."""


def _event_target(
	resource_type: ResourceType,
	data_keys: tuple[str, ...],
) -> _EventResourceTarget:
	"""name the resource one event type routes by."""
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
	EventType.RUN_ACTIVITY_STARTED: _event_target(
		ResourceType.THREAD,
		("thread_id",),
	),
	EventType.RUN_ACTIVITY_PROGRESS: _event_target(
		ResourceType.THREAD,
		("thread_id",),
	),
	EventType.RUN_ACTIVITY_ENDED: _event_target(
		ResourceType.THREAD,
		("thread_id",),
	),
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
"""every event type that fans out by resource access, and what it routes by.

an event type absent from here has no resource governing it, so it falls back
to scope routing: one user, or a system broadcast.
"""


def _resource_id_from_data(
	data: Mapping[str, object],
	keys: tuple[str, ...],
) -> TypeID | None:
	"""pull the routing resource's id out of an event payload.

	keys are tried in order, so an event carrying several ids names the one it
	routes by first.
	"""
	for key in keys:
		value = data.get(key)
		if value is not None and is_typeid(str(value)):
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
	"""the event's scope as a plain string.

	the column round-trips as either the enum or its value depending on where
	the row came from, and every caller only wants to compare it.
	"""
	if isinstance(event.scope, EventScope):
		return event.scope.value
	return str(event.scope)


def _scope_user_recipient_id(event: Event) -> TypeID | None:
	"""resolve the direct-user recipient from event scope."""
	if _event_scope(event) == EventScope.USER.value and event.scope_id is not None:
		return TypeID(str(event.scope_id))
	return None


def _scope_broadcasts(event: Event) -> bool:
	"""whether this event goes to everyone rather than a resolved audience."""
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
		"metadata": event.public_metadata,
		"version": event.version,
		"resource_revision": event.resource_revision,
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


async def _resolve_event_recipient_ids(
	event: Event,
) -> list[TypeID] | None:
	"""resolve all user IDs that should receive this event.

	uses a fresh read-only session because the caller's session may already
	be closed by the time recipients are needed (persist_and_fanout_event commits
	before resolving so newly-created rows are visible to the lookup).
	returns None when the event has no resource route; scope routing handles
	direct-user or system broadcast delivery.
	"""
	routing = _resolve_routing(event)
	if not routing:
		return None
	resource_type, resource_id = routing
	return await list_accessible_user_ids_for_resources(
		[(resource_type, resource_id)], None
	)


def _unique_recipient_ids(values: Iterable[TypeID]) -> list[TypeID]:
	"""dedupe recipients while keeping their order.

	the same user can be reached through several rules at once, and nobody
	should receive one event twice.
	"""
	result: list[TypeID] = []
	seen: set[str] = set()
	for value in values:
		key = str(value)
		if key in seen:
			continue
		seen.add(key)
		result.append(TypeID(key))
	return result


async def _send_live_payload_locally(
	stream_payload: dict[str, Any],
	recipient_ids: list[TypeID] | None,
	user_id: TypeID | str | None,
	broadcast: bool,
	exclude_user_id: TypeID | str | None = None,
) -> None:
	"""dispatch server subscribers, then deliver to local WebSockets."""
	await dispatch_server_event(stream_payload)
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
	"""dispatch a live event locally and relay it to every API process."""
	await _send_live_payload_locally(
		stream_payload,
		recipient_ids,
		user_id,
		broadcast,
		exclude_user_id,
	)
	await publish_remote_fanout(
		stream_payload,
		recipient_ids=recipient_ids,
		user_id=user_id,
		broadcast=broadcast,
		exclude_user_id=exclude_user_id,
	)


async def broadcast_to_resource(
	resource_type: ResourceType,
	resource_id: TypeID,
	stream_payload: dict[str, Any],
	exclude_user_id: TypeID | str | None = None,
) -> None:
	"""deliver a live payload to everyone who can read a resource."""
	recipient_ids = await list_accessible_user_ids_for_resources(
		[(resource_type, resource_id)], None
	)
	if not recipient_ids:
		return
	await fanout_live_payload(
		stream_payload,
		recipient_ids,
		None,
		False,
		exclude_user_id=exclude_user_id,
	)


async def _fanout_event_scope(
	event: Event,
	stream_payload: dict[str, Any],
) -> None:
	"""deliver an event that no resource governs, by its scope alone.

	an event with neither a user nor a system scope has nowhere to go: it is
	still persisted, so it is logged rather than raised on.
	"""
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


async def start_remote_fanout_relay(
	on_connected: Callable[[], Awaitable[None]] | None = None,
) -> asyncio.Task[None]:
	"""start the redis listener that sends remote websocket payloads locally."""
	return await start_remote_fanout_listener(
		_send_live_payload_locally,
		on_connected,
	)


async def request_socket_kill(user_id: TypeID) -> None:
	"""close the user's websockets on every backend process."""
	await publish_socket_kill(user_id)


async def start_socket_kill_relay() -> asyncio.Task[None]:
	"""start the redis listener that force-closes revoked users' sockets."""

	async def _kill(user_id: TypeID) -> None:
		"""drop this process's sockets for a user revoked on another one."""
		await event_connections.close_user_connections(user_id)

	return await start_socket_kill_listener(_kill)


class ConnectionManager:
	"""manages process-local websocket connections per user."""

	def __init__(self) -> None:
		"""start with no connections held."""
		self._connections: dict[TypeID, set[WebSocket]] = defaultdict(set)
		self._lock = asyncio.Lock()

	async def connect(self, user_id: TypeID, websocket: WebSocket) -> None:
		"""accept one socket and track it against its user."""
		await websocket.accept()
		async with self._lock:
			self._connections[user_id].add(websocket)
		logger.debug("websocket connected for user %s", user_id)

	async def disconnect(self, user_id: TypeID, websocket: WebSocket) -> None:
		"""stop tracking one socket, and the user once none are left."""
		async with self._lock:
			self._connections[user_id].discard(websocket)
			if not self._connections[user_id]:
				del self._connections[user_id]
		logger.debug("websocket disconnected for user %s", user_id)

	async def send_to_user(self, user_id: TypeID, data: dict[str, Any]) -> None:
		"""send to every socket this user has open here.

		a socket that refuses the payload is already gone, so it is dropped
		rather than retried.
		"""
		async with self._lock:
			connections = list(self._connections.get(user_id, []))

		for websocket in connections:
			try:
				await websocket.send_json(data)
			except Exception:
				logger.debug("failed to send to websocket for user %s", user_id)
				await self.disconnect(user_id, websocket)

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
		"""send to every socket on this process, for system broadcasts."""
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
				await self.disconnect(user_id, websocket)

	async def close_user_connections(self, user_id: TypeID) -> None:
		"""force-close every open websocket for a user (session revocation)."""
		async with self._lock:
			connections = list(self._connections.pop(user_id, ()))
		for websocket in connections:
			try:
				await websocket.close(code=4002, reason="session revoked")
			except Exception:
				logger.debug("failed to close websocket for user %s", user_id)


event_connections = ConnectionManager()
"""this process's websocket connections; remote ones are reached over Redis."""

EventEmitter = Callable[[Event], Awaitable[None]]
"""how a tool or filter emits an event without knowing where it goes.

what an emitter does with the event - persist it, deliver it live, or both - is
the caller's choice at construction, not the tool's.
"""


def _copy_event(event: Event) -> Event:
	"""snapshot an event so later mutation cannot change what was delivered.

	the emitter hands events to a drain task, and the caller keeps using the
	original: without a copy, a payload could change between emit and write.
	"""
	return Event(
		id=event.id,
		scope=event.scope,
		scope_id=event.scope_id,
		type=event.type,
		data=copy.deepcopy(event.data),
		expires_at=event.expires_at,
		version=event.version,
		resource_revision=event.resource_revision,
		user_id=event.user_id,
		thread_id=event.thread_id,
		message_id=event.message_id,
		task_id=event.task_id,
		project_id=event.project_id,
		calendar_id=event.calendar_id,
		calendar_event_id=event.calendar_event_id,
		reminder_list_id=event.reminder_list_id,
		reminder_id=event.reminder_id,
		metadata_=copy.deepcopy(event.metadata_),
	)


def build_live_user_event_emitter(user_id: TypeID) -> EventEmitter:
	"""create an emitter that reaches one user's sockets and writes nothing.

	for a run defined by leaving no trace: its requester still watches it work,
	but no row outlives the request and nobody else is told it happened.
	"""

	async def emit(event: Event) -> None:
		"""deliver one event to its user, giving it an id if it has none."""
		if not event.id:
			event.id = TypeID(new_typeid("event"))
		await fanout_live_payload(_build_event_data(event), None, user_id, False)

	return emit


def build_live_persisting_event_emitter(
	before_persist: Callable[[Event], Awaitable[None]] | None = None,
	on_emit: Callable[[], Awaitable[None]] | None = None,
) -> EventEmitter:
	"""create an emitter for consistent durable and live events.

	this is the core behavior: tools and filters never emit events
	that vanish (no no-op emitter). delivery happens from the persisted snapshot.

	emitting hands the event to a drain task rather than awaiting the write, so
	it does not block a run's tool loop until ``maxsize`` events are in flight;
	past that it applies backpressure, which is deliberate - a producer that
	outruns the database that far is emitting faster than anyone can read.

	recipient lists are resolved for every event so access changes take effect
	during a long-running emitter.
	"""
	queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=256)
	drain_lock = asyncio.Lock()
	drain_task: asyncio.Task[None] | None = None

	async def _fanout_with_current_route(event: Event) -> None:
		"""fanout an event using the current access route."""
		event_data = _build_event_data(event)
		routing = _resolve_routing(event)
		if routing:
			resource_type, resource_id = routing
			user_ids = await list_accessible_user_ids_for_resources(
				[(resource_type, resource_id)], None
			)
			await fanout_live_payload(event_data, user_ids, None, False)
			return
		await _fanout_event_scope(event, event_data)

	async def _persist_and_fanout(snapshot: Event) -> None:
		"""write one event, then deliver the row that was written.

		delivering from the snapshot rather than the caller's object is what
		makes the durable and live views of an event identical.
		"""
		if before_persist is not None:
			await before_persist(snapshot)
		async with async_session_local() as bg_session:
			bg_session.add(snapshot)
			await bg_session.commit()
		await _fanout_with_current_route(snapshot)

	async def _drain() -> None:
		"""write queued events until the queue empties, then hand off.

		one event failing must not strand the rest, so each is logged and the
		drain continues; the re-spawn on exit closes the race where a producer
		enqueues just as this task decides it is done.
		"""
		nonlocal drain_task
		try:
			while True:
				try:
					snapshot = queue.get_nowait()
				except asyncio.QueueEmpty:
					return
				try:
					await _persist_and_fanout(snapshot)
				except Exception:
					logger.exception(
						"event persistence or fanout failed",
						extra={
							"event_id": str(snapshot.id),
							"event_type": snapshot.type,
						},
					)
				finally:
					queue.task_done()
		finally:
			async with drain_lock:
				drain_task = None
				if not queue.empty():
					drain_task = create_background_task(
						_drain(),
						name="event_persist_and_fanout",
					)

	async def emit(event: Event) -> None:
		"""queue one event for durable delivery, and start the drain if idle."""
		nonlocal drain_task
		if on_emit is not None:
			await on_emit()
		# ensure stable id for correlation
		if not event.id:
			event.id = TypeID(new_typeid("event"))

		snapshot = _copy_event(event)
		await queue.put(snapshot)
		async with drain_lock:
			if drain_task is None or drain_task.done():
				drain_task = create_background_task(
					_drain(),
					name="event_persist_and_fanout",
				)

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
	"""deliver to a resolved audience, or fall back to scope routing.

	an empty recipient list is not the same as no list: the first means the
	event resolved to nobody, the second that no resource governs it.
	"""
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
	await run_post_commit_actions_safely(session)

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
	require_permission(principal, ActionPermission.EVENTS_MANAGE)
	event = Event(**event_in.model_dump(exclude={"metadata"}))
	apply_metadata_write(event, event_in.metadata)
	return await persist_and_fanout_event(session, event=event)


async def list_events(
	session: AsyncSession,
	principal: Principal,
	filters: EventListFilters | None = None,
) -> list[Event]:
	"""query the event log as an operator.

	an operator surface, not a participant one: it reads across resources, so
	it is gated on the permission rather than on access to any one of them.
	participants read events through the message-anchored thread endpoint.
	"""
	require_permission(principal, ActionPermission.EVENTS_READ)
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
