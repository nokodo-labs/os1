"""Coverage-focused integration tests for plugins endpoints."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_plugins_available_and_native_detail(
	client: AsyncClient,
	admin_auth: dict[str, object],
) -> None:
	headers = admin_auth["headers"]
	assert isinstance(headers, dict)

	resp = await client.get("/v1/plugins/available", headers=headers)
	assert resp.status_code == 200
	available = resp.json()
	assert isinstance(available, list)

	native_ids = [p["id"] for p in available if p.get("is_native") is True]
	assert native_ids

	detail = await client.get(
		f"/v1/plugins/available/{native_ids[0]}",
		headers=headers,
	)
	assert detail.status_code == 200
	assert detail.json()["is_native"] is True


@pytest.mark.asyncio
async def test_plugins_crud_and_name_conflict(
	client: AsyncClient,
	admin_auth: dict[str, object],
) -> None:
	headers = admin_auth["headers"]
	assert isinstance(headers, dict)

	create_a = await client.post(
		"/v1/plugins",
		headers=headers,
		json={
			"name": "plug-a",
			"description": "d",
			"type": "tool",
			"author": None,
			"version": None,
			"source_code": "code",
		},
	)
	assert create_a.status_code == 201
	plugin_a = create_a.json()

	available_db = await client.get(
		f"/v1/plugins/available/{plugin_a['id']}",
		headers=headers,
	)
	assert available_db.status_code == 200
	assert available_db.json()["is_native"] is False

	create_b = await client.post(
		"/v1/plugins",
		headers=headers,
		json={
			"name": "plug-b",
			"description": None,
			"type": "tool",
			"author": None,
			"version": None,
			"source_code": "code",
		},
	)
	assert create_b.status_code == 201
	plugin_b = create_b.json()

	listed = await client.get("/v1/plugins", headers=headers)
	assert listed.status_code == 200

	got = await client.get(f"/v1/plugins/{plugin_a['id']}", headers=headers)
	assert got.status_code == 200

	updated = await client.patch(
		f"/v1/plugins/{plugin_a['id']}",
		headers=headers,
		json={"metadata": {"a": 1}},
	)
	assert updated.status_code == 200
	updated_body = updated.json()
	metadata = updated_body.get("metadata")
	if metadata is None:
		metadata = updated_body.get("metadata_")
	assert metadata == {"a": 1}

	conflict = await client.patch(
		f"/v1/plugins/{plugin_b['id']}",
		headers=headers,
		json={"name": plugin_a["name"]},
	)
	assert conflict.status_code == 409

	missing = await client.get("/v1/plugins/available/does-not-exist", headers=headers)
	assert missing.status_code == 404

	deleted = await client.delete(f"/v1/plugins/{plugin_a['id']}", headers=headers)
	assert deleted.status_code == 204
