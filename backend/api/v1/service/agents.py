"""Service layer for agent operations."""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.agent import AGENT_TYPEID_PREFIX, Agent
from api.models.event import Event, EventScope
from api.models.event_types import EventType
from api.models.model import MODEL_TYPEID_PREFIX, Model
from api.permissions import ResourceType
from api.schemas.access_rule import AccessRuleCreate
from api.schemas.agent import Agent as AgentSchema
from api.schemas.agent import AgentCreate, AgentUpdate
from api.schemas.sorting import SortDir
from api.v1.service import access_rules as access_rules_service
from api.v1.service import events as event_service
from api.v1.service.auth import Principal
from api.v1.service.authorization import (
	list_accessible_user_ids,
	require_permission,
	require_resource_access,
	resource_access_predicate,
)
from api.v1.service.listing import apply_sort, exact_typeid_filter
from api.v1.service.resource_payload_cache import (
	get_or_set_resource_payload_cache,
	invalidate_resource_payload_cache,
)
from nokodo_ai.utils.search import contains_pattern
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
	await event_service.persist_and_fanout_event(
		session,
		event=event,
		origin_session_id=origin_session_id,
	)
	return await _get_agent(agent_id, session)


async def list_agents(
	session: AsyncSession,
	principal: Principal,
	skip: int = 0,
	limit: int = 100,
	sort_by: str = "created_at",
	sort_dir: SortDir = "desc",
	q: str | None = None,
) -> list[Agent]:
	"""list agents visible to principal.

	managers see all agents. readers see only agents they have
	explicit access to via access rules.
	"""
	stmt = select(Agent)

	if not _can_manage(principal):
		stmt = stmt.where(resource_access_predicate(principal, ResourceType.AGENT))

	stmt = _apply_agent_search(stmt, q)
	stmt = apply_sort(
		stmt,
		sort_by,
		sort_dir,
		{
			"name": Agent.name,
			"created_at": Agent.created_at,
			"updated_at": Agent.updated_at,
		},
		tie_breaker=Agent.id,
	)
	result = await session.execute(stmt.offset(skip).limit(limit))
	return list(result.scalars().all())


def _apply_agent_search(stmt, q: str | None):
	if not q or not q.strip():
		return stmt
	pattern = contains_pattern(q.strip())
	return stmt.where(
		or_(
			Agent.name.ilike(pattern, escape="\\"),
			Agent.description.ilike(pattern, escape="\\"),
			exact_typeid_filter(Agent.id, q, AGENT_TYPEID_PREFIX),
			exact_typeid_filter(Agent.model_id, q, MODEL_TYPEID_PREFIX),
		)
	)


async def count_agents(
	session: AsyncSession,
	principal: Principal,
	q: str | None = None,
) -> int:
	"""count agents visible to principal."""
	stmt = select(func.count()).select_from(Agent)
	if not _can_manage(principal):
		stmt = stmt.where(resource_access_predicate(principal, ResourceType.AGENT))
	stmt = _apply_agent_search(stmt, q)
	return await session.scalar(stmt) or 0


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
	await event_service.persist_and_fanout_event(
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
	delete_recipients = await list_accessible_user_ids(
		ResourceType.AGENT,
		agent_id,
		session,
	)
	await session.delete(agent)
	event = Event(
		scope=EventScope.USER,
		scope_id=principal.user_id,
		type=EventType.AGENT_DELETED,
		data={"id": str(agent_id)},
		user_id=principal.user_id,
	)
	await event_service.persist_and_fanout_event(
		session,
		event=event,
		origin_session_id=origin_session_id,
		recipient_ids=delete_recipients,
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
	await event_service.persist_and_fanout_event(session, event=event)
	return updated_rules
