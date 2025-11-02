"""Tests for main application endpoints."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient) -> None:
	"""Test health check endpoint."""
	response = await client.get("/health")
	assert response.status_code == 200
	assert response.json() == {"status": "healthy"}


@pytest.mark.asyncio
async def test_api_docs_accessible(client: AsyncClient) -> None:
	"""Test that API documentation is accessible."""
	response = await client.get("/v1/docs")
	assert response.status_code == 200
