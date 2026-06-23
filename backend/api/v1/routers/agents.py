"""Agent routers."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.models.agent import Agent
from api.permissions import ResourceType
from api.schemas.agent import Agent as AgentSchema
from api.schemas.agent import AgentCreate, AgentListFilters, AgentSortBy, AgentUpdate
from api.schemas.sorting import SortDir
from api.v1.routers.resource_access import create_resource_access_router
from api.v1.service import agents as agent_service
from api.v1.service.auth import Principal, get_current_principal
from api.v1.service.events import SessionId
from nokodo_ai.utils.typeid import TypeID


router = APIRouter(prefix="/agents", tags=["agents"])
router.include_router(create_resource_access_router(ResourceType.AGENT, "agent_id"))


@router.post("", response_model=AgentSchema, status_code=status.HTTP_201_CREATED)
async def create_agent(
	agent_in: AgentCreate,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> Agent:
	"""Register a new agent."""
	return await agent_service.create_agent(
		agent_in,
		db,
		principal=principal,
		origin_session_id=x_session_id,
	)


@router.get("", response_model=list[AgentSchema])
async def list_agents(
	filters: Annotated[AgentListFilters, Depends()],
	skip: int = 0,
	limit: int = 100,
	sort_by: AgentSortBy = "created_at",
	sort_dir: SortDir = "desc",
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[Agent]:
	"""List all agents visible to the caller."""
	return await agent_service.list_agents(
		db,
		principal=principal,
		skip=skip,
		limit=limit,
		sort_by=sort_by,
		sort_dir=sort_dir,
		q=filters.q,
	)


@router.get("/count", response_model=int)
async def count_agents(
	filters: Annotated[AgentListFilters, Depends()],
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> int:
	"""Count agents matching the list filters."""
	return await agent_service.count_agents(db, principal=principal, q=filters.q)


@router.get("/{agent_id}", response_model=AgentSchema)
async def get_agent(
	agent_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> AgentSchema:
	"""Fetch an agent."""
	return await agent_service.get_agent_payload(agent_id, db, principal=principal)


@router.patch("/{agent_id}", response_model=AgentSchema)
async def update_agent(
	agent_id: TypeID,
	agent_in: AgentUpdate,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> Agent:
	"""Update an agent."""
	return await agent_service.update_agent(
		agent_id,
		agent_in,
		db,
		principal=principal,
		origin_session_id=x_session_id,
	)


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(
	agent_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> None:
	"""Delete an agent."""
	await agent_service.delete_agent(
		agent_id,
		db,
		principal=principal,
		origin_session_id=x_session_id,
	)
