"""MCP integration endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.models.mcp import MCPServer
from api.schemas.mcp import (
	MCPDiscoveredCapabilities,
	MCPDiscoveryResult,
	MCPServerCreate,
	MCPServerUpdate,
)
from api.schemas.mcp import MCPServer as MCPServerSchema
from api.v1.service.auth import Principal, get_current_principal
from api.v1.service.integrations import mcp as mcp_service
from nokodo_ai.utils.typeid import TypeID


router = APIRouter(prefix="/mcp", tags=["integrations: MCP"])


@router.get("/servers", response_model=list[MCPServerSchema])
async def list_servers(
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[MCPServer]:
	"""list global MCP servers."""
	return await mcp_service.list_servers(db, principal=principal)


@router.post(
	"/servers", response_model=MCPServerSchema, status_code=status.HTTP_201_CREATED
)
async def create_server(
	server_in: MCPServerCreate,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> MCPServer:
	"""create a global MCP server."""
	return await mcp_service.create_server(server_in, db, principal=principal)


@router.get("/servers/{server_id}", response_model=MCPServerSchema)
async def get_server(
	server_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> MCPServer:
	"""get a global MCP server."""
	return await mcp_service.get_server(server_id, db, principal=principal)


@router.patch("/servers/{server_id}", response_model=MCPServerSchema)
async def update_server(
	server_id: TypeID,
	server_in: MCPServerUpdate,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> MCPServer:
	"""update a global MCP server."""
	return await mcp_service.update_server(
		server_id, server_in, db, principal=principal
	)


@router.delete("/servers/{server_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_server(
	server_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> None:
	"""delete a global MCP server."""
	await mcp_service.delete_server(server_id, db, principal=principal)


@router.post("/servers/{server_id}/discover", response_model=MCPDiscoveryResult)
async def discover_server(
	server_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> MCPDiscoveryResult:
	"""refresh cached capabilities for a global MCP server."""
	return await mcp_service.discover_server(server_id, db, principal=principal)


@router.get(
	"/servers/{server_id}/capabilities",
	response_model=MCPDiscoveredCapabilities,
)
async def list_capabilities(
	server_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> MCPDiscoveredCapabilities:
	"""list cached capabilities for a global MCP server."""
	return await mcp_service.list_capabilities(server_id, db, principal=principal)
