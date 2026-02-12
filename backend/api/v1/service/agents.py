"""Service layer for agent operations."""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.agent import Agent
from api.models.model import Model
from api.permissions import ResourceType
from api.schemas.agent import AgentCreate, AgentUpdate
from api.v1.service.auth import Principal
from api.v1.service.authorization import (
	require_permission,
	require_resource_access,
	resource_access_predicate,
)
from nokodo_ai.utils.typeid import TypeID


def _can_manage(principal: Principal) -> bool:
	"""check if principal has agents:manage permission."""
	return principal.is_admin or principal.has_permission("agents:manage")


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
	agent_id: TypeID,
	session: AsyncSession,
) -> Agent:
	"""fetch an agent by id (no access check)."""
	stmt = select(Agent).where(Agent.id == agent_id)
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
	require_permission(principal, "agents:create")
	await _ensure_model(agent_in.model_id, session)
	agent = Agent(**agent_in.model_dump(by_alias=True))
	session.add(agent)
	await session.commit()
	return await _get_agent(TypeID(agent.id), session)


async def list_agents(
	session: AsyncSession,
	*,
	principal: Principal,
) -> list[Agent]:
	"""list agents visible to principal.

	managers see all agents. readers see only agents they have
	explicit access to via access rules.
	"""
	base = select(Agent).order_by(Agent.created_at.desc())

	if _can_manage(principal):
		result = await session.execute(base)
		return list(result.scalars().all())

	predicate = resource_access_predicate(principal, ResourceType.AGENT)
	result = await session.execute(base.where(predicate))
	return list(result.scalars().all())


async def get_agent(
	agent_id: TypeID,
	session: AsyncSession,
	*,
	principal: Principal,
) -> Agent:
	"""get a single agent."""
	if not _can_manage(principal):
		await require_resource_access(
			agent_id,
			session,
			principal,
			ResourceType.AGENT,
		)
	return await _get_agent(agent_id, session)


async def update_agent(
	agent_id: TypeID,
	agent_in: AgentUpdate,
	session: AsyncSession,
	*,
	principal: Principal,
) -> Agent:
	require_permission(principal, "agents:manage")
	agent = await _get_agent(agent_id, session)
	if agent_in.model_id is not None:
		await _ensure_model(agent_in.model_id, session)

	update_data = agent_in.model_dump(exclude_unset=True)
	for field, value in update_data.items():
		setattr(agent, field, value)

	session.add(agent)
	await session.commit()
	return await _get_agent(TypeID(agent.id), session)


async def delete_agent(
	agent_id: TypeID,
	session: AsyncSession,
	*,
	principal: Principal,
) -> None:
	require_permission(principal, "agents:manage")
	agent = await _get_agent(agent_id, session)
	await session.delete(agent)
	await session.commit()
