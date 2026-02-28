"""Tests for agent service."""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.access_rule import AccessRule
from api.models.model import ModelType
from api.models.user import User
from api.permissions import AccessLevel
from api.schemas.agent import AgentCreate, AgentUpdate
from api.schemas.model import ModelCreate
from api.schemas.provider import ProviderCreate
from api.v1.service import agents as agent_service
from api.v1.service import models as model_service
from api.v1.service import providers as provider_service
from api.v1.service.auth import Principal
from nokodo_ai.utils.typeid import new_typeid


async def _principal(
	session: AsyncSession,
	*,
	is_admin: bool,
) -> Principal:
	uid = new_typeid("user")
	user = User(
		email=f"{uid}@example.com",
		username=f"a{uid.replace('_', '')[:20]}",
		hashed_password="x",
		is_superuser=is_admin,
	)
	session.add(user)
	await session.flush()
	await session.refresh(user)
	return Principal(user=user, group_ids=(), permissions=frozenset())


@pytest.mark.asyncio
async def test_create_agent(db_session: AsyncSession) -> None:
	"""Test creating an agent."""
	agent_in = AgentCreate(
		name="test-agent",
		description="Test Agent",
		system_prompt="You are a test agent.",
		plugin_ids=[],
		config={},
	)
	principal = await _principal(db_session, is_admin=True)
	agent = await agent_service.create_agent(
		agent_in,
		db_session,
		principal=principal,
	)
	assert agent.name == "test-agent"


@pytest.mark.asyncio
async def test_list_agents(db_session: AsyncSession) -> None:
	"""Test listing agents."""
	principal = await _principal(db_session, is_admin=True)
	# Create agents
	await agent_service.create_agent(
		AgentCreate(
			name="agent-1",
			plugin_ids=[],
			config={},
		),
		db_session,
		principal=principal,
	)
	await agent_service.create_agent(
		AgentCreate(
			name="agent-2",
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
	principal = await _principal(db_session, is_admin=True)
	agent = await agent_service.create_agent(
		AgentCreate(
			name="agent-get",
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
	principal = await _principal(db_session, is_admin=True)
	agent = await agent_service.create_agent(
		AgentCreate(
			name="agent-update",
			plugin_ids=[],
			config={},
		),
		db_session,
		principal=principal,
	)


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
	principal = await _principal(db_session, is_admin=True)
	agent = await agent_service.create_agent(
		AgentCreate(
			name="agent-delete",
			plugin_ids=[],
			config={},
		),
		db_session,
		principal=principal,
	)

	await agent_service.delete_agent(agent.id, db_session, principal=principal)


	with pytest.raises(HTTPException) as exc:
		await agent_service.get_agent(agent.id, db_session, principal=principal)
	assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_create_agent_invalid_model(db_session: AsyncSession) -> None:
	"""Test creating an agent with invalid model (non-existent model_id)."""
	principal = await _principal(db_session, is_admin=True)
	agent_in = AgentCreate(
		name="agent-invalid-model",
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
	principal = await _principal(db_session, is_admin=True)
	agent = await agent_service.create_agent(
		AgentCreate(
			name="agent-update-model",
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
	principal = await _principal(db_session, is_admin=True)
	agent_in = AgentCreate(
		name="agent-no-model",
		plugin_ids=[],
		config={},
		model_id=None,
	)
	agent = await agent_service.create_agent(agent_in, db_session, principal=principal)
	assert agent.model_id is None


@pytest.mark.asyncio
async def test_agent_hidden_without_access_rule(db_session: AsyncSession) -> None:
	"""non-admin cannot get an agent unless an access rule grants access."""
	admin = await _principal(db_session, is_admin=True)
	agent = await agent_service.create_agent(
		AgentCreate(name="hidden-agent", plugin_ids=[], config={}),
		db_session,
		principal=admin,
	)

	non_admin = await _principal(db_session, is_admin=False)
	with pytest.raises(HTTPException):
		await agent_service.get_agent(agent.id, db_session, principal=non_admin)


@pytest.mark.asyncio
async def test_create_agent_with_model(db_session: AsyncSession) -> None:
	"""Test creating an agent with a valid model."""
	principal = await _principal(db_session, is_admin=True)
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
			model_type=ModelType.CHAT_MODEL,
		),
		db_session,
		principal=principal,
	)

	agent_in = AgentCreate(
		name="agent-with-model",
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
async def test_list_agents_filters_by_access_rules(
	db_session: AsyncSession,
) -> None:
	"""non-admin sees only agents with a matching access rule."""
	admin_principal = await _principal(db_session, is_admin=True)
	accessible = await agent_service.create_agent(
		AgentCreate(name="list-accessible", plugin_ids=[], config={}),
		db_session,
		principal=admin_principal,
	)
	await agent_service.create_agent(
		AgentCreate(name="list-hidden", plugin_ids=[], config={}),
		db_session,
		principal=admin_principal,
	)

	non_admin_principal = await _principal(db_session, is_admin=False)
	non_admin_user = non_admin_principal.user

	# grant reader access to one agent
	db_session.add(
		AccessRule(
			agent_id=accessible.id,
			subject_user_id=non_admin_user.id,
			level=AccessLevel.READER,
			order_index=0,
		)
	)
	await db_session.commit()

	visible = await agent_service.list_agents(db_session, principal=non_admin_principal)
	assert [agent.id for agent in visible] == [accessible.id]
