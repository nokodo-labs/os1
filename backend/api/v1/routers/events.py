"""Event routers."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.database import AsyncSessionLocal, get_db
from api.core.logging import get_logger
from api.models.event import Event, EventScope
from api.schemas.event import Event as EventSchema
from api.schemas.event import EventCreate
from api.v1.service import auth as auth_service
from api.v1.service import events as event_service
from api.v1.service import threads as thread_service
from api.v1.service.auth import Principal, get_current_principal
from api.v1.service.chat.run_status import get_active_runs_signal
from nokodo_ai.utils.typeid import TypeID


router = APIRouter(prefix="/events", tags=["events"])

logger = get_logger(__name__)


@router.post("", response_model=EventSchema, status_code=201)
async def emit_event(
	event_in: EventCreate,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> Event:
	"""Persist and broadcast an event."""
	return await event_service.emit_event(event_in, db, principal=principal)


@router.get("", response_model=list[EventSchema])
async def list_events(
	scope: EventScope | None = None,
	thread_id: TypeID | None = None,
	task_id: TypeID | None = None,
	user_id: TypeID | None = None,
	since: datetime | None = None,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[Event]:
	"""Query events with flexible filters."""
	return await event_service.list_events(
		db,
		principal=principal,
		scope=scope,
		thread_id=thread_id,
		task_id=task_id,
		user_id=user_id,
		since=since,
	)


@router.websocket("/stream")
async def events_stream(websocket: WebSocket) -> None:
	"""WebSocket endpoint for real-time event streaming.

	authentication: uses httpOnly refresh_token cookie (auto-sent by browser).
	csrf protection: validates Origin header against allowed origins.
	"""
	if not auth_service.is_websocket_origin_allowed(websocket):
		await websocket.close(code=4003, reason="origin not allowed")
		return

	user = await auth_service.authenticate_websocket_refresh_cookie(websocket)
	if user is None:
		await websocket.close(code=4001, reason="unauthorized")
		return

	user_id = str(user.id)

	await event_service.event_connections.connect(user_id, websocket)
	await websocket.send_json({"type": "stream.connected", "user_id": user_id})

	# send active runs signal so the client knows which runs to resume
	try:
		signal = await get_active_runs_signal(user_id)
		if signal is not None:
			await websocket.send_json(signal)
	except Exception:
		logger.debug("failed to send active runs signal for user %s", user_id)

	try:
		while True:
			data = await websocket.receive_json()
			msg_type = data.get("type")
			if msg_type == "ping":
				await websocket.send_json({"type": "stream.pong"})
			elif msg_type in ("typing.start", "typing.stop"):
				thread_id = data.get("thread_id")
				if not thread_id:
					continue
				# delegate to threads service (participant-scoped broadcast)
				async with AsyncSessionLocal() as db_session:
					await thread_service.handle_typing_event(
						session=db_session,
						user_id=user_id,
						thread_id=thread_id,
						typing=msg_type == "typing.start",
					)
	except WebSocketDisconnect:
		logger.debug(f"websocket disconnected for user {user_id}")
	except Exception as e:
		logger.debug(f"websocket error for user {user_id}: {e}")
	finally:
		await event_service.event_connections.disconnect(user_id, websocket)
