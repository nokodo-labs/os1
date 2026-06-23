"""Access level resolver API tests."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from nokodo_ai.utils.typeid import new_typeid


async def _create_user(
	client: AsyncClient,
	admin_headers: dict[str, str],
	prefix: str,
) -> tuple[dict[str, object], dict[str, str]]:
	email = f"{prefix}-{new_typeid('user')}@example.com"
	username = f"{prefix}{new_typeid('user')[-12:]}"
	password = "password"
	user_resp = await client.post(
		"/v1/users",
		headers=admin_headers,
		json={
			"email": email,
			"username": username,
			"password": password,
			"is_superuser": False,
		},
	)
	assert user_resp.status_code == 201
	user = user_resp.json()

	login_resp = await client.post(
		"/v1/auth/login/access-token",
		data={"username": email, "password": password},
	)
	assert login_resp.status_code == 200
	token = login_resp.json()["access_token"]
	return user, {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_resolve_access_levels_gates_self_by_read_access(
	client: AsyncClient,
	admin_auth: dict[str, object],
	user_auth: dict[str, object],
) -> None:
	owner = user_auth["user"]
	owner_headers = user_auth["headers"]
	admin_headers = admin_auth["headers"]
	assert isinstance(owner, dict)
	assert isinstance(owner_headers, dict)
	assert isinstance(admin_headers, dict)

	project_resp = await client.post(
		"/v1/projects",
		headers=owner_headers,
		json={"name": "resolver project"},
	)
	assert project_resp.status_code == 201
	project_id = project_resp.json()["id"]

	editor, editor_headers = await _create_user(client, admin_headers, "editor")
	outsider, outsider_headers = await _create_user(client, admin_headers, "outsider")

	acl_resp = await client.put(
		f"/v1/projects/{project_id}/access/rules",
		headers=owner_headers,
		json=[{"subject_user_id": editor["id"], "level": "editor"}],
	)
	assert acl_resp.status_code == 200

	editor_resp = await client.post(
		f"/v1/projects/{project_id}/access/resolve",
		headers=editor_headers,
		json={
			"subject_user_ids": [editor["id"]],
		},
	)
	assert editor_resp.status_code == 200
	assert editor_resp.json() == [
		{
			"resource_type": "project",
			"resource_id": project_id,
			"user_id": editor["id"],
			"level": "editor",
		}
	]

	outsider_resp = await client.post(
		f"/v1/projects/{project_id}/access/resolve",
		headers=outsider_headers,
		json={
			"subject_user_ids": [outsider["id"]],
		},
	)
	assert outsider_resp.status_code == 404


@pytest.mark.asyncio
async def test_resolve_access_levels_requires_admin_for_other_subjects(
	client: AsyncClient,
	admin_auth: dict[str, object],
	user_auth: dict[str, object],
) -> None:
	owner = user_auth["user"]
	owner_headers = user_auth["headers"]
	admin_headers = admin_auth["headers"]
	assert isinstance(owner, dict)
	assert isinstance(owner_headers, dict)
	assert isinstance(admin_headers, dict)

	project_resp = await client.post(
		"/v1/projects",
		headers=owner_headers,
		json={"name": "bulk resolver project"},
	)
	assert project_resp.status_code == 201
	project_id = project_resp.json()["id"]

	editor, editor_headers = await _create_user(client, admin_headers, "editor")
	outsider, _ = await _create_user(client, admin_headers, "outsider")

	acl_resp = await client.put(
		f"/v1/projects/{project_id}/access/rules",
		headers=owner_headers,
		json=[{"subject_user_id": editor["id"], "level": "editor"}],
	)
	assert acl_resp.status_code == 200

	forbidden_resp = await client.post(
		f"/v1/projects/{project_id}/access/resolve",
		headers=editor_headers,
		json={
			"subject_user_ids": [owner["id"]],
		},
	)
	assert forbidden_resp.status_code == 403

	owner_resp = await client.post(
		f"/v1/projects/{project_id}/access/resolve",
		headers=owner_headers,
		json={
			"subject_user_ids": [owner["id"], editor["id"], outsider["id"]],
		},
	)
	assert owner_resp.status_code == 200
	assert owner_resp.json() == [
		{
			"resource_type": "project",
			"resource_id": project_id,
			"user_id": owner["id"],
			"level": "admin",
		},
		{
			"resource_type": "project",
			"resource_id": project_id,
			"user_id": editor["id"],
			"level": "editor",
		},
		{
			"resource_type": "project",
			"resource_id": project_id,
			"user_id": outsider["id"],
			"level": None,
		},
	]


@pytest.mark.asyncio
async def test_individual_access_rule_routes_are_resource_scoped(
	client: AsyncClient,
	admin_auth: dict[str, object],
	user_auth: dict[str, object],
) -> None:
	owner_headers = user_auth["headers"]
	admin_headers = admin_auth["headers"]
	assert isinstance(owner_headers, dict)
	assert isinstance(admin_headers, dict)

	project_resp = await client.post(
		"/v1/projects",
		headers=owner_headers,
		json={"name": "individual rule project"},
	)
	assert project_resp.status_code == 201
	project_id = project_resp.json()["id"]

	other_project_resp = await client.post(
		"/v1/projects",
		headers=owner_headers,
		json={"name": "other individual rule project"},
	)
	assert other_project_resp.status_code == 201
	other_project_id = other_project_resp.json()["id"]

	editor, _ = await _create_user(client, admin_headers, "editor")

	create_resp = await client.post(
		f"/v1/projects/{project_id}/access/rules",
		headers=owner_headers,
		json={"subject_user_id": editor["id"], "level": "reader"},
	)
	assert create_resp.status_code == 201
	created_rule = create_resp.json()
	rule_id = created_rule["id"]
	assert created_rule["subject_user_id"] == editor["id"]

	list_resp = await client.get(
		f"/v1/projects/{project_id}/access/rules",
		headers=owner_headers,
	)
	assert list_resp.status_code == 200
	assert [rule["id"] for rule in list_resp.json()] == [rule_id]

	get_resp = await client.get(
		f"/v1/projects/{project_id}/access/rules/{rule_id}",
		headers=owner_headers,
	)
	assert get_resp.status_code == 200
	assert get_resp.json()["id"] == rule_id

	wrong_resource_resp = await client.get(
		f"/v1/projects/{other_project_id}/access/rules/{rule_id}",
		headers=owner_headers,
	)
	assert wrong_resource_resp.status_code == 404

	patch_resp = await client.patch(
		f"/v1/projects/{project_id}/access/rules/{rule_id}",
		headers=owner_headers,
		json={"level": "editor", "order_index": 2},
	)
	assert patch_resp.status_code == 200
	patched_rule = patch_resp.json()
	assert patched_rule["level"] == "editor"
	assert patched_rule["order_index"] == 2

	delete_resp = await client.delete(
		f"/v1/projects/{project_id}/access/rules/{rule_id}",
		headers=owner_headers,
	)
	assert delete_resp.status_code == 204

	final_list_resp = await client.get(
		f"/v1/projects/{project_id}/access/rules",
		headers=owner_headers,
	)
	assert final_list_resp.status_code == 200
	assert final_list_resp.json() == []
