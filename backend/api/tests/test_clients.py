"""Tests for user client registration."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.user import UserCreate
from api.v1.service import users as user_service


@pytest.mark.asyncio
async def test_upsert_list_update_delete_current_client(
	client: AsyncClient,
	db_session: AsyncSession,
) -> None:
	user = await user_service.create_user(
		UserCreate(
			email="client_user@example.com",
			username="client_user",
			password="password123",
			is_superuser=True,
		),
		db_session,
	)
	login_resp = await client.post(
		"/v1/auth/login/access-token",
		data={"username": user.email, "password": "password123"},
	)
	assert login_resp.status_code == 200
	headers = {"Authorization": f"Bearer {login_resp.json()['access_token']}"}

	create_resp = await client.post(
		f"/v1/users/{user.id}/clients",
		json={
			"client_key": "stable-client-key",
			"name": "desktop browser",
			"user_agent": "test browser",
			"info": {"os": "Windows", "browser": "Chrome"},
		},
		headers=headers,
	)
	assert create_resp.status_code == 200
	created = create_resp.json()
	assert created["client_key"] == "stable-client-key"
	assert created["name"] == "desktop browser"
	assert created["info"] == {"os": "Windows", "browser": "Chrome"}
	assert created["preferences"] == {}

	refresh_resp = await client.post(
		f"/v1/users/{user.id}/clients",
		json={
			"client_key": "stable-client-key",
			"name": "desktop browser refreshed",
			"user_agent": "test browser refreshed",
			"info": {"os": "Windows", "browser": "Edge"},
		},
		headers=headers,
	)
	assert refresh_resp.status_code == 200
	refreshed = refresh_resp.json()
	assert refreshed["id"] == created["id"]
	assert refreshed["name"] == "desktop browser refreshed"
	assert refreshed["info"] == {"os": "Windows", "browser": "Edge"}

	list_resp = await client.get(f"/v1/users/{user.id}/clients", headers=headers)
	assert list_resp.status_code == 200
	assert [item["id"] for item in list_resp.json()] == [created["id"]]

	patch_resp = await client.patch(
		f"/v1/users/{user.id}/clients/{created['id']}",
		json={"name": "desktop browser renamed"},
		headers=headers,
	)
	assert patch_resp.status_code == 200
	assert patch_resp.json()["name"] == "desktop browser renamed"

	prefs_resp = await client.put(
		f"/v1/users/{user.id}/clients/{created['id']}/preferences",
		json={
			"appearance": {
				"themeMode": "dark",
				"autoBackground": False,
				"background": "clouds2-dark",
				"staticColor": "#101010",
				"bubbleTailStyle": "imessage",
			},
			"accessibility": {
				"hapticFeedback": False,
			},
			"advanced": {
				"svgLiquidGlass": True,
				"svgLiquidGlassIsland": True,
				"svgLiquidMetal": False,
			},
		},
		headers=headers,
	)
	assert prefs_resp.status_code == 200
	assert prefs_resp.json()["preferences"] == {
		"appearance": {
			"themeMode": "dark",
			"autoBackground": False,
			"background": "clouds2-dark",
			"staticColor": "#101010",
			"bubbleTailStyle": "imessage",
		},
		"accessibility": {
			"hapticFeedback": False,
		},
		"advanced": {
			"svgLiquidGlass": True,
			"svgLiquidGlassIsland": True,
			"svgLiquidMetal": False,
		},
	}

	invalid_prefs_resp = await client.put(
		f"/v1/users/{user.id}/clients/{created['id']}/preferences",
		json={"accessibility": {"hapticFeedback": True, "unknown": True}},
		headers=headers,
	)
	assert invalid_prefs_resp.status_code == 422

	clear_resp = await client.put(
		f"/v1/users/{user.id}/clients/{created['id']}/preferences",
		json={"appearance": {}, "accessibility": {}, "advanced": {}},
		headers=headers,
	)
	assert clear_resp.status_code == 200
	assert clear_resp.json()["preferences"] == {}

	delete_resp = await client.delete(
		f"/v1/users/{user.id}/clients/{created['id']}",
		headers=headers,
	)
	assert delete_resp.status_code == 204

	list_after_delete = await client.get(
		f"/v1/users/{user.id}/clients", headers=headers
	)
	assert list_after_delete.status_code == 200
	assert list_after_delete.json() == []
