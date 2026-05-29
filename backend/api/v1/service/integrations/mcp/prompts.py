"""MCP prompt projection and expansion helpers."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.mcp import MCPClient, MCPError
from api.models.mcp import MCPServer, MCPServerScope
from api.schemas.mcp import MCPDiscoveredPrompt, MCPSurfaceConfig
from api.schemas.prompt import Prompt as PromptOut
from api.settings import settings
from api.v1.service.integrations.mcp.cache import (
	CachedMCPPromptRef,
	get_cached_mcp_prompt_refs,
	set_cached_mcp_prompt_refs,
)
from api.v1.service.integrations.mcp.service import client_config
from api.v1.service.prompts.external import ExternalPromptSource


MCP_PROMPT_COMMAND_PREFIX = "mcp-"


def mcp_external_prompt_source() -> ExternalPromptSource:
	"""return the MCP implementation of the external prompt source boundary."""
	return ExternalPromptSource(
		name="mcp",
		prefix=MCP_PROMPT_COMMAND_PREFIX,
		load_placeholders=load_prompt_placeholders,
		render_content_map=render_prompt_content_map,
		list_prompts=list_prompt_catalog,
		get_prompt=get_prompt_catalog,
	)


async def load_prompt_placeholders(session: AsyncSession) -> dict[str, str]:
	"""return prompt-map placeholders for auto-expandable MCP prompts."""
	return {command: "" for command in await _list_prompt_refs(session)}


async def render_prompt_content_map(
	session: AsyncSession,
	commands: set[str],
) -> dict[str, str]:
	"""render selected no-argument MCP prompts for prompt expansion."""
	if not any(command.startswith(MCP_PROMPT_COMMAND_PREFIX) for command in commands):
		return {}
	refs = await _list_prompt_refs(session)
	matched_refs = [ref for command in commands if (ref := refs.get(command))]
	if not matched_refs:
		return {}
	servers = await _load_prompt_servers(
		{ref.server_id for ref in matched_refs},
		session,
	)
	rendered: dict[str, str] = {}
	refs_by_server: dict[str, list[CachedMCPPromptRef]] = {}
	for ref in matched_refs:
		refs_by_server.setdefault(ref.server_id, []).append(ref)
	for server_id, server_refs in refs_by_server.items():
		server = servers.get(server_id)
		if server is None:
			continue
		try:
			async with MCPClient(client_config(server)) as client:
				for ref in server_refs:
					try:
						result = await client.get_prompt(ref.name)
					except (MCPError, OSError, TimeoutError, ValueError):
						continue
					rendered[ref.command] = result.text
		except (MCPError, OSError, TimeoutError, ValueError):
			continue
	return rendered


async def list_prompt_catalog(session: AsyncSession) -> list[PromptOut]:
	"""list MCP prompts as external prompt catalog items."""
	refs = await _list_prompt_refs(session)
	now = datetime.now(UTC)
	return [
		PromptOut(
			id=ref.command,
			command=ref.command,
			content="",
			source="external",
			created_at=now,
			updated_at=now,
		)
		for ref in refs.values()
	]


async def get_prompt_catalog(
	prompt_id: str,
	session: AsyncSession,
) -> PromptOut | None:
	"""return one MCP prompt catalog item by stable command id."""
	refs = await _list_prompt_refs(session)
	if prompt_id not in refs:
		return None
	rendered = await render_prompt_content_map(session, {prompt_id})
	now = datetime.now(UTC)
	return PromptOut(
		id=prompt_id,
		command=prompt_id,
		content=rendered.get(prompt_id, ""),
		source="external",
		created_at=now,
		updated_at=now,
	)


async def _list_prompt_refs(session: AsyncSession) -> dict[str, CachedMCPPromptRef]:
	"""list no-argument MCP prompt references, preferring Redis cache."""
	if not settings.integrations.mcp.enabled:
		return {}
	cached = await get_cached_mcp_prompt_refs(session)
	if cached is not None:
		return cached
	result = await session.execute(
		select(MCPServer)
		.where(
			MCPServer.scope == MCPServerScope.GLOBAL,
			MCPServer.enabled.is_(True),
		)
		.order_by(MCPServer.name)
	)
	refs: dict[str, CachedMCPPromptRef] = {}
	for server in result.scalars().all():
		if not MCPSurfaceConfig.model_validate(server.capabilities or {}).prompts:
			continue
		for prompt in _server_prompts(server):
			if not prompt.enabled or prompt.requires_arguments:
				continue
			refs[prompt.command] = CachedMCPPromptRef(
				server_id=str(server.id),
				name=prompt.name,
				command=prompt.command,
			)
	await set_cached_mcp_prompt_refs(session, refs)
	return refs


async def _load_prompt_servers(
	server_ids: set[str],
	session: AsyncSession,
) -> dict[str, MCPServer]:
	"""load enabled MCP server rows needed to render matched prompt refs."""
	result = await session.execute(
		select(MCPServer).where(
			MCPServer.scope == MCPServerScope.GLOBAL,
			MCPServer.enabled.is_(True),
			MCPServer.id.in_(server_ids),
		)
	)
	return {str(server.id): server for server in result.scalars().all()}


def _server_prompts(server: MCPServer) -> list[MCPDiscoveredPrompt]:
	"""return discovered prompt snapshots for an MCP server row."""
	return [
		MCPDiscoveredPrompt.model_validate(item)
		for item in (server.discovered_prompts or [])
	]
