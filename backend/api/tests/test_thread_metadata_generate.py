from __future__ import annotations

import pytest
from httpx import AsyncClient

from nokodo_ai.utils.typeid import new_typeid


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

	async def fake_resolve_chat_model(*_args, **_kwargs):
		return object()

	async def fake_run_chat_model_json_schema(*_args, **_kwargs):
		return {"title": "🔧 fix login", "tags": ["auth", "bug"]}

	from api.v1.routers import threads as threads_router
	from api.v1.service import threads as thread_service

	monkeypatch.setattr(
		threads_router,
		"resolve_chat_model",
		fake_resolve_chat_model,
	)
	monkeypatch.setattr(
		thread_service,
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
		json={"replace": False, "model_id": new_typeid("model")},
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

	async def fake_resolve_chat_model(*_args, **_kwargs):
		return object()

	async def fake_run_chat_model_json_schema(*_args, **_kwargs):
		return {"title": "🧠 new title", "tags": ["new"]}

	from api.v1.routers import threads as threads_router
	from api.v1.service import threads as thread_service

	monkeypatch.setattr(
		threads_router,
		"resolve_chat_model",
		fake_resolve_chat_model,
	)
	monkeypatch.setattr(
		thread_service,
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
		json={"replace": False, "model_id": new_typeid("model")},
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

	async def fake_resolve_chat_model(*_args, **_kwargs):
		return object()

	async def fake_run_chat_model_json_schema(*_args, **_kwargs):
		return {"title": "🧠 new title", "tags": ["new"]}

	from api.v1.routers import threads as threads_router
	from api.v1.service import threads as thread_service

	monkeypatch.setattr(
		threads_router,
		"resolve_chat_model",
		fake_resolve_chat_model,
	)
	monkeypatch.setattr(
		thread_service,
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
		json={"replace": True, "model_id": new_typeid("model")},
		headers=headers,
	)
	assert gen_resp.status_code == 200
	data = gen_resp.json()
	assert data["title"] == "🧠 new title"
	assert data["tags"] == ["new"]
