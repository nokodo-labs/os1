"""MCP server list-change notification listeners."""

from __future__ import annotations

import asyncio
import contextlib
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import async_session_local
from api.local_tasks import create_background_task
from api.mcp import MCPClient, MCPDependencyError, MCPError, MCPListChangedEvent
from api.models.mcp import MCPServer, MCPServerScope
from api.settings import settings
from api.v1.service.integrations.mcp.service import (
	client_config,
	discover_server_unchecked,
)


logger = logging.getLogger(__name__)

_INITIAL_RECONNECT_DELAY_SECONDS = 1.0


async def start_mcp_list_change_listeners() -> list[asyncio.Task[None]]:
	"""start list-change listeners for enabled global MCP servers."""
	if not _listeners_enabled():
		return []
	async with async_session_local() as session:
		server_ids = await _list_listenable_server_ids(session)
	return [
		create_background_task(
			listen_for_server_list_changes(server_id),
			name=f"mcp-list-change-listener-{server_id}",
		)
		for server_id in server_ids
	]


async def stop_mcp_list_change_listeners(tasks: list[asyncio.Task[None]]) -> None:
	"""cancel active MCP list-change listener tasks."""
	for task in tasks:
		task.cancel()
	if tasks:
		await asyncio.gather(*tasks, return_exceptions=True)


async def listen_for_server_list_changes(server_id: str) -> None:
	"""keep one MCP server notification session alive until cancelled."""
	delay = _INITIAL_RECONNECT_DELAY_SECONDS
	while True:
		try:
			should_retry = await _listen_once(server_id)
		except asyncio.CancelledError:
			raise
		except (MCPDependencyError, MCPError, OSError, TimeoutError, ValueError) as exc:
			logger.warning("MCP list-change listener failed for %s: %s", server_id, exc)
			should_retry = True
		if not should_retry:
			return
		await asyncio.sleep(delay)
		delay = min(
			delay * 2,
			float(settings.integrations.mcp.list_change_reconnect_max_delay_seconds),
		)


async def _listen_once(server_id: str) -> bool:
	"""open one MCP notification session; return whether to reconnect."""
	async with async_session_local() as session:
		server = await _get_listenable_server(session, server_id)
	if server is None:
		return False

	done_event = asyncio.Event()
	refresher = _ServerRefreshDebouncer(server_id, done_event)

	try:
		async with MCPClient(client_config(server), receive_events=True) as client:
			consumer_task = asyncio.create_task(
				_consume_server_events(client, refresher),
				name=f"mcp-list-change-consumer-{server_id}",
			)
			done_task = asyncio.create_task(
				done_event.wait(),
				name=f"mcp-list-change-done-{server_id}",
			)
			completed, pending = await asyncio.wait(
				[consumer_task, done_task],
				return_when=asyncio.FIRST_COMPLETED,
			)
			for task in pending:
				task.cancel()
			if pending:
				await asyncio.gather(*pending, return_exceptions=True)
			if consumer_task in completed:
				consumer_task.result()
	finally:
		await refresher.cancel()
	return True


async def _consume_server_events(
	client: MCPClient,
	refresher: _ServerRefreshDebouncer,
) -> None:
	"""consume normalized MCP server events and schedule refreshes."""
	async for event in client.events():
		if isinstance(event, MCPListChangedEvent):
			refresher.schedule()


class _ServerRefreshDebouncer:
	"""debounce repeated list-change notifications for one server."""

	def __init__(self, server_id: str, done_event: asyncio.Event) -> None:
		"""create a debouncer for one MCP server listener."""
		self._server_id = server_id
		self._done_event = done_event
		self._task: asyncio.Task[None] | None = None

	def schedule(self) -> None:
		"""schedule one debounced server snapshot refresh."""
		if self._task is not None and not self._task.done():
			return
		self._task = create_background_task(
			self._run(),
			name=f"mcp-list-change-refresh-{self._server_id}",
		)

	async def cancel(self) -> None:
		"""cancel any pending debounced refresh."""
		if self._task is None or self._task.done():
			return
		self._task.cancel()
		with contextlib.suppress(asyncio.CancelledError):
			await self._task

	async def _run(self) -> None:
		"""wait for the debounce window, then refresh the server snapshot."""
		debounce_seconds = float(settings.integrations.mcp.list_change_debounce_seconds)
		await asyncio.sleep(debounce_seconds)
		server_active = await _refresh_server_snapshot(self._server_id)
		if not server_active:
			self._done_event.set()


async def _refresh_server_snapshot(server_id: str) -> bool:
	"""refresh one server snapshot after an upstream list-change notification."""
	async with async_session_local() as session:
		server = await _get_listenable_server(session, server_id)
		if server is None:
			return False
		try:
			await discover_server_unchecked(server, session)
		except (MCPDependencyError, MCPError, OSError, ValueError) as exc:
			await session.commit()
			logger.warning("MCP list-change refresh failed for %s: %s", server_id, exc)
			return True
		except Exception:
			await session.rollback()
			raise
		await session.commit()
		return True


async def _list_listenable_server_ids(session: AsyncSession) -> list[str]:
	"""return enabled global server ids eligible for list-change listening."""
	result = await session.execute(
		select(MCPServer.id).where(
			MCPServer.scope == MCPServerScope.GLOBAL,
			MCPServer.enabled.is_(True),
		)
	)
	return [str(server_id) for server_id in result.scalars().all()]


async def _get_listenable_server(
	session: AsyncSession,
	server_id: str,
) -> MCPServer | None:
	"""load an enabled global MCP server for notification listening."""
	result = await session.execute(
		select(MCPServer).where(
			MCPServer.id == server_id,
			MCPServer.scope == MCPServerScope.GLOBAL,
			MCPServer.enabled.is_(True),
		)
	)
	return result.scalars().one_or_none()


def _listeners_enabled() -> bool:
	"""return whether MCP list-change listeners should run."""
	return (
		settings.integrations.mcp.enabled
		and settings.integrations.mcp.list_change_listening_enabled
	)
