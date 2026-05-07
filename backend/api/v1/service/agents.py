"""Service layer for agent operations."""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.agent import Agent
from api.models.event import Event, EventScope
from api.models.event_types import EventType
from api.models.model import Model
from api.permissions import ResourceType
from api.schemas.access_rule import AccessRuleCreate
from api.schemas.agent import Agent as AgentSchema
from api.schemas.agent import AgentCreate, AgentUpdate
from api.v1.service import access_rules as access_rules_service
from api.v1.service import events as event_service
from api.v1.service.auth import Principal
from api.v1.service.authorization import (
	require_permission,
	require_resource_access,
	resource_access_predicate,
)
from api.v1.service.resource_payload_cache import (
	get_or_set_resource_payload_cache,
	invalidate_resource_payload_cache,
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
	principal: Principal,
	origin_session_id: str | None = None,
) -> Agent:
	require_permission(principal, "agents:create")
	await _ensure_model(agent_in.model_id, session)
	agent = Agent(**agent_in.model_dump(by_alias=True))
	session.add(agent)
	await session.flush()
	await session.refresh(agent)
	agent_id = TypeID(agent.id)
	agent_data = AgentSchema.model_validate(agent).model_dump(mode="json")
	event = Event(
		scope=EventScope.USER,
		scope_id=principal.user_id,
		type=EventType.AGENT_CREATED,
		data=agent_data,
		user_id=principal.user_id,
	)
	await event_service.publish_event(
		session,
		event=event,
		origin_session_id=origin_session_id,
	)
	return await _get_agent(agent_id, session)


async def list_agents(
	session: AsyncSession,
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


async def get_agent_payload(
	agent_id: TypeID,
	session: AsyncSession,
	principal: Principal,
	use_cache: bool = True,
) -> AgentSchema:
	"""get an agent API payload after access is validated."""
	if not _can_manage(principal):
		await require_resource_access(
			agent_id,
			session,
			principal,
			ResourceType.AGENT,
		)

	async def load_payload() -> AgentSchema:
		return AgentSchema.model_validate(await _get_agent(agent_id, session))

	if not use_cache:
		return await load_payload()
	return await get_or_set_resource_payload_cache(
		ResourceType.AGENT,
		agent_id,
		AgentSchema,
		load_payload,
	)


async def update_agent(
	agent_id: TypeID,
	agent_in: AgentUpdate,
	session: AsyncSession,
	principal: Principal,
	origin_session_id: str | None = None,
) -> Agent:
	require_permission(principal, "agents:manage")
	agent = await _get_agent(agent_id, session)
	model_id = agent_in.model_id
	if "model_id" in agent_in.model_fields_set and isinstance(model_id, str):
		await _ensure_model(model_id, session)

	update_data = agent_in.model_dump(exclude_unset=True, by_alias=True)
	for field, value in update_data.items():
		setattr(agent, field, value)

	session.add(agent)
	await session.flush()
	await session.refresh(agent)
	agent_data = AgentSchema.model_validate(agent).model_dump(mode="json")
	event = Event(
		scope=EventScope.USER,
		scope_id=principal.user_id,
		type=EventType.AGENT_UPDATED,
		data=agent_data,
		user_id=principal.user_id,
	)
	await event_service.publish_event(
		session,
		event=event,
		origin_session_id=origin_session_id,
	)
	await invalidate_resource_payload_cache(ResourceType.AGENT, agent_id)
	return await _get_agent(agent_id, session)


async def delete_agent(
	agent_id: TypeID,
	session: AsyncSession,
	principal: Principal,
	origin_session_id: str | None = None,
) -> None:
	require_permission(principal, "agents:manage")
	agent = await _get_agent(agent_id, session)
	await session.delete(agent)
	event = Event(
		scope=EventScope.USER,
		scope_id=principal.user_id,
		type=EventType.AGENT_DELETED,
		data={"id": str(agent_id)},
		user_id=principal.user_id,
	)
	await event_service.publish_event(
		session,
		event=event,
		origin_session_id=origin_session_id,
	)
	await invalidate_resource_payload_cache(ResourceType.AGENT, agent_id)


async def set_agent_access_rules(
	agent_id: TypeID,
	rules: list[AccessRuleCreate],
	session: AsyncSession,
	principal: Principal,
) -> list:
	"""replace access rules for an agent and notify affected users."""
	require_permission(principal, "agents:manage")
	updated_rules = await access_rules_service.set_access_rules_unchecked(
		ResourceType.AGENT, agent_id, rules, session
	)
	agent = await _get_agent(agent_id, session)
	agent_data = AgentSchema.model_validate(agent).model_dump(mode="json")
	event = Event(
		scope=EventScope.USER,
		scope_id=principal.user_id,
		type=EventType.AGENT_UPDATED,
		data=agent_data,
		user_id=principal.user_id,
	)
	await event_service.publish_event(session, event=event)
	return updated_rules
