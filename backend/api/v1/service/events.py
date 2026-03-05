"""event service helpers.

this module centralizes event persistence + websocket broadcasting.

resource events (note.*, thread.*, file.*, etc.) are automatically routed
to all users with at least READER access to the affected resource.
non-resource events (settings.*, user.*, stream.*) fall back to
owner-only or broadcast routing.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable, Coroutine
from datetime import datetime
from typing import TYPE_CHECKING, Annotated, Any

from fastapi import Header, HTTPException, WebSocket, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import AsyncSessionLocal
from api.models.event import Event, EventScope
from api.models.event_types import EventType
from api.permissions import ResourceType
from api.schemas.event import EventCreate
from api.tasks import create_background_task
from api.v1.service.auth import Principal
from api.v1.service.authorization import list_accessible_user_ids, require_permission
from nokodo_ai.utils.typeid import TypeID, new_typeid


logger = logging.getLogger(__name__)

# shared annotated type - add to any router param that mutates resources.
# FastAPI maps the parameter name x_session_id -> header X-Session-ID.
SessionId = Annotated[str | None, Header()]


if TYPE_CHECKING:
	from api.models.event import Event as EventModel


# --- access-based event routing ---
# maps event types to the resource type + data-key that holds the resource ID.
# events not listed here fall back to owner-only or broadcast routing.

_EVENT_ROUTING: dict[str, tuple[ResourceType, str]] = {
	# note events
	EventType.NOTE_CREATED: (ResourceType.NOTE, "id"),
	EventType.NOTE_UPDATED: (ResourceType.NOTE, "id"),
	EventType.NOTE_DELETED: (ResourceType.NOTE, "id"),
	# thread events
	EventType.THREAD_CREATED: (ResourceType.THREAD, "id"),
	EventType.THREAD_UPDATED: (ResourceType.THREAD, "id"),
	EventType.THREAD_DELETED: (ResourceType.THREAD, "id"),
	# message events (route via parent thread)
	EventType.MESSAGE_CREATED: (ResourceType.THREAD, "thread_id"),
	EventType.MESSAGE_UPDATED: (ResourceType.THREAD, "thread_id"),
	EventType.MESSAGE_DELETED: (ResourceType.THREAD, "thread_id"),
	# file events
	EventType.FILE_CREATED: (ResourceType.FILE, "id"),
	EventType.FILE_UPDATED: (ResourceType.FILE, "id"),
	EventType.FILE_DELETED: (ResourceType.FILE, "id"),
	EventType.FILE_PROCESSING: (ResourceType.FILE, "id"),
	EventType.FILE_READY: (ResourceType.FILE, "id"),
	# agent events
	EventType.AGENT_CREATED: (ResourceType.AGENT, "id"),
	EventType.AGENT_UPDATED: (ResourceType.AGENT, "id"),
	EventType.AGENT_DELETED: (ResourceType.AGENT, "id"),
	# project events
	EventType.PROJECT_CREATED: (ResourceType.PROJECT, "id"),
	EventType.PROJECT_UPDATED: (ResourceType.PROJECT, "id"),
	EventType.PROJECT_DELETED: (ResourceType.PROJECT, "id"),
	# memory events
	EventType.MEMORY_CREATED: (ResourceType.MEMORY, "id"),
	EventType.MEMORY_UPDATED: (ResourceType.MEMORY, "id"),
	EventType.MEMORY_DELETED: (ResourceType.MEMORY, "id"),
	# reminder list events
	EventType.REMINDER_LIST_CREATED: (ResourceType.REMINDER_LIST, "id"),
	EventType.REMINDER_LIST_UPDATED: (ResourceType.REMINDER_LIST, "id"),
	EventType.REMINDER_LIST_DELETED: (ResourceType.REMINDER_LIST, "id"),
	# reminder events (route via parent list)
	EventType.REMINDER_CREATED: (ResourceType.REMINDER_LIST, "list_id"),
	EventType.REMINDER_UPDATED: (ResourceType.REMINDER_LIST, "list_id"),
	EventType.REMINDER_COMPLETED: (ResourceType.REMINDER_LIST, "list_id"),
	EventType.REMINDER_DELETED: (ResourceType.REMINDER_LIST, "list_id"),
	# group events
	EventType.GROUP_CREATED: (ResourceType.GROUP, "id"),
	EventType.GROUP_UPDATED: (ResourceType.GROUP, "id"),
	EventType.GROUP_DELETED: (ResourceType.GROUP, "id"),
	EventType.GROUP_MEMBER_ADDED: (ResourceType.GROUP, "group_id"),
	EventType.GROUP_MEMBER_REMOVED: (ResourceType.GROUP, "group_id"),
	# run events (route via thread)
	EventType.RUN_STARTED: (ResourceType.THREAD, "thread_id"),
	EventType.RUN_COMPLETED: (ResourceType.THREAD, "thread_id"),
	# tool events (route via thread)
	EventType.TOOL_PROGRESS: (ResourceType.THREAD, "thread_id"),
	EventType.TOOL_CUSTOM: (ResourceType.THREAD, "thread_id"),
	EventType.TOOL_NOTIFICATION: (ResourceType.THREAD, "thread_id"),
}


def _resolve_routing(event: Event) -> tuple[ResourceType, str] | None:
	"""resolve the resource type and ID for access-based fan-out.

	returns None for events that should use the legacy routing path
	(owner-only or broadcast).
	"""
	config = _EVENT_ROUTING.get(event.type)
	if not config:
		return None
	resource_type, data_key = config
	# extract resource ID from event data
	resource_id: str | None = None
	if event.data and data_key in event.data:
		resource_id = str(event.data[data_key])
	# fallback: thread-scoped resources can use event.thread_id
	if not resource_id and resource_type == ResourceType.THREAD and event.thread_id:
		resource_id = str(event.thread_id)
	if not resource_id:
		return None
	return (resource_type, resource_id)


def _build_event_data(
	event: EventModel,
	origin_session_id: str | None = None,
) -> dict[str, Any]:
	"""serialize an event model into a JSON-safe dict for WS transmission."""
	return {
		"id": str(event.id),
		"type": event.type,
		"scope": (event.scope.value if hasattr(event.scope, "value") else event.scope),
		"scope_id": str(event.scope_id) if event.scope_id else None,
		"data": event.data,
		"version": event.version,
		"user_id": str(event.user_id) if event.user_id else None,
		"thread_id": str(event.thread_id) if event.thread_id else None,
		"message_id": str(event.message_id) if event.message_id else None,
		"task_id": str(event.task_id) if event.task_id else None,
		"project_id": str(event.project_id) if event.project_id else None,
		"created_at": event.created_at.isoformat() if event.created_at else None,
		"origin_session_id": origin_session_id,
	}


async def _resolve_recipient_ids(
	event: Event,
) -> list[str] | None:
	"""resolve all user IDs that should receive this event.

	uses a fresh read-only session so pending deletes in the caller's
	transaction don't hide the resource row.
	returns None when the event has no resource routing (fall back to legacy).
	"""
	routing = _resolve_routing(event)
	if not routing:
		return None
	resource_type, resource_id = routing
	async with AsyncSessionLocal() as session:
		return await list_accessible_user_ids(resource_type, resource_id, session)


class ConnectionManager:
	"""Manages active WebSocket connections per user for event broadcasting."""

	def __init__(self) -> None:
		self._connections: dict[str, set[WebSocket]] = defaultdict(set)
		self._lock = asyncio.Lock()

	async def connect(self, user_id: str, websocket: WebSocket) -> None:
		await websocket.accept()
		async with self._lock:
			self._connections[user_id].add(websocket)
		logger.debug("websocket connected for user %s", user_id)

	async def disconnect(self, user_id: str, websocket: WebSocket) -> None:
		async with self._lock:
			self._connections[user_id].discard(websocket)
			if not self._connections[user_id]:
				del self._connections[user_id]
		logger.debug("websocket disconnected for user %s", user_id)

	async def send_to_user(self, user_id: str, data: dict[str, Any]) -> None:
		async with self._lock:
			connections = list(self._connections.get(user_id, []))

		for websocket in connections:
			try:
				await websocket.send_json(data)
			except Exception:
				logger.debug("failed to send to websocket for user %s", user_id)

	async def send_to_users(
		self,
		user_ids: list[str],
		data: dict[str, Any],
		*,
		exclude_user_id: str | None = None,
	) -> None:
		"""send to all sessions of multiple users concurrently."""
		targets = (uid for uid in user_ids if uid != exclude_user_id)
		await asyncio.gather(*(self.send_to_user(uid, data) for uid in targets))

	async def broadcast(self, data: dict[str, Any]) -> None:
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

	async def broadcast_event(
		self,
		event: EventModel,
		*,
		origin_session_id: str | None = None,
	) -> None:
		"""legacy broadcast: owner-only or full broadcast.

		prefer publish_event() for persisted resource events (does access-based
		routing automatically). this method is kept for the emitter fast-path.
		"""
		event_data = _build_event_data(event, origin_session_id)
		if event.user_id:
			await self.send_to_user(str(event.user_id), event_data)
		else:
			await self.broadcast(event_data)


event_connections = ConnectionManager()

EventEmitter = Callable[[Event], Awaitable[None]]


def build_event_emitter(
	*,
	message_id_provider: Callable[[], str | None] | None = None,
	before_persist: Callable[[Event], Awaitable[None]] | None = None,
) -> EventEmitter:
	"""Create a non-blocking emitter that broadcasts immediately and persists async.

	This is the "core" behavior: tools/filters should never be able to emit events
	that vanish (no no-op emitter). Persistence happens in a separate session.

	recipient lists are resolved on first use per resource and cached for the
	lifetime of this emitter (a single agent run).
	"""
	_recipient_cache: dict[str, list[str]] = {}

	async def _broadcast_with_routing(event: Event) -> None:
		"""broadcast an event with access-based routing (cached per resource)."""
		event_data = _build_event_data(event)
		routing = _resolve_routing(event)
		if routing:
			resource_type, resource_id = routing
			cache_key = f"{resource_type.value}:{resource_id}"
			if cache_key not in _recipient_cache:
				async with AsyncSessionLocal() as read_session:
					_recipient_cache[cache_key] = await list_accessible_user_ids(
						resource_type,
						resource_id,
						read_session,
					)
			user_ids = _recipient_cache[cache_key]
			if user_ids:
				await event_connections.send_to_users(user_ids, event_data)
				return
		# fallback: owner-only or broadcast
		if event.user_id:
			await event_connections.send_to_user(str(event.user_id), event_data)
		else:
			await event_connections.broadcast(event_data)

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
				event.message_id = msg_id

		# broadcast immediately (with access-based routing)
		_track(
			"event_broadcast",
			_broadcast_with_routing(event),
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
				metadata_=event.metadata_,
			)
			async with AsyncSessionLocal() as bg_session:
				bg_session.add(copy)
				await bg_session.commit()

		_track("event_persist", _persist())

	return emit


async def publish_event(
	session: AsyncSession,
	*,
	event: Event,
	origin_session_id: str | None = None,
) -> Event:
	"""persist an event and broadcast to all users with access.

	recipient resolution uses a separate read-only session so that
	pending hard-deletes in the caller's transaction don't hide the
	resource row.
	"""
	# resolve recipients before commit (separate session)
	recipient_ids = await _resolve_recipient_ids(event)

	session.add(event)
	await session.commit()
	await session.refresh(event)

	event_data = _build_event_data(event, origin_session_id)

	if recipient_ids:
		await event_connections.send_to_users(recipient_ids, event_data)
	elif event.user_id:
		await event_connections.send_to_user(str(event.user_id), event_data)
	else:
		await event_connections.broadcast(event_data)

	return event


async def emit_event(
	event_in: EventCreate,
	session: AsyncSession,
	*,
	principal: Principal,
) -> Event:
	"""emit an event via the API."""
	require_permission(principal, "events:manage")
	if event_in.user_id is not None and not principal.is_admin:
		target_user_id = str(event_in.user_id)
		if target_user_id != principal.user_id:
			raise HTTPException(
				status_code=status.HTTP_403_FORBIDDEN,
				detail="forbidden",
			)
	event = Event(**event_in.model_dump(by_alias=True))
	return await publish_event(session, event=event)


async def list_events(
	session: AsyncSession,
	*,
	principal: Principal,
	scope: EventScope | None = None,
	thread_id: str | None = None,
	task_id: str | None = None,
	user_id: str | None = None,
	since: datetime | None = None,
) -> list[Event]:
	require_permission(principal, "events:manage")
	stmt = select(Event).order_by(Event.created_at.desc())

	if scope is not None:
		stmt = stmt.where(Event.scope == scope)
	if thread_id is not None:
		stmt = stmt.where(Event.thread_id == thread_id)
	if task_id is not None:
		stmt = stmt.where(Event.task_id == task_id)
	if user_id is not None:
		stmt = stmt.where(Event.user_id == user_id)
	if since is not None:
		stmt = stmt.where(Event.created_at >= since)

	result = await session.execute(stmt.limit(200))
	return list(result.scalars().all())
