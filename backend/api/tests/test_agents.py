"""Tests for agent service."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.agent import AgentVisibility
from api.schemas.agent import AgentCreate
from api.v1.service import agents as agent_service


@pytest.mark.asyncio
async def test_create_agent(db_session: AsyncSession) -> None:
	"""Test creating an agent."""
	agent_in = AgentCreate(
		name="test-agent",
		description="Test Agent",
		system_prompt="You are a test agent.",
		visibility=AgentVisibility.PRIVATE,
		tool_ids=[],
		config={},
	)
	agent = await agent_service.create_agent(agent_in, db_session)
	assert agent.name == "test-agent"
	assert agent.visibility == AgentVisibility.PRIVATE


@pytest.mark.asyncio
async def test_list_agents(db_session: AsyncSession) -> None:
	"""Test listing agents."""
	# Create agents
	await agent_service.create_agent(
		AgentCreate(
			name="agent-1",
			visibility=AgentVisibility.PUBLIC,
			tool_ids=[],
			config={},
		),
		db_session,
	)
	await agent_service.create_agent(
		AgentCreate(
			name="agent-2",
			visibility=AgentVisibility.PRIVATE,
			tool_ids=[],
			config={},
		),
		db_session,
	)

	agents = await agent_service.list_agents(db_session)
	assert len(agents) >= 2
	names = {a.name for a in agents}
	assert "agent-1" in names
	assert "agent-2" in names


@pytest.mark.asyncio
async def test_get_agent(db_session: AsyncSession) -> None:
	"""Test getting an agent."""
	agent = await agent_service.create_agent(
		AgentCreate(
			name="agent-get",
			visibility=AgentVisibility.PUBLIC,
			tool_ids=[],
			config={},
		),
		db_session,
	)

	fetched = await agent_service.get_agent(agent.id, db_session)
	assert fetched is not None
	assert fetched.id == agent.id
	assert fetched.name == "agent-get"


@pytest.mark.asyncio
async def test_update_agent(db_session: AsyncSession) -> None:
	"""Test updating an agent."""
	agent = await agent_service.create_agent(
		AgentCreate(
			name="agent-update",
			visibility=AgentVisibility.PUBLIC,
			tool_ids=[],
			config={},
		),
		db_session,
	)

	from api.schemas.agent import AgentUpdate

	update_in = AgentUpdate(description="Updated description")
	updated = await agent_service.update_agent(agent.id, update_in, db_session)
	assert updated.description == "Updated description"
	assert updated.name == "agent-update"


@pytest.mark.asyncio
async def test_delete_agent(db_session: AsyncSession) -> None:
	"""Test deleting an agent."""
	agent = await agent_service.create_agent(
		AgentCreate(
			name="agent-delete",
			visibility=AgentVisibility.PUBLIC,
			tool_ids=[],
			config={},
		),
		db_session,
	)

	await agent_service.delete_agent(agent.id, db_session)

	from fastapi import HTTPException

	with pytest.raises(HTTPException) as exc:
		await agent_service.get_agent(agent.id, db_session)
	assert exc.value.status_code == 404
