"""MCP integration endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.models.mcp import MCPServer
from api.schemas.mcp import (
	MCPCapabilityType,
	MCPCapabilityUpdate,
	MCPDiscoveredCapabilities,
	MCPDiscoveryResult,
	MCPServerCreate,
	MCPServerUpdate,
)
from api.schemas.mcp import MCPServer as MCPServerSchema
from api.v1.service.authentication import Principal, get_current_principal
from api.v1.service.integrations.mcp import (
	create_server as create_server_service,
)
from api.v1.service.integrations.mcp import (
	delete_server as delete_server_service,
)
from api.v1.service.integrations.mcp import (
	discover_server as discover_server_service,
)
from api.v1.service.integrations.mcp import (
	get_server as get_server_service,
)
from api.v1.service.integrations.mcp import (
	list_capabilities as list_capabilities_service,
)
from api.v1.service.integrations.mcp import (
	list_servers as list_servers_service,
)
from api.v1.service.integrations.mcp import (
	update_capability as update_capability_service,
)
from api.v1.service.integrations.mcp import (
	update_server as update_server_service,
)
from nokodo_ai.utils.typeid import TypeID


router = APIRouter(prefix="/mcp", tags=["integrations: MCP"])


@router.get("/servers", response_model=list[MCPServerSchema])
async def list_servers(
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[MCPServer]:
	"""list global MCP servers."""
	return await list_servers_service(db, principal=principal)


@router.post(
	"/servers", response_model=MCPServerSchema, status_code=status.HTTP_201_CREATED
)
async def create_server(
	server_in: MCPServerCreate,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> MCPServer:
	"""create a global MCP server."""
	return await create_server_service(server_in, db, principal=principal)


@router.get("/servers/{server_id}", response_model=MCPServerSchema)
async def get_server(
	server_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> MCPServer:
	"""get a global MCP server."""
	return await get_server_service(server_id, db, principal=principal)


@router.patch("/servers/{server_id}", response_model=MCPServerSchema)
async def update_server(
	server_id: TypeID,
	server_in: MCPServerUpdate,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> MCPServer:
	"""update a global MCP server."""
	return await update_server_service(server_id, server_in, db, principal=principal)


@router.delete("/servers/{server_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_server(
	server_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> None:
	"""delete a global MCP server."""
	await delete_server_service(server_id, db, principal=principal)


@router.post("/servers/{server_id}/discover", response_model=MCPDiscoveryResult)
async def discover_server(
	server_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> MCPDiscoveryResult:
	"""refresh cached capabilities for a global MCP server."""
	return await discover_server_service(server_id, db, principal=principal)


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
	return await list_capabilities_service(server_id, db, principal=principal)


@router.patch(
	"/servers/{server_id}/capabilities/{capability_type}/{capability_id}",
	response_model=MCPServerSchema,
)
async def update_capability(
	server_id: TypeID,
	capability_type: MCPCapabilityType,
	capability_id: TypeID,
	capability_in: MCPCapabilityUpdate,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> MCPServer:
	"""update a discovered MCP capability snapshot."""
	return await update_capability_service(
		server_id,
		capability_type,
		capability_id,
		capability_in,
		db,
		principal=principal,
	)
