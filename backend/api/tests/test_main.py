"""Tests for main application endpoints."""

import pytest
from httpx import AsyncClient

import api.main as main_module
from api.boot_settings import boot_settings
from api.settings import settings as runtime_settings


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
	assert payload["name"] == runtime_settings.branding.site_name
	assert payload["api_version"] == "v1"


@pytest.mark.asyncio
async def test_lifespan_initializes_database(monkeypatch: pytest.MonkeyPatch) -> None:
	"""The lifespan hook should initialize the database outside of test mode."""
	called = {"init": False}

	async def fake_init_db() -> None:
		called["init"] = True

	async def fake_noop() -> None:
		return None

	async def fake_start_invalidation_subscriber() -> None:
		return None

	async def fake_start_event_subscriber() -> None:
		return None

	monkeypatch.setattr(main_module, "init_db", fake_init_db)
	monkeypatch.setattr(main_module, "startup_taskiq", fake_noop)
	monkeypatch.setattr(main_module, "shutdown_taskiq", fake_noop)
	monkeypatch.setattr(
		main_module,
		"reconcile_calendar_event_notification_schedules",
		fake_noop,
	)
	monkeypatch.setattr(
		main_module,
		"reconcile_reminder_notification_schedules",
		fake_noop,
	)
	monkeypatch.setattr(
		main_module,
		"start_invalidation_subscriber",
		fake_start_invalidation_subscriber,
	)
	monkeypatch.setattr(
		main_module,
		"start_event_subscriber",
		fake_start_event_subscriber,
	)
	monkeypatch.setattr(boot_settings, "ENV", "dev")
	original_testing = boot_settings.TESTING
	boot_settings.TESTING = False
	try:
		async with main_module.lifespan(main_module.app):
			pass
	finally:
		boot_settings.TESTING = original_testing

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
	original_testing = boot_settings.TESTING
	boot_settings.TESTING = True
	try:
		async with main_module.lifespan(main_module.app):
			pass
	finally:
		boot_settings.TESTING = original_testing

	assert called["init"] == 0


@pytest.mark.asyncio
async def test_system_status_endpoint(client: AsyncClient) -> None:
	response = await client.get("/system/status")
	assert response.status_code == 200
	data = response.json()
	assert "initialized" in data
	assert isinstance(data["initialized"], bool)


@pytest.mark.asyncio
async def test_public_settings_endpoint(client: AsyncClient) -> None:
	response = await client.get("/v1/settings")
	assert response.status_code == 200
	data = response.json()
	assert "data" in data
	assert "branding" in data["data"]
	assert "public_frontend_origin" in data["data"]["branding"]
	assert "public_cdn_origin" in data["data"]["branding"]
	assert "public_console_origin" in data["data"]["branding"]
