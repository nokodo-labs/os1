"""Event routers."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import async_session_local, get_db
from api.logging import get_logger
from api.models.event import Event
from api.models.user import User
from api.schemas.event import Event as EventSchema
from api.schemas.event import EventCreate, EventListFilters
from api.v1.service.authentication import (
	Principal,
	authenticate_websocket_refresh_cookie,
	get_current_principal,
	is_websocket_origin_allowed,
)
from api.v1.service.collaborative_documents import (
	DocError,
	handle_awareness,
	handle_disconnect,
	handle_join,
	handle_leave,
	handle_update,
)
from api.v1.service.events import (
	create_event_from_request,
	event_connections,
)
from api.v1.service.events import (
	list_events as list_events_service,
)
from api.v1.service.runs import get_active_runs_signal
from api.v1.service.threads import handle_typing_event
from api.v1.service.users import (
	is_user_active,
	mark_user_active,
	mark_user_inactive,
	touch_user_activity,
)
from nokodo_ai.utils.typeid import TypeID, new_typeid


router = APIRouter(prefix="/events", tags=["events"])

logger = get_logger(__name__)


@router.post("", response_model=EventSchema, status_code=201)
async def create_event(
	event_in: EventCreate,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> Event:
	"""Persist and broadcast an event."""
	return await create_event_from_request(
		event_in,
		db,
		principal=principal,
	)


@router.get("", response_model=list[EventSchema])
async def list_events(
	filters: Annotated[EventListFilters, Depends()],
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[Event]:
	"""Query events with flexible filters."""
	return await list_events_service(
		db,
		principal=principal,
		filters=filters,
	)


@router.websocket("/stream")
async def events_stream(websocket: WebSocket) -> None:
	"""WebSocket endpoint for real-time event streaming.

	authentication: uses httpOnly refresh_token cookie (auto-sent by browser).
	csrf protection: validates Origin header against allowed origins.
	"""
	if not is_websocket_origin_allowed(websocket):
		await websocket.close(code=4003, reason="origin not allowed")
		return

	user = await authenticate_websocket_refresh_cookie(websocket)
	if user is None:
		await websocket.close(code=4001, reason="unauthorized")
		return

	user_id = user.id

	# reuse the per-tab session ID the client already generates (sent as
	# X-Session-ID on HTTP requests). this keeps one identity per browser tab
	# across both HTTP and WS. fall back to a server-generated ID if missing.
	client_sid = websocket.query_params.get("session_id")
	ws_session_id = client_sid if client_sid else str(new_typeid("ws"))

	await event_connections.connect(user_id, websocket)
	await mark_user_active(user_id)
	await websocket.send_json(
		{
			"type": "stream.connected",
			"user_id": user_id,
			"session_id": ws_session_id,
		}
	)

	# send active runs signal so the client knows which runs to resume
	try:
		signal = await get_active_runs_signal(user_id)
		await websocket.send_json(signal)
	except Exception:
		logger.debug("failed to send active runs signal for user %s", user_id)

	try:
		while True:
			data = await websocket.receive_json()
			msg_type = data.get("type")
			if msg_type == "ping":
				await touch_user_activity(user_id)
				await websocket.send_json({"type": "stream.pong"})
			elif msg_type in ("typing.start", "typing.stop"):
				thread_id_raw = data.get("thread_id")
				if not thread_id_raw:
					continue
				# delegate to threads service (participant-scoped broadcast)
				async with async_session_local() as db_session:
					await handle_typing_event(
						session=db_session,
						user_id=user_id,
						thread_id=TypeID(str(thread_id_raw)),
						typing=msg_type == "typing.start",
					)

			# --- collaborative editing (doc.*) ---
			elif msg_type == "doc.join":
				document_id = data.get("document_id")
				if not document_id:
					continue
				result = await handle_join(document_id, user, user_id, ws_session_id)
				if isinstance(result, DocError):
					await websocket.send_json(
						{
							"type": "doc.error",
							"document_id": document_id,
							"error": result.error,
						}
					)
					continue
				await websocket.send_json(
					{
						"type": "doc.state",
						"document_id": document_id,
						"session_id": ws_session_id,
						"state": result.state_b64,
						"participants": result.participants,
					}
				)
			elif msg_type == "doc.leave":
				document_id = data.get("document_id")
				if not document_id:
					continue
				await handle_leave(document_id, user_id, ws_session_id)
			elif msg_type == "doc.update":
				document_id = data.get("document_id")
				update_b64 = data.get("update")
				if not document_id or not update_b64:
					continue
				await handle_update(document_id, update_b64, ws_session_id)
			elif msg_type == "doc.awareness":
				document_id = data.get("document_id")
				awareness_data = data.get("data")
				if not document_id or not awareness_data:
					continue
				await handle_awareness(
					document_id,
					awareness_data,
					user_id,
					ws_session_id,
				)
	except WebSocketDisconnect:
		logger.debug("websocket disconnected for user %s", user_id)
	except Exception:
		logger.debug("websocket error for user %s", user_id, exc_info=True)
	finally:
		# clean up document sessions
		await handle_disconnect(user_id, ws_session_id)
		await event_connections.disconnect(user_id, websocket)
		last_seen = await mark_user_inactive(user_id)
		# persist last_active_at to DB when user fully disconnects
		if not await is_user_active(user_id):
			try:
				async with async_session_local() as db_session:
					await db_session.execute(
						update(User)
						.where(User.id == user_id)
						.values(last_active_at=last_seen)
					)
					await db_session.commit()
			except Exception:
				logger.debug("failed to persist last_active_at for user %s", user_id)
