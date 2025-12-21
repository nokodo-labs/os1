"""Service layer for agent operations."""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.models.agent import Agent, AgentVisibility
from api.models.model import Model
from api.schemas.agent import AgentCreate, AgentUpdate
from api.v1.service.auth import Principal
from api.v1.service.authorization import require_permission


async def _ensure_model(
	model_id: str | None,
	session: AsyncSession,
) -> None:
	if not model_id:
		return
	model = await session.get(Model, model_id)
	if not model:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Model not found",
		)


async def _get_agent(
	agent_id: str,
	session: AsyncSession,
	principal: Principal,
) -> Agent:
	stmt = (
		select(Agent)
		.options(selectinload(Agent.model))
		.where(Agent.id == agent_id)
	)
	if not principal.is_admin:
		stmt = stmt.where(Agent.visibility == AgentVisibility.PUBLIC)
	result = await session.execute(stmt)
	agent = result.scalars().one_or_none()
	if not agent:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Agent not found",
		)
	return agent


async def create_agent(
	agent_in: AgentCreate,
	session: AsyncSession,
	*,
	principal: Principal,
) -> Agent:
	require_permission(principal, "agents:manage")
	await _ensure_model(agent_in.model_id, session)
	agent = Agent(**agent_in.model_dump(by_alias=True))
	session.add(agent)
	await session.commit()
	return await _get_agent(agent.id, session, principal)


async def list_agents(session: AsyncSession, *, principal: Principal) -> list[Agent]:
	stmt = select(Agent).options(selectinload(Agent.model))
	if not principal.is_admin:
		stmt = stmt.where(Agent.visibility == AgentVisibility.PUBLIC)
	stmt = stmt.order_by(Agent.created_at.desc())
	result = await session.execute(stmt)
	return list(result.scalars().all())


async def get_agent(
	agent_id: str,
	session: AsyncSession,
	*,
	principal: Principal,
) -> Agent:
	return await _get_agent(agent_id, session, principal)


async def update_agent(
	agent_id: str,
	agent_in: AgentUpdate,
	session: AsyncSession,
	*,
	principal: Principal,
) -> Agent:
	require_permission(principal, "agents:manage")
	agent = await _get_agent(agent_id, session, principal)
	if agent_in.model_id is not None:
		await _ensure_model(agent_in.model_id, session)

	update_data = agent_in.model_dump(exclude_unset=True)
	for field, value in update_data.items():
		setattr(agent, field, value)

	session.add(agent)
	await session.commit()
	return await _get_agent(agent.id, session, principal)


async def delete_agent(
	agent_id: str,
	session: AsyncSession,
	*,
	principal: Principal,
) -> None:
	require_permission(principal, "agents:manage")
	agent = await _get_agent(agent_id, session, principal)
	await session.delete(agent)
	await session.commit()
