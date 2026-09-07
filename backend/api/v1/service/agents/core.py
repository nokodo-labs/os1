"""Service layer for agent operations."""

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.agent import AGENT_TYPEID_PREFIX, Agent
from api.models.event import Event, EventScope
from api.models.event_types import EventType
from api.models.model import MODEL_TYPEID_PREFIX, Model
from api.permissions import AccessLevel, ActionPermission, ResourceType
from api.schemas.access_rule import AccessRuleCreate
from api.schemas.agent import Agent as AgentSchema
from api.schemas.agent import AgentCreate, AgentUpdate
from api.schemas.sorting import SortDir
from api.v1.service.access_rules import set_access_rules_unchecked
from api.v1.service.authentication import Principal
from api.v1.service.authorization import (
	apply_metadata_write,
	apply_resource_access_list_filters,
	enqueue_accessible_users_version_drop,
	list_accessible_user_ids_for_resources,
	require_permission,
	require_resource_access,
	resource_access_predicate,
)
from api.v1.service.events import persist_and_fanout_event
from api.v1.service.listing import apply_sort, exact_typeid_filter
from api.v1.service.resource_payload_cache import (
	get_or_set_resource_payload_cache,
	invalidate_resource_payload_cache,
)
from nokodo_ai.utils.search import contains_pattern
from nokodo_ai.utils.typeid import TypeID


def _can_manage(principal: Principal) -> bool:
	"""check if principal has agents:manage permission."""
	return principal.has_permission(ActionPermission.AGENTS_MANAGE)


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
	require_permission(principal, ActionPermission.AGENTS_CREATE)
	await _ensure_model(agent_in.model_id, session)
	agent = Agent(**agent_in.model_dump(exclude={"metadata"}))
	apply_metadata_write(agent, agent_in.metadata)
	session.add(agent)
	await session.flush()
	await session.refresh(agent)
	agent_id = agent.id
	agent_data = AgentSchema.model_validate(agent).model_dump(mode="json")
	event = Event(
		scope=EventScope.USER,
		scope_id=principal.user.id,
		type=EventType.AGENT_CREATED,
		data=agent_data,
		user_id=principal.user.id,
	)
	await persist_and_fanout_event(
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
	access_relationship: str | None = None,
	resolved_access_level: AccessLevel | None = None,
) -> list[Agent]:
	"""list agents visible to principal.

	managers see all agents. readers see only agents they have
	explicit access to via access rules.
	"""
	stmt = select(Agent)

	if not _can_manage(principal):
		stmt = stmt.where(resource_access_predicate(principal, ResourceType.AGENT))
	stmt = apply_resource_access_list_filters(
		stmt,
		principal,
		ResourceType.AGENT,
		access_relationship,
		resolved_access_level,
	)

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
	access_relationship: str | None = None,
	resolved_access_level: AccessLevel | None = None,
) -> int:
	"""count agents visible to principal."""
	stmt = select(func.count()).select_from(Agent)
	if not _can_manage(principal):
		stmt = stmt.where(resource_access_predicate(principal, ResourceType.AGENT))
	stmt = apply_resource_access_list_filters(
		stmt,
		principal,
		ResourceType.AGENT,
		access_relationship,
		resolved_access_level,
	)
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
	require_permission(principal, ActionPermission.AGENTS_MANAGE)
	agent = await _get_agent(agent_id, session)
	model_id = agent_in.model_id
	if "model_id" in agent_in.model_fields_set and isinstance(model_id, str):
		await _ensure_model(model_id, session)

	update_data = agent_in.model_dump(exclude_unset=True, exclude={"metadata"})
	for field, value in update_data.items():
		setattr(agent, field, value)
	apply_metadata_write(agent, agent_in.metadata)

	session.add(agent)
	await session.flush()
	await session.refresh(agent)
	agent_data = AgentSchema.model_validate(agent).model_dump(mode="json")
	event = Event(
		scope=EventScope.USER,
		scope_id=principal.user.id,
		type=EventType.AGENT_UPDATED,
		data=agent_data,
		user_id=principal.user.id,
	)
	await persist_and_fanout_event(
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
	require_permission(principal, ActionPermission.AGENTS_MANAGE)
	agent = await _get_agent(agent_id, session)
	delete_recipients = await list_accessible_user_ids_for_resources(
		[(ResourceType.AGENT, agent_id)], session
	)
	# the row is gone for good, so reap the counter rather than leave behind a
	# key that any ACL mutation created and nothing will ever read again.
	enqueue_accessible_users_version_drop(ResourceType.AGENT, agent_id, session)
	await session.delete(agent)
	event = Event(
		scope=EventScope.USER,
		scope_id=principal.user.id,
		type=EventType.AGENT_DELETED,
		data={"id": str(agent_id)},
		user_id=principal.user.id,
	)
	await persist_and_fanout_event(
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
	require_permission(principal, ActionPermission.AGENTS_MANAGE)
	updated_rules = await set_access_rules_unchecked(
		ResourceType.AGENT, agent_id, rules, session
	)
	agent = await _get_agent(agent_id, session)
	agent_data = AgentSchema.model_validate(agent).model_dump(mode="json")
	event = Event(
		scope=EventScope.USER,
		scope_id=principal.user.id,
		type=EventType.AGENT_UPDATED,
		data=agent_data,
		user_id=principal.user.id,
	)
	await persist_and_fanout_event(session, event=event)
	return updated_rules
