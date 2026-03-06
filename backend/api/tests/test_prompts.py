"""prompt API tests."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from api.v1.service.prompt_runtime import render_inline_with_prompts


@pytest.mark.asyncio
async def test_prompts_admin_only(
	client: AsyncClient,
	user_auth: dict[str, object],
) -> None:
	"""prompts are admin-only resources."""
	headers = user_auth["headers"]
	assert isinstance(headers, dict)

	resp = await client.get("/v1/prompts", headers=headers)
	assert resp.status_code == 403


@pytest.mark.asyncio
async def test_list_prompts_sorting(
	client: AsyncClient,
	admin_auth: dict[str, object],
) -> None:
	"""list prompts supports server-side sort_by + sort_dir."""
	headers = admin_auth["headers"]
	assert isinstance(headers, dict)

	a = await client.post(
		"/v1/prompts",
		headers=headers,
		json={"command": "a", "content": "a"},
	)
	assert a.status_code == 201

	b = await client.post(
		"/v1/prompts",
		headers=headers,
		json={"command": "b", "content": "b"},
	)
	assert b.status_code == 201

	resp = await client.get(
		"/v1/prompts",
		headers=headers,
		params={"sort_by": "command", "sort_dir": "desc", "limit": 50},
	)
	assert resp.status_code == 200
	items = resp.json()
	assert items[0]["command"] == "b"


@pytest.mark.asyncio
async def test_prompt_create_missing_reference_returns_error(
	client: AsyncClient,
	admin_auth: dict[str, object],
) -> None:
	"""creating a prompt with missing referenced prompt should fail."""
	headers = admin_auth["headers"]
	assert isinstance(headers, dict)

	resp = await client.post(
		"/v1/prompts",
		headers=headers,
		json={"command": "bad", "content": "{{PROMPTS.missing}}"},
	)
	assert resp.status_code == 400
	assert "does not exist" in resp.text


@pytest.mark.asyncio
async def test_prompt_circular_dependency_returns_error(
	client: AsyncClient,
	admin_auth: dict[str, object],
) -> None:
	"""circular prompt references are rejected."""
	headers = admin_auth["headers"]
	assert isinstance(headers, dict)

	b = await client.post(
		"/v1/prompts",
		headers=headers,
		json={"command": "b", "content": "base"},
	)
	assert b.status_code == 201
	b_id = b.json()["id"]

	a = await client.post(
		"/v1/prompts",
		headers=headers,
		json={"command": "a", "content": "{{PROMPTS.b}}"},
	)
	assert a.status_code == 201

	cycle = await client.patch(
		f"/v1/prompts/{b_id}",
		headers=headers,
		json={"content": "{{PROMPTS.a}}"},
	)
	assert cycle.status_code == 400
	assert "circular" in cycle.text


@pytest.mark.asyncio
async def test_prompt_max_depth_returns_error(
	client: AsyncClient,
	admin_auth: dict[str, object],
) -> None:
	"""excessive nesting depth is rejected."""
	headers = admin_auth["headers"]
	assert isinstance(headers, dict)

	# build a chain p0 -> p1 -> ... -> p51 (depth 51)
	end = await client.post(
		"/v1/prompts",
		headers=headers,
		json={"command": "p51", "content": "end"},
	)
	assert end.status_code == 201

	for idx in range(50, -1, -1):
		resp = await client.post(
			"/v1/prompts",
			headers=headers,
			json={
				"command": f"p{idx}",
				"content": f"{{{{PROMPTS.p{idx + 1}}}}}",
			},
		)
		if idx == 0:
			assert resp.status_code == 400
			assert "nesting depth" in resp.text
		else:
			assert resp.status_code == 201


@pytest.mark.asyncio
async def test_prompt_render_with_include_and_variables(
	client: AsyncClient,
	admin_auth: dict[str, object],
	db_session: AsyncSession,
) -> None:
	"""Jinja includes and variables render through the prompt engine."""
	headers = admin_auth["headers"]
	assert isinstance(headers, dict)

	greeting = await client.post(
		"/v1/prompts",
		headers=headers,
		json={"command": "greeting", "content": "Hello {{ name }}"},
	)
	assert greeting.status_code == 201

	inline = "{% include 'greeting' %}!"
	rendered = await render_inline_with_prompts(
		db_session,
		text=inline,
		variables={"name": "Noko"},
	)
	assert rendered == "Hello Noko!"


@pytest.mark.asyncio
async def test_prompt_render_legacy_prompts_syntax(
	client: AsyncClient,
	admin_auth: dict[str, object],
	db_session: AsyncSession,
) -> None:
	"""legacy {{PROMPTS.x}} syntax still works via auto-conversion."""
	headers = admin_auth["headers"]
	assert isinstance(headers, dict)

	inner = await client.post(
		"/v1/prompts",
		headers=headers,
		json={"command": "inner", "content": "Inner"},
	)
	assert inner.status_code == 201

	outer = await client.post(
		"/v1/prompts",
		headers=headers,
		json={"command": "outer", "content": "[{{PROMPTS.inner}}]"},
	)
	assert outer.status_code == 201

	rendered = await render_inline_with_prompts(
		db_session,
		text="{{PROMPTS.outer}}",
	)
	assert rendered == "[Inner]"
