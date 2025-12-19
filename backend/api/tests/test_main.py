"""Tests for main application endpoints."""

import pytest
from httpx import AsyncClient

import api.main as main_module
from api.core.config import settings as app_settings


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


@pytest.mark.asyncio
async def test_root_endpoint(client: AsyncClient) -> None:
	"""Ensure the root metadata endpoint renders project info."""
	response = await client.get("/")
	assert response.status_code == 200
	payload = response.json()
	assert payload["name"] == app_settings.PROJECT_NAME
	assert payload["api_version"] == "v1"


@pytest.mark.asyncio
async def test_lifespan_initializes_database(monkeypatch: pytest.MonkeyPatch) -> None:
	"""The lifespan hook should initialize the database outside of test mode."""
	called = {"init": False}

	async def fake_init_db() -> None:
		called["init"] = True

	monkeypatch.setattr(main_module, "init_db", fake_init_db)
	original_testing = app_settings.TESTING
	app_settings.TESTING = False
	try:
		async with main_module.lifespan(main_module.app):
			pass
	finally:
		app_settings.TESTING = original_testing

	assert called["init"] is True


@pytest.mark.asyncio
async def test_lifespan_skips_db_init_when_testing(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""When TESTING is true lifespan must not initialize the database."""
	called = {"init": 0}

	async def fake_init_db() -> None:
		called["init"] += 1

	monkeypatch.setattr(main_module, "init_db", fake_init_db)
	original_testing = app_settings.TESTING
	app_settings.TESTING = True
	try:
		async with main_module.lifespan(main_module.app):
			pass
	finally:
		app_settings.TESTING = original_testing

	assert called["init"] == 0


@pytest.mark.asyncio
async def test_system_status_endpoint(client):
	response = await client.get("/v1/system/status")
	assert response.status_code == 200
	data = response.json()
	assert "initialized" in data
	assert isinstance(data["initialized"], bool)


@pytest.mark.asyncio
async def test_system_config_endpoint(client):
	response = await client.get("/v1/system/config")
	assert response.status_code == 200
	data = response.json()
	assert "frontend_origin" in data
	assert "cdn_origin" in data
