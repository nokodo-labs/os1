"""Agent endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.core.database import get_db
from api.models.agent import Agent
from api.models.model import Model
from api.schemas.agent import Agent as AgentSchema
from api.schemas.agent import AgentCreate


router = APIRouter(prefix="/agents", tags=["agents"])


async def _get_agent(agent_id: str, db: AsyncSession) -> Agent:
	stmt = select(Agent).options(selectinload(Agent.model)).where(Agent.id == agent_id)
	result = await db.execute(stmt)
	agent = result.scalars().one_or_none()
	if not agent:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Agent not found",
		)
	return agent


async def _ensure_model(model_id: str | None, db: AsyncSession) -> None:
	if not model_id:
		return
	model = await db.get(Model, model_id)
	if not model:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Model not found",
		)


@router.post("", response_model=AgentSchema, status_code=status.HTTP_201_CREATED)
async def create_agent(
	agent_in: AgentCreate,
	db: AsyncSession = Depends(get_db),
) -> Agent:
	"""Register a new agent."""
	await _ensure_model(agent_in.model_id, db)
	agent = Agent(**agent_in.model_dump(by_alias=True))
	db.add(agent)
	await db.commit()
	return await _get_agent(agent.id, db)


@router.get("", response_model=list[AgentSchema])
async def list_agents(
	db: AsyncSession = Depends(get_db),
) -> list[Agent]:
	"""List all agents."""
	stmt = (
		select(Agent)
		.options(selectinload(Agent.model))
		.order_by(Agent.created_at.desc())
	)
	result = await db.execute(stmt)
	return list(result.scalars().all())


@router.get("/{agent_id}", response_model=AgentSchema)
async def get_agent(
	agent_id: str,
	db: AsyncSession = Depends(get_db),
) -> Agent:
	"""Fetch an agent."""
	return await _get_agent(agent_id, db)
