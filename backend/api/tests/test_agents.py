"""Tests for agent service."""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.agent import Agent, AgentVisibility
from api.models.model import ModelType
from api.models.user import User
from api.schemas.agent import AgentCreate, AgentUpdate
from api.schemas.model import ModelCreate
from api.schemas.provider import ProviderCreate
from api.v1.service import agents as agent_service
from api.v1.service import models as model_service
from api.v1.service import providers as provider_service
from api.v1.service.auth import Principal
from nokodo_ai.utils.typeid import new_typeid


def _admin_principal() -> Principal:
	user = User(email="admin@example.com", hashed_password="x", is_superuser=True)
	return Principal(user=user, group_ids=(), permissions=frozenset())


def _user_principal() -> Principal:
	user = User(email="user@example.com", hashed_password="x", is_superuser=False)
	return Principal(user=user, group_ids=(), permissions=frozenset())


@pytest.mark.asyncio
async def test_create_agent(db_session: AsyncSession) -> None:
	"""Test creating an agent."""
	agent_in = AgentCreate(
		name="test-agent",
		description="Test Agent",
		system_prompt="You are a test agent.",
		visibility=AgentVisibility.PRIVATE,
		plugin_ids=[],
		config={},
	)
	agent = await agent_service.create_agent(
		agent_in,
		db_session,
		principal=_admin_principal(),
	)
	assert agent.name == "test-agent"
	assert agent.visibility == AgentVisibility.PRIVATE


@pytest.mark.asyncio
async def test_list_agents(db_session: AsyncSession) -> None:
	"""Test listing agents."""
	principal = _admin_principal()
	# Create agents
	await agent_service.create_agent(
		AgentCreate(
			name="agent-1",
			visibility=AgentVisibility.PUBLIC,
			plugin_ids=[],
			config={},
		),
		db_session,
		principal=principal,
	)
	await agent_service.create_agent(
		AgentCreate(
			name="agent-2",
			visibility=AgentVisibility.PRIVATE,
			plugin_ids=[],
			config={},
		),
		db_session,
		principal=principal,
	)

	agents = await agent_service.list_agents(db_session, principal=principal)
	assert len(agents) >= 2
	names = {a.name for a in agents}
	assert "agent-1" in names
	assert "agent-2" in names


@pytest.mark.asyncio
async def test_get_agent(db_session: AsyncSession) -> None:
	"""Test getting an agent."""
	principal = _admin_principal()
	agent = await agent_service.create_agent(
		AgentCreate(
			name="agent-get",
			visibility=AgentVisibility.PUBLIC,
			plugin_ids=[],
			config={},
		),
		db_session,
		principal=principal,
	)

	fetched = await agent_service.get_agent(agent.id, db_session, principal=principal)
	assert fetched is not None
	assert fetched.id == agent.id
	assert fetched.name == "agent-get"


@pytest.mark.asyncio
async def test_update_agent(db_session: AsyncSession) -> None:
	"""Test updating an agent."""
	principal = _admin_principal()
	agent = await agent_service.create_agent(
		AgentCreate(
			name="agent-update",
			visibility=AgentVisibility.PUBLIC,
			plugin_ids=[],
			config={},
		),
		db_session,
		principal=principal,
	)

	from api.schemas.agent import AgentUpdate

	update_in = AgentUpdate(description="Updated description")
	updated = await agent_service.update_agent(
		agent.id,
		update_in,
		db_session,
		principal=principal,
	)
	assert updated.description == "Updated description"
	assert updated.name == "agent-update"


