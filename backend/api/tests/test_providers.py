"""Provider tests."""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.config import settings
from api.models.provider import ProviderStatus
from api.schemas.provider import ProviderCreate, ProviderUpdate
from api.v1.service import providers as provider_service
from nokodo_ai.utils.security import decrypt_string


@pytest.mark.asyncio
async def test_create_provider(db_session: AsyncSession) -> None:
	provider_in = ProviderCreate(
		name="Test Provider",
		adapter_type="openai",
		base_url="https://api.openai.com/v1",
	)
	provider = await provider_service.create_provider(provider_in, db_session)
	assert provider.name == "Test Provider"
	assert provider.id is not None


@pytest.mark.asyncio
async def test_list_providers(db_session: AsyncSession) -> None:
	provider_in = ProviderCreate(name="P1", adapter_type="a1")
	await provider_service.create_provider(provider_in, db_session)

	providers = await provider_service.list_providers(db_session)
	assert len(providers) >= 1


@pytest.mark.asyncio
async def test_get_provider(db_session: AsyncSession) -> None:
	provider_in = ProviderCreate(name="P2", adapter_type="a2")
	created = await provider_service.create_provider(provider_in, db_session)

	fetched = await provider_service.get_provider(created.id, db_session)
	assert fetched.id == created.id


@pytest.mark.asyncio
async def test_get_provider_not_found(db_session: AsyncSession) -> None:
	with pytest.raises(HTTPException) as exc:
		await provider_service.get_provider("nonexistent", db_session)
	assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_update_provider(db_session: AsyncSession) -> None:
	provider_in = ProviderCreate(name="P3", adapter_type="a3")
	created = await provider_service.create_provider(provider_in, db_session)

	update_in = ProviderUpdate(
		adapter_type="a3_updated", status=ProviderStatus.DISABLED
	)
	updated = await provider_service.update_provider(created.id, update_in, db_session)
	assert updated.adapter_type == "a3_updated"
	assert updated.status == ProviderStatus.DISABLED


@pytest.mark.asyncio
async def test_update_provider_not_found(db_session: AsyncSession) -> None:
	with pytest.raises(HTTPException) as exc:
		await provider_service.update_provider(
			"nonexistent", ProviderUpdate(adapter_type="X"), db_session
		)
	assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_provider_router_endpoints(client: AsyncClient) -> None:
	"""Exercise list/detail/update routes to raise coverage."""
	create_resp = await client.post(
		"/v1/providers",
		json={
			"name": "router-provider",
			"adapter_type": "openai",
			"base_url": "https://api.example.com",
		},
	)
	assert create_resp.status_code == 201
	provider_id = create_resp.json()["id"]

	list_resp = await client.get("/v1/providers")
	assert list_resp.status_code == 200
	assert any(item["id"] == provider_id for item in list_resp.json())

	detail_resp = await client.get(f"/v1/providers/{provider_id}")
	assert detail_resp.status_code == 200
	assert detail_resp.json()["id"] == provider_id

	update_resp = await client.patch(
		f"/v1/providers/{provider_id}",
		json={"status": "disabled"},
	)
	assert update_resp.status_code == 200
	assert update_resp.json()["status"] == "disabled"


@pytest.mark.asyncio
async def test_create_provider_with_api_key(db_session: AsyncSession) -> None:
	"""Test creating a provider with an API key."""
	api_key = "sk-test-123"
	provider_in = ProviderCreate(
		name="Encrypted Provider",
		adapter_type="openai",
		api_key=api_key,
	)
	provider = await provider_service.create_provider(provider_in, db_session)

	assert provider.encrypted_api_key is not None
	assert provider.encrypted_api_key != api_key
	assert decrypt_string(provider.encrypted_api_key, settings.SECRET_KEY) == api_key


@pytest.mark.asyncio
async def test_update_provider_api_key(db_session: AsyncSession) -> None:
	"""Test updating a provider's API key."""
	# Create without key
	provider_in = ProviderCreate(
		name="Update Provider",
		adapter_type="openai",
	)
	provider = await provider_service.create_provider(provider_in, db_session)
	assert provider.encrypted_api_key is None

	# Update with key
	api_key = "sk-new-key"
	update_in = ProviderUpdate(api_key=api_key)
	updated = await provider_service.update_provider(provider.id, update_in, db_session)

	assert updated.encrypted_api_key is not None
	assert decrypt_string(updated.encrypted_api_key, settings.SECRET_KEY) == api_key
