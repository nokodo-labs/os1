"""WebSocket endpoint for real-time event streaming."""

from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from api.core.database import AsyncSessionLocal
from api.core.logging import get_logger
from api.models.user import User
from api.settings import settings
from api.v1.service.connection_manager import event_connections
from nokodo_ai.utils.security import decode_jwt_token


logger = get_logger(__name__)

router = APIRouter(prefix="/events", tags=["events"])


async def _authenticate_websocket(token: str | None) -> User | None:
	"""Authenticate a WebSocket connection using a JWT token."""
	if not token:
		return None

	try:
		payload = decode_jwt_token(
			token,
			secret_key=settings.security.secret_key,
			algorithms=[settings.security.jwt_algorithm],
		)
		user_id = payload.get("sub")
		if not user_id:
			return None
	except Exception:
		return None

	async with AsyncSessionLocal() as session:
		result = await session.execute(
			select(User).options(selectinload(User.role)).where(User.id == user_id)
		)
		user = result.scalar_one_or_none()

	if user and not user.is_active:
		return None

	return user


@router.websocket("/stream")
async def events_stream(websocket: WebSocket, token: str | None = None) -> None:
	"""WebSocket endpoint for real-time event streaming.

	Connect with: ws://host/v1/events/stream?token=<jwt>
	"""
	user = await _authenticate_websocket(token)

	if not user:
		await websocket.close(code=4001, reason="unauthorized")
		return

	user_id = str(user.id)

	await event_connections.connect(user_id, websocket)

	# Send initial connected message
	await websocket.send_json(
		{
			"type": "stream.connected",
			"user_id": user_id,
		}
	)

	try:
		while True:
			# Wait for incoming messages (ping/pong handling, future client events)
			data = await websocket.receive_json()

			# Handle ping messages
			if data.get("type") == "ping":
				await websocket.send_json({"type": "stream.pong"})

	except WebSocketDisconnect:
		logger.debug("websocket disconnected for user %s", user_id)
	except Exception as e:
		logger.debug("websocket error for user %s: %s", user_id, e)
	finally:
		await event_connections.disconnect(user_id, websocket)
