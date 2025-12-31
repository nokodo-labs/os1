"""WebSocket connection manager for real-time event broadcasting."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import TYPE_CHECKING, Any

from fastapi import WebSocket

from api.core.logging import get_logger


if TYPE_CHECKING:
	from api.models.event import Event


logger = get_logger(__name__)


class ConnectionManager:
	"""Manages active WebSocket connections per user for event broadcasting."""

	def __init__(self) -> None:
		self._connections: dict[str, set[WebSocket]] = defaultdict(set)
		self._lock = asyncio.Lock()

	async def connect(self, user_id: str, websocket: WebSocket) -> None:
		"""Register a new WebSocket connection for a user."""
		await websocket.accept()
		async with self._lock:
			self._connections[user_id].add(websocket)
		logger.debug("websocket connected for user %s", user_id)

	async def disconnect(self, user_id: str, websocket: WebSocket) -> None:
		"""Unregister a WebSocket connection for a user."""
		async with self._lock:
			self._connections[user_id].discard(websocket)
			if not self._connections[user_id]:
				del self._connections[user_id]
		logger.debug("websocket disconnected for user %s", user_id)

	async def send_to_user(self, user_id: str, data: dict[str, Any]) -> None:
		"""Send a message to all connections for a specific user."""
		async with self._lock:
			connections = list(self._connections.get(user_id, []))

		for websocket in connections:
			try:
				await websocket.send_json(data)
			except Exception:
				logger.debug("failed to send to websocket for user %s", user_id)

	async def broadcast(self, data: dict[str, Any]) -> None:
		"""Broadcast a message to all connected users."""
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

	async def broadcast_event(self, event: Event) -> None:
		"""Broadcast an event to relevant users.

		If the event has a user_id, send only to that user.
		Otherwise, broadcast to all connected users.
		"""
		event_data = {
			"id": str(event.id),
			"type": event.type,
			"scope": event.scope.value
			if hasattr(event.scope, "value")
			else event.scope,
			"scope_id": str(event.scope_id) if event.scope_id else None,
			"data": event.data,
			"version": event.version,
			"user_id": str(event.user_id) if event.user_id else None,
			"thread_id": str(event.thread_id) if event.thread_id else None,
			"message_id": str(event.message_id) if event.message_id else None,
			"task_id": str(event.task_id) if event.task_id else None,
			"project_id": str(event.project_id) if event.project_id else None,
			"created_at": event.created_at.isoformat() if event.created_at else None,
		}

		if event.user_id:
			await self.send_to_user(str(event.user_id), event_data)
		else:
			await self.broadcast(event_data)


# Singleton instance for app-wide use
event_connections = ConnectionManager()
