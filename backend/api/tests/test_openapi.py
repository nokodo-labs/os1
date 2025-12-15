"""Tests ensuring the API can generate and serve OpenAPI specs."""

import json

import pytest
from httpx import AsyncClient

from api.v1.app import v1_app


def _assert_openapi_schema_shape(schema: dict) -> None:
	assert isinstance(schema.get("openapi"), str)
	assert isinstance(schema.get("info"), dict)
	assert isinstance(schema.get("paths"), dict)


@pytest.mark.asyncio
async def test_openapi_schema_can_be_generated() -> None:
	"""Ensure schema generation works and is JSON serializable."""
	schema = v1_app.openapi()
	_assert_openapi_schema_shape(schema)
	assert schema["info"]["title"] == "nokodo AI API v1"
	json.dumps(schema)


@pytest.mark.asyncio
async def test_openapi_json_endpoint_returns_schema(client: AsyncClient) -> None:
	"""Ensure the mounted v1 OpenAPI endpoint returns a valid schema."""
	response = await client.get("/v1/openapi.json")
	assert response.status_code == 200
	assert response.headers.get("content-type", "").startswith("application/json")

	schema = response.json()
	_assert_openapi_schema_shape(schema)
	assert schema["info"]["title"] == "nokodo AI API v1"
	assert "/system/status" in schema["paths"]
