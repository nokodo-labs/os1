"""MCP lifecycle helpers."""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.mcp import MCPServer, MCPServerScope
from api.settings import settings
from api.v1.service.integrations.mcp.service import discover_server_unchecked


logger = logging.getLogger(__name__)


async def initialize_global_mcp_servers(session: AsyncSession) -> None:
	"""discover enabled global MCP servers during backend startup."""
	if (
		not settings.integrations.mcp.enabled
		or not settings.integrations.mcp.startup_discovery_enabled
	):
		return
	result = await session.execute(
		select(MCPServer).where(
			MCPServer.scope == MCPServerScope.GLOBAL,
			MCPServer.enabled.is_(True),
		)
	)
	servers = list(result.scalars().all())
	for server in servers:
		try:
			await discover_server_unchecked(server, session)
		except Exception as exc:
			logger.warning(
				"MCP server startup discovery failed for %s: %s", server.id, exc
			)
	await session.commit()
