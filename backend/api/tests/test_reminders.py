import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_reminders_subtasks_is_always_a_list(
	client: AsyncClient,
	user_auth: dict[str, object],
) -> None:
	"""list reminders returns subtasks as [] when absent."""
	headers = user_auth["headers"]
	assert isinstance(headers, dict)

	create_res = await client.post(
		"/v1/reminders",
		headers=headers,
		json={"title": "parent"},
	)
	assert create_res.status_code == 201
	parent_id = create_res.json()["id"]

	list_res = await client.get("/v1/reminders", headers=headers)
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

	parent_res = await client.post(
		"/v1/reminders",
		headers=headers,
		json={"title": "parent"},
	)
	assert parent_res.status_code == 201
	parent_id = parent_res.json()["id"]

	child_res = await client.post(
		"/v1/reminders",
		headers=headers,
		json={"title": "child", "parent_id": parent_id},
	)
	assert child_res.status_code == 201
	child_id = child_res.json()["id"]

	list_res = await client.get(
		"/v1/reminders",
		headers=headers,
		params={"include_subtasks": True, "limit": 50},
	)
	assert list_res.status_code == 200
	data = list_res.json()

	parent = next(r for r in data if r["id"] == parent_id)
	assert isinstance(parent["subtasks"], list)
	assert {sub["id"] for sub in parent["subtasks"]} == {child_id}

	assert all(r["id"] != child_id for r in data)