@pytest.mark.asyncio
async def test_delete_agent(db_session: AsyncSession) -> None:
	"""Test deleting an agent."""
	principal = _admin_principal()
	agent = await agent_service.create_agent(
		AgentCreate(
			name="agent-delete",
			visibility=AgentVisibility.PUBLIC,
			plugin_ids=[],
			config={},
		),
		db_session,
		principal=principal,
	)

	await agent_service.delete_agent(agent.id, db_session, principal=principal)

	from fastapi import HTTPException

	with pytest.raises(HTTPException) as exc:
		await agent_service.get_agent(agent.id, db_session, principal=principal)
	assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_create_agent_invalid_model(db_session: AsyncSession) -> None:
	"""Test creating an agent with invalid model (non-existent model_id)."""
	principal = _admin_principal()
	agent_in = AgentCreate(
		name="agent-invalid-model",
		visibility=AgentVisibility.PUBLIC,
		plugin_ids=[],
		config={},
		model_id=new_typeid("model"),  # valid format but doesn't exist
	)
	with pytest.raises(HTTPException) as exc:
		await agent_service.create_agent(agent_in, db_session, principal=principal)
	assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_update_agent_with_model_invalid(db_session: AsyncSession) -> None:
	"""Test updating an agent with invalid model."""
	principal = _admin_principal()
	agent = await agent_service.create_agent(
		AgentCreate(
			name="agent-update-model",
			visibility=AgentVisibility.PUBLIC,
			plugin_ids=[],
			config={},
		),
		db_session,
		principal=principal,
	)

	update_in = AgentUpdate(
		model_id=new_typeid("model")
	)  # valid format but doesn't exist
	with pytest.raises(HTTPException) as exc:
		await agent_service.update_agent(
			agent.id,
			update_in,
			db_session,
			principal=principal,
		)
	assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_create_agent_no_model(db_session: AsyncSession) -> None:
	"""Test creating an agent explicitly without a model."""
	principal = _admin_principal()
	agent_in = AgentCreate(
		name="agent-no-model",
		visibility=AgentVisibility.PUBLIC,
		plugin_ids=[],
		config={},
		model_id=None,
	)
	agent = await agent_service.create_agent(agent_in, db_session, principal=principal)
	assert agent.model_id is None


@pytest.mark.asyncio
async def test_private_agent_hidden_from_non_admin(db_session: AsyncSession) -> None:
	owner = _user_principal().user
	db_session.add(owner)
	await db_session.commit()
	private_agent = Agent(
		name="private-hidden",
		description=None,
		system_prompt=None,
		visibility=AgentVisibility.PRIVATE,
		plugin_ids=[],
		config={},
		model_id=None,
	)
	private_agent.owner_id = owner.id
	db_session.add(private_agent)
	await db_session.commit()

	non_admin = Principal(user=owner, group_ids=(), permissions=frozenset())
	with pytest.raises(HTTPException):
		await agent_service.get_agent(private_agent.id, db_session, principal=non_admin)


@pytest.mark.asyncio
async def test_create_agent_with_model(db_session: AsyncSession) -> None:
	"""Test creating an agent with a valid model."""
	principal = _admin_principal()
	# Create provider
	provider = await provider_service.create_provider(
		ProviderCreate(name="P_Agent_Test", adapter_type="openai"),
		db_session,
		principal=principal,
	)
	# Create model
	model = await model_service.create_model(
		ModelCreate(
			name="gpt-4-agent-test",
			provider_id=provider.id,
			model_type=ModelType.LLM,
		),
		db_session,
		principal=principal,
	)

	agent_in = AgentCreate(
		name="agent-with-model",
		visibility=AgentVisibility.PUBLIC,
		plugin_ids=[],
		config={},
		model_id=model.id,
	)
	agent = await agent_service.create_agent(agent_in, db_session, principal=principal)
	assert agent.model_id == model.id


@pytest.mark.asyncio
async def test_get_agent_endpoint(
	client: AsyncClient,
	admin_auth: dict[str, object],
) -> None:
	"""Ensure the GET /v1/agents/{id} route returns the created agent."""
	headers = admin_auth["headers"]
	assert isinstance(headers, dict)
	create_resp = await client.post(
		"/v1/agents",
		json={"name": "router-agent", "plugin_ids": [], "config": {}},
		headers=headers,
	)
	assert create_resp.status_code == 201
	agent_id = create_resp.json()["id"]

	detail_resp = await client.get(f"/v1/agents/{agent_id}", headers=headers)
	assert detail_resp.status_code == 200
	assert detail_resp.json()["id"] == agent_id


@pytest.mark.asyncio
async def test_list_agents_filters_private_for_non_admin(
	db_session: AsyncSession,
) -> None:
	admin_principal = _admin_principal()
	public = await agent_service.create_agent(
		AgentCreate(
			name="list-public",
			visibility=AgentVisibility.PUBLIC,
			plugin_ids=[],
			config={},
		),
		db_session,
		principal=admin_principal,
	)
	await agent_service.create_agent(
		AgentCreate(
			name="list-private",
			visibility=AgentVisibility.PRIVATE,
			plugin_ids=[],
			config={},
		),
		db_session,
		principal=admin_principal,
	)

	non_admin_user = _user_principal().user
	db_session.add(non_admin_user)
	await db_session.commit()
	non_admin_principal = Principal(
		user=non_admin_user, group_ids=(), permissions=frozenset()
	)

	visible = await agent_service.list_agents(db_session, principal=non_admin_principal)
	assert [agent.id for agent in visible] == [public.id]
