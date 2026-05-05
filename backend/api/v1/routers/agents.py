"""Agent routers."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.models.access_rule import AccessRule
from api.models.agent import Agent
from api.permissions import ResourceType
from api.schemas.access_rule import (
	AccessRuleCreate,
	AccessRuleResponse,
)
from api.schemas.agent import Agent as AgentSchema
from api.schemas.agent import AgentCreate, AgentUpdate
from api.v1.service import access_rules as access_rules_service
from api.v1.service import agents as agent_service
from api.v1.service.auth import Principal, get_current_principal
from api.v1.service.authorization import require_permission
from api.v1.service.events import SessionId
from nokodo_ai.utils.typeid import TypeID


router = APIRouter(prefix="/agents", tags=["agents"])


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
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[Agent]:
	"""List all agents visible to the caller."""
	return await agent_service.list_agents(db, principal=principal)


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


@router.get("/{agent_id}/access-rules", response_model=list[AccessRuleResponse])
async def list_agent_access_rules(
	agent_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[AccessRule]:
	"""list access rules for an agent.

	requires agents:manage permission (not resource-level admin) because
	agents are admin-managed resources without individual owners.
	"""
	require_permission(principal, "agents:manage")
	return await access_rules_service.list_access_rules_unchecked(
		ResourceType.AGENT, agent_id, db
	)


@router.put("/{agent_id}/access-rules", response_model=list[AccessRuleResponse])
async def set_agent_access_rules(
	agent_id: TypeID,
	rules: list[AccessRuleCreate],
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[AccessRule]:
	"""replace access rules for an agent.

	requires agents:manage permission.
	"""
	return await agent_service.set_agent_access_rules(
		agent_id, rules, db, principal=principal
	)
