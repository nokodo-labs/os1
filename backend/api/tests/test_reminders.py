import pytest
from httpx import AsyncClient


async def default_reminder_list_id(
	client: AsyncClient,
	headers: dict[str, str],
) -> str:
	list_res = await client.get("/v1/reminder-lists", headers=headers)
	assert list_res.status_code == 200
	reminder_lists = list_res.json()
	default_list = next(item for item in reminder_lists if item["is_default"])
	return str(default_list["id"])


@pytest.mark.asyncio
async def test_list_reminders_subtasks_is_always_a_list(
	client: AsyncClient,
	user_auth: dict[str, object],
) -> None:
	"""list reminders returns subtasks as [] when absent."""
	headers = user_auth["headers"]
	assert isinstance(headers, dict)
	auth_headers = {str(key): str(value) for key, value in headers.items()}
	list_id = await default_reminder_list_id(client, auth_headers)

	create_res = await client.post(
		f"/v1/reminder-lists/{list_id}/reminders",
		headers=auth_headers,
		json={"title": "parent"},
	)
	assert create_res.status_code == 201
	parent_id = create_res.json()["id"]

	list_res = await client.get(
		f"/v1/reminder-lists/{list_id}/reminders",
		headers=auth_headers,
	)
	assert list_res.status_code == 200
	data = list_res.json()

	parent = next(r for r in data if r["id"] == parent_id)
	assert "subtasks" in parent
	assert isinstance(parent["subtasks"], list)
	assert parent["subtasks"] == []


@pytest.mark.asyncio
async def test_list_reminders_include_subtasks_populates_children(
	client: AsyncClient,
	user_auth: dict[str, object],
) -> None:
	"""include_subtasks eagerly loads nested subtasks."""
	headers = user_auth["headers"]
	assert isinstance(headers, dict)
	auth_headers = {str(key): str(value) for key, value in headers.items()}
	list_id = await default_reminder_list_id(client, auth_headers)

	parent_res = await client.post(
		f"/v1/reminder-lists/{list_id}/reminders",
		headers=auth_headers,
		json={"title": "parent"},
	)
	assert parent_res.status_code == 201
	parent_id = parent_res.json()["id"]

	child_res = await client.post(
		f"/v1/reminder-lists/{list_id}/reminders",
		headers=auth_headers,
		json={"title": "child", "parent_id": parent_id},
	)
	assert child_res.status_code == 201
	child_id = child_res.json()["id"]

	list_res = await client.get(
		f"/v1/reminder-lists/{list_id}/reminders",
		headers=auth_headers,
		params={"include_subtasks": True, "limit": 50},
	)
	assert list_res.status_code == 200
	data = list_res.json()

	parent = next(r for r in data if r["id"] == parent_id)
	assert isinstance(parent["subtasks"], list)
	assert {sub["id"] for sub in parent["subtasks"]} == {child_id}

	assert all(r["id"] != child_id for r in data)


@pytest.mark.asyncio
async def test_reminder_parent_validation_rejects_cycles_and_excess_depth(
	client: AsyncClient,
	user_auth: dict[str, object],
) -> None:
	headers = user_auth["headers"]
	assert isinstance(headers, dict)
	auth_headers = {str(key): str(value) for key, value in headers.items()}
	list_id = await default_reminder_list_id(client, auth_headers)

	parent_res = await client.post(
		f"/v1/reminder-lists/{list_id}/reminders",
		headers=auth_headers,
		json={"title": "parent"},
	)
	assert parent_res.status_code == 201
	parent_id = parent_res.json()["id"]

	child_res = await client.post(
		f"/v1/reminder-lists/{list_id}/reminders",
		headers=auth_headers,
		json={"title": "child", "parent_id": parent_id},
	)
	assert child_res.status_code == 201
	child_id = child_res.json()["id"]

	cycle_res = await client.patch(
		f"/v1/reminder-lists/{list_id}/reminders/{parent_id}",
		headers=auth_headers,
		json={"parent_id": child_id},
	)
	assert cycle_res.status_code == 422

	self_parent_res = await client.patch(
		f"/v1/reminder-lists/{list_id}/reminders/{child_id}",
		headers=auth_headers,
		json={"parent_id": child_id},
	)
	assert self_parent_res.status_code == 422

	other_list_res = await client.post(
		"/v1/reminder-lists",
		headers=auth_headers,
		json={"name": "other"},
	)
	assert other_list_res.status_code == 201
	other_list_id = other_list_res.json()["id"]

	move_child_res = await client.patch(
		f"/v1/reminder-lists/{list_id}/reminders/{child_id}",
		headers=auth_headers,
		json={"list_id": other_list_id},
	)
	assert move_child_res.status_code == 400

	deep_parent_id = parent_id
	for index in range(8):
		deep_res = await client.post(
			f"/v1/reminder-lists/{list_id}/reminders",
			headers=auth_headers,
			json={"title": f"deep {index}", "parent_id": deep_parent_id},
		)
		assert deep_res.status_code == 201
		deep_parent_id = deep_res.json()["id"]

	too_deep_res = await client.post(
		f"/v1/reminder-lists/{list_id}/reminders",
		headers=auth_headers,
		json={"title": "too deep", "parent_id": deep_parent_id},
	)
	assert too_deep_res.status_code == 422
