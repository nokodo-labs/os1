"""Model tests."""

from __future__ import annotations

from enum import Enum

import pytest
from fastapi import HTTPException
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.base import StringEnum
from api.models.model import ModelType
from api.models.user import User
from api.schemas.model import ModelCreate, ModelUpdate
from api.schemas.provider import ProviderCreate
from api.v1.service import models as model_service
from api.v1.service import providers as provider_service
from api.v1.service.auth import Principal


def _admin_principal() -> Principal:
	user = User(
		email="admin@example.com",
		username="admin_models",
		hashed_password="x",
		is_superuser=True,
	)
	return Principal(user=user, group_ids=(), permissions=frozenset())


@pytest.mark.asyncio
async def test_create_model(db_session: AsyncSession) -> None:
	# Create provider
	admin = _admin_principal()
	provider = await provider_service.create_provider(
		ProviderCreate(name="P_Model", adapter_type="openai"),
		db_session,
		principal=admin,
	)

	model_in = ModelCreate(
		provider_id=provider.id,
		name="gpt-4",
		model_type=ModelType.CHAT_MODEL,
		capabilities=["chat"],
		enabled=True,
	)
	model = await model_service.create_model(model_in, db_session, principal=admin)
	assert model.name == "gpt-4"
	assert model.provider_id == provider.id


@pytest.mark.asyncio
async def test_create_model_invalid_provider(db_session: AsyncSession) -> None:
	admin = _admin_principal()
	model_in = ModelCreate(
		provider_id="nonexistent",
		name="gpt-4",
		model_type=ModelType.CHAT_MODEL,
		capabilities=[],
		enabled=True,
	)
	with pytest.raises(HTTPException) as exc:
		await model_service.create_model(model_in, db_session, principal=admin)
	assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_list_models(db_session: AsyncSession) -> None:
	admin = _admin_principal()
	provider = await provider_service.create_provider(
		ProviderCreate(name="P_List", adapter_type="openai"),
		db_session,
		principal=admin,
	)
	model_in = ModelCreate(
		provider_id=provider.id,
		name="m1",
		model_type=ModelType.CHAT_MODEL,
		capabilities=[],
		enabled=True,
	)
	await model_service.create_model(model_in, db_session, principal=admin)

	models = await model_service.list_models(db_session, principal=admin)
	assert len(models) >= 1

	models_filtered = await model_service.list_models(
		db_session, provider_id=provider.id, principal=admin
	)
	assert len(models_filtered) >= 1

	models_empty = await model_service.list_models(
		db_session, provider_id="nonexistent", principal=admin
	)
	assert len(models_empty) == 0


@pytest.mark.asyncio
async def test_get_model(db_session: AsyncSession) -> None:
	admin = _admin_principal()
	provider = await provider_service.create_provider(
		ProviderCreate(name="P_Get", adapter_type="openai"),
		db_session,
		principal=admin,
	)
	model_in = ModelCreate(
		provider_id=provider.id,
		name="m2",
		model_type=ModelType.CHAT_MODEL,
		capabilities=[],
		enabled=True,
	)
	created = await model_service.create_model(model_in, db_session, principal=admin)

	fetched = await model_service.get_model(created.id, db_session, principal=admin)
	assert fetched.id == created.id


@pytest.mark.asyncio
async def test_get_model_not_found(db_session: AsyncSession) -> None:
	admin = _admin_principal()
	with pytest.raises(HTTPException) as exc:
		await model_service.get_model("nonexistent", db_session, principal=admin)
	assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_models_router_endpoints(
	client: AsyncClient,
	admin_auth: dict[str, object],
) -> None:
	"""Hit list and detail routes to cover router branch logic."""
	headers = admin_auth["headers"]
	assert isinstance(headers, dict)
	provider_resp = await client.post(
		"/v1/providers",
		json={"name": "models-router-provider", "adapter_type": "openai"},
		headers=headers,
	)
	assert provider_resp.status_code == 201
	provider_id = provider_resp.json()["id"]
	model_resp = await client.post(
		"/v1/models",
		json={
			"provider_id": provider_id,
			"name": "models-router",
			"model_type": "chat_model",
			"capabilities": ["chat"],
		},
		headers=headers,
	)
	assert model_resp.status_code == 201
	model_id = model_resp.json()["id"]

	list_resp = await client.get("/v1/models", headers=headers)
	assert list_resp.status_code == 200
	assert any(item["id"] == model_id for item in list_resp.json())

	detail_resp = await client.get(f"/v1/models/{model_id}", headers=headers)
	assert detail_resp.status_code == 200
	assert detail_resp.json()["id"] == model_id

	filtered_list_resp = await client.get(
		f"/v1/models?provider_id={provider_id}",
		headers=headers,
	)
	assert filtered_list_resp.status_code == 200
	assert any(item["id"] == model_id for item in filtered_list_resp.json())

	update_resp = await client.patch(
		f"/v1/models/{model_id}",
		json={"name": "models-router-updated"},
		headers=headers,
	)
	assert update_resp.status_code == 200
	assert update_resp.json()["name"] == "models-router-updated"

	delete_resp = await client.delete(f"/v1/models/{model_id}", headers=headers)
	assert delete_resp.status_code == 204

	not_found_resp = await client.get(f"/v1/models/{model_id}", headers=headers)
	assert not_found_resp.status_code == 404


@pytest.mark.asyncio
async def test_update_model_service(db_session: AsyncSession) -> None:
	admin = _admin_principal()
	provider = await provider_service.create_provider(
		ProviderCreate(name="P_Update", adapter_type="openai"),
		db_session,
		principal=admin,
	)
	model = await model_service.create_model(
		ModelCreate(
			provider_id=provider.id,
			name="m_update",
			model_type=ModelType.CHAT_MODEL,
			capabilities=[],
			enabled=True,
		),
		db_session,
		principal=admin,
	)

	updated = await model_service.update_model(
		model.id,
		ModelUpdate(name="m_updated", enabled=False),
		db_session,
		principal=admin,
	)
	assert updated.id == model.id
	assert updated.name == "m_updated"
	assert updated.enabled is False


@pytest.mark.asyncio
async def test_delete_model_service(db_session: AsyncSession) -> None:
	admin = _admin_principal()
	provider = await provider_service.create_provider(
		ProviderCreate(name="P_Delete", adapter_type="openai"),
		db_session,
		principal=admin,
	)
	model = await model_service.create_model(
		ModelCreate(
			provider_id=provider.id,
			name="m_delete",
			model_type=ModelType.CHAT_MODEL,
			capabilities=[],
			enabled=True,
		),
		db_session,
		principal=admin,
	)

	await model_service.delete_model(model.id, db_session, principal=admin)
	with pytest.raises(HTTPException) as exc:
		await model_service.get_model(model.id, db_session, principal=admin)
	assert exc.value.status_code == 404


class EnumForTest(Enum):
	A = "a"
	B = "b"


def test_string_enum_none_handling() -> None:
	string_enum = StringEnum(EnumForTest)

	# Test process_bind_param
	assert string_enum.process_bind_param(None, None) is None
	assert string_enum.process_bind_param(EnumForTest.A, None) == "a"

	# Test process_result_value
	assert string_enum.process_result_value(None, None) is None
	assert string_enum.process_result_value("a", None) == EnumForTest.A
