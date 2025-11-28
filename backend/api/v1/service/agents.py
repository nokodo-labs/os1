"""Service layer for agent operations."""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.models.agent import Agent
from api.models.model import Model
from api.schemas.agent import AgentCreate


async def _ensure_model(model_id: str | None, session: AsyncSession) -> None:
	if not model_id:
		return
	model = await session.get(Model, model_id)
	if not model:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Model not found",
		)


async def _get_agent(agent_id: str, session: AsyncSession) -> Agent:
	stmt = select(Agent).options(selectinload(Agent.model)).where(Agent.id == agent_id)
	result = await session.execute(stmt)
	agent = result.scalars().one_or_none()
	if not agent:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Agent not found",
		)
	return agent


async def create_agent(agent_in: AgentCreate, session: AsyncSession) -> Agent:
	await _ensure_model(agent_in.model_id, session)
	agent = Agent(**agent_in.model_dump(by_alias=True))
	session.add(agent)
	await session.commit()
	return await _get_agent(agent.id, session)


async def list_agents(session: AsyncSession) -> list[Agent]:
	stmt = (
		select(Agent)
		.options(selectinload(Agent.model))
		.order_by(Agent.created_at.desc())
	)
	result = await session.execute(stmt)
	return list(result.scalars().all())


async def get_agent(agent_id: str, session: AsyncSession) -> Agent:
	return await _get_agent(agent_id, session)
