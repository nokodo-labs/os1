from enum import Enum

import pytest

from api.models.common import StringEnum
from api.models.model import Model
from api.models.provider import Provider, ProviderStatus, ProviderType


class EnumForTest(Enum):
	A = "a"
	B = "b"


def test_string_enum_none_handling():
	string_enum = StringEnum(EnumForTest)

	# Test process_bind_param
	assert string_enum.process_bind_param(None, None) is None
	assert string_enum.process_bind_param(EnumForTest.A, None) == "a"

	# Test process_result_value
	assert string_enum.process_result_value(None, None) is None
	assert string_enum.process_result_value("a", None) == EnumForTest.A


@pytest.mark.asyncio
async def test_provider_model_properties(db_session):
	provider = Provider(
		name="test-provider-props",
		adapter_type="openai",
		provider_type=ProviderType.EXTERNAL,
		status=ProviderStatus.ENABLED,
		is_autofetch_enabled=True,
	)
	db_session.add(provider)
	await db_session.commit()
	await db_session.refresh(provider)

	model1 = Model(
		provider_id=provider.id,
		name="model-manual",
		model_type="llm",
		capabilities={},
		enabled=True,
		is_autofetched=False,
	)
	model2 = Model(
		provider_id=provider.id,
		name="model-auto",
		model_type="llm",
		capabilities={},
		enabled=True,
		is_autofetched=True,
	)
	db_session.add_all([model1, model2])
	await db_session.commit()

	# Need to refresh provider to load relationship
	await db_session.refresh(provider, attribute_names=["models"])

	assert len(provider.manual_models) == 1
	assert provider.manual_models[0].name == "model-manual"

	assert len(provider.autofetched_models) == 1
	assert provider.autofetched_models[0].name == "model-auto"


@pytest.mark.asyncio
async def test_system_status_endpoint(client):
	response = await client.get("/v1/system/status")
	assert response.status_code == 200
	data = response.json()
	assert "initialized" in data
	assert isinstance(data["initialized"], bool)
