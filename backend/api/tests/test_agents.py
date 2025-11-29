"""Tests for agent service."""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.agent import AgentVisibility
from api.models.model import ModelType
from api.schemas.agent import AgentCreate, AgentUpdate
from api.schemas.model import ModelCreate
from api.schemas.provider import ProviderCreate
from api.v1.service import agents as agent_service
from api.v1.service import models as model_service
from api.v1.service import providers as provider_service


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


@pytest.mark.asyncio
async def test_create_agent_invalid_model(db_session: AsyncSession) -> None:
	"""Test creating an agent with invalid model."""
	agent_in = AgentCreate(
		name="agent-invalid-model",
		visibility=AgentVisibility.PUBLIC,
		tool_ids=[],
		config={},
		model_id="nonexistent",
	)
	with pytest.raises(HTTPException) as exc:
		await agent_service.create_agent(agent_in, db_session)
	assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_update_agent_with_model_invalid(db_session: AsyncSession) -> None:
	"""Test updating an agent with invalid model."""
	agent = await agent_service.create_agent(
		AgentCreate(
			name="agent-update-model",
			visibility=AgentVisibility.PUBLIC,
			tool_ids=[],
			config={},
		),
		db_session,
	)

	update_in = AgentUpdate(model_id="nonexistent")
	with pytest.raises(HTTPException) as exc:
		await agent_service.update_agent(agent.id, update_in, db_session)
	assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_create_agent_no_model(db_session: AsyncSession) -> None:
	"""Test creating an agent explicitly without a model."""
	agent_in = AgentCreate(
		name="agent-no-model",
		visibility=AgentVisibility.PUBLIC,
		tool_ids=[],
		config={},
		model_id=None,
	)
	agent = await agent_service.create_agent(agent_in, db_session)
	assert agent.model_id is None


@pytest.mark.asyncio
async def test_create_agent_with_model(db_session: AsyncSession) -> None:
	"""Test creating an agent with a valid model."""
	# Create provider
	provider = await provider_service.create_provider(
		ProviderCreate(name="P_Agent_Test", adapter_type="openai"), db_session
	)
	# Create model
	model = await model_service.create_model(
		ModelCreate(
			name="gpt-4-agent-test",
			provider_id=provider.id,
			model_type=ModelType.LLM,
		),
		db_session,
	)

	agent_in = AgentCreate(
		name="agent-with-model",
		visibility=AgentVisibility.PUBLIC,
		tool_ids=[],
		config={},
		model_id=model.id,
	)
	agent = await agent_service.create_agent(agent_in, db_session)
	assert agent.model_id == model.id


@pytest.mark.asyncio
async def test_get_agent_endpoint(client: AsyncClient) -> None:
	"""Ensure the GET /v1/agents/{id} route returns the created agent."""
	create_resp = await client.post(
		"/v1/agents",
		json={"name": "router-agent", "tool_ids": [], "config": {}},
	)
	assert create_resp.status_code == 201
	agent_id = create_resp.json()["id"]

	detail_resp = await client.get(f"/v1/agents/{agent_id}")
	assert detail_resp.status_code == 200
	assert detail_resp.json()["id"] == agent_id
