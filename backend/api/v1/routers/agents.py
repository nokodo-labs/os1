"""Agent routers."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.database import get_db
from api.models.agent import Agent
from api.schemas.agent import Agent as AgentSchema
from api.schemas.agent import AgentCreate
from api.v1.service import agents as agent_service


router = APIRouter(prefix="/agents", tags=["agents"])


@router.post("", response_model=AgentSchema, status_code=status.HTTP_201_CREATED)
async def create_agent(
	agent_in: AgentCreate,
	db: AsyncSession = Depends(get_db),
) -> Agent:
	"""Register a new agent."""
	return await agent_service.create_agent(agent_in, db)


@router.get("", response_model=list[AgentSchema])
async def list_agents(
	db: AsyncSession = Depends(get_db),
) -> list[Agent]:
	"""List all agents."""
	return await agent_service.list_agents(db)


@router.get("/{agent_id}", response_model=AgentSchema)
async def get_agent(
	agent_id: str,
	db: AsyncSession = Depends(get_db),
) -> Agent:
	"""Fetch an agent."""
	return await agent_service.get_agent(agent_id, db)
