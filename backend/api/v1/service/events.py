"""event service helpers.

this module centralizes event persistence + websocket broadcasting.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import TYPE_CHECKING, Annotated, Any

from fastapi import Header, HTTPException, WebSocket, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.database import AsyncSessionLocal
from api.models.event import Event, EventScope
from api.schemas.event import EventCreate
from api.v1.service.auth import Principal
from api.v1.service.authorization import require_permission
from nokodo_ai.utils.typeid import TypeID, new_typeid


logger = logging.getLogger(__name__)

# shared annotated type — add to any router param that mutates resources.
# FastAPI maps the parameter name x_session_id → header X-Session-ID.
SessionId = Annotated[str | None, Header()]


if TYPE_CHECKING:
	from api.models.event import Event as EventModel


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
		event_data: dict[str, Any] = {
			"id": str(event.id),
			"type": event.type,
			"scope": (
				event.scope.value if hasattr(event.scope, "value") else event.scope
			),
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
	"""

	def _track(name: str, task: asyncio.Task[object]) -> None:
		def _log_result(done: asyncio.Task[object]) -> None:
			try:
				done.result()
			except Exception:
				logger.exception("background task failed: %s", name)

		task.add_done_callback(_log_result)

	async def emit(event: Event) -> None:
		# ensure stable id for correlation
		if not event.id:
			event.id = TypeID(new_typeid("event"))

		# attach message correlation if available
		if event.message_id is None and message_id_provider:
			msg_id = message_id_provider()
			if msg_id:
				event.message_id = msg_id

		# broadcast immediately
		_track(
			"event_broadcast",
			asyncio.create_task(event_connections.broadcast_event(event)),
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

		_track("event_persist", asyncio.create_task(_persist()))

	return emit


async def publish_event(
	session: AsyncSession,
	*,
	event: Event,
	origin_session_id: str | None = None,
) -> Event:
	"""persist an event and broadcast it."""
	session.add(event)
	await session.commit()
	await session.refresh(event)
	await event_connections.broadcast_event(event, origin_session_id=origin_session_id)
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
