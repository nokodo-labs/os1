from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient

from api.v1.service.threads import metadata as thread_metadata_service


@pytest.mark.asyncio
async def test_generate_thread_metadata_fills_missing(
	client: AsyncClient,
	user_auth: dict[str, object],
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	headers = user_auth["headers"]
	assert isinstance(headers, dict)
	user = user_auth["user"]
	assert isinstance(user, dict)

	async def fake_resolve_task_chat_model(*_args: object, **_kwargs: object) -> Any:
		return object()

	async def fake_run_chat_model_json_schema(
		*_args: object, **_kwargs: object
	) -> dict[str, object]:
		return {"title": "🔧 fix login", "tags": ["auth", "bug"]}

	monkeypatch.setattr(
		thread_metadata_service,
		"resolve_task_chat_model",
		fake_resolve_task_chat_model,
	)
	monkeypatch.setattr(
		thread_metadata_service,
		"run_chat_model_json_schema",
		fake_run_chat_model_json_schema,
	)

	thread_resp = await client.post(
		"/v1/threads",
		json={"owner_id": user["id"], "title": None},
		headers=headers,
	)
	assert thread_resp.status_code == 201
	thread_id = thread_resp.json()["id"]

	assistant_resp = await client.post(
		f"/v1/threads/{thread_id}/messages",
		json={"type": "assistant", "content": "hello"},
		headers=headers,
	)
	assert assistant_resp.status_code == 201

	gen_resp = await client.post(
		f"/v1/threads/{thread_id}/metadata/generate",
		json={"replace": False},
		headers=headers,
	)
	assert gen_resp.status_code == 200
	data = gen_resp.json()
	assert data["title"] == "🔧 fix login"
	assert data["tags"] == ["auth", "bug"]


@pytest.mark.asyncio
async def test_generate_thread_metadata_does_not_replace_when_fill_missing(
	client: AsyncClient,
	user_auth: dict[str, object],
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	headers = user_auth["headers"]
	assert isinstance(headers, dict)
	user = user_auth["user"]
	assert isinstance(user, dict)

	async def fake_resolve_task_chat_model(*_args: object, **_kwargs: object) -> Any:
		return object()

	async def fake_run_chat_model_json_schema(
		*_args: object, **_kwargs: object
	) -> dict[str, object]:
		return {"title": "🧠 new title", "tags": ["new"]}

	monkeypatch.setattr(
		thread_metadata_service,
		"resolve_task_chat_model",
		fake_resolve_task_chat_model,
	)
	monkeypatch.setattr(
		thread_metadata_service,
		"run_chat_model_json_schema",
		fake_run_chat_model_json_schema,
	)

	thread_resp = await client.post(
		"/v1/threads",
		json={"owner_id": user["id"], "title": "keep"},
		headers=headers,
	)
	assert thread_resp.status_code == 201
	thread_id = thread_resp.json()["id"]

	patch_resp = await client.patch(
		f"/v1/threads/{thread_id}",
		json={"tags": ["keep"]},
		headers=headers,
	)
	assert patch_resp.status_code == 200

	assistant_resp = await client.post(
		f"/v1/threads/{thread_id}/messages",
		json={"type": "assistant", "content": "hello"},
		headers=headers,
	)
	assert assistant_resp.status_code == 201

	gen_resp = await client.post(
		f"/v1/threads/{thread_id}/metadata/generate",
		json={"replace": False},
		headers=headers,
	)
	assert gen_resp.status_code == 200
	data = gen_resp.json()
	assert data["title"] == "keep"
	assert data["tags"] == ["keep"]


@pytest.mark.asyncio
async def test_generate_thread_metadata_replaces_when_replace_true(
	client: AsyncClient,
	user_auth: dict[str, object],
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	headers = user_auth["headers"]
	assert isinstance(headers, dict)
	user = user_auth["user"]
	assert isinstance(user, dict)

	async def fake_resolve_task_chat_model(*_args: object, **_kwargs: object) -> Any:
		return object()

	async def fake_run_chat_model_json_schema(
		*_args: object, **_kwargs: object
	) -> dict[str, object]:
		return {"title": "🧠 new title", "tags": ["new"]}

	monkeypatch.setattr(
		thread_metadata_service,
		"resolve_task_chat_model",
		fake_resolve_task_chat_model,
	)
	monkeypatch.setattr(
		thread_metadata_service,
		"run_chat_model_json_schema",
		fake_run_chat_model_json_schema,
	)

	thread_resp = await client.post(
		"/v1/threads",
		json={"owner_id": user["id"], "title": "keep"},
		headers=headers,
	)
	assert thread_resp.status_code == 201
	thread_id = thread_resp.json()["id"]

	patch_resp = await client.patch(
		f"/v1/threads/{thread_id}",
		json={"tags": ["keep"]},
		headers=headers,
	)
	assert patch_resp.status_code == 200

	assistant_resp = await client.post(
		f"/v1/threads/{thread_id}/messages",
		json={"type": "assistant", "content": "hello"},
		headers=headers,
	)
	assert assistant_resp.status_code == 201

	gen_resp = await client.post(
		f"/v1/threads/{thread_id}/metadata/generate",
		json={"replace": True},
		headers=headers,
	)
	assert gen_resp.status_code == 200
	data = gen_resp.json()
	assert data["title"] == "🧠 new title"
	assert data["tags"] == ["new"]
