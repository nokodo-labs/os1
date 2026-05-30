from __future__ import annotations

import pytest
from httpx import AsyncClient

from api.v1.service.threads import maintenance as thread_maintenance_service


def _headers(user_auth: dict[str, object]) -> dict[str, str]:
	headers = user_auth["headers"]
	assert isinstance(headers, dict)
	result: dict[str, str] = {}
	for key, value in headers.items():
		assert isinstance(key, str)
		assert isinstance(value, str)
		result[key] = value
	return result


def _user_id(user_auth: dict[str, object]) -> str:
	user = user_auth["user"]
	assert isinstance(user, dict)
	user_id: object = None
	for key, value in user.items():
		assert isinstance(key, str)
		if key == "id":
			user_id = value
	assert isinstance(user_id, str)
	return user_id


@pytest.mark.asyncio
async def test_run_thread_maintenance_fills_missing_metadata_and_summary(
	client: AsyncClient,
	user_auth: dict[str, object],
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	headers = _headers(user_auth)
	user_id = _user_id(user_auth)

	async def fake_resolve_task_chat_model(*_args: object, **_kwargs: object) -> object:
		return object()

	async def fake_run_chat_model_json_schema(
		*_args: object, **_kwargs: object
	) -> dict[str, object]:
		return {
			"title": "fix login",
			"tags": ["auth", "bug"],
			"summary": "the user needed help fixing login.",
			"emoji": "🔧",
		}

	monkeypatch.setattr(
		thread_maintenance_service,
		"resolve_task_chat_model",
		fake_resolve_task_chat_model,
	)
	monkeypatch.setattr(
		thread_maintenance_service,
		"run_chat_model_json_schema",
		fake_run_chat_model_json_schema,
	)

	thread_resp = await client.post(
		"/v1/threads",
		json={"owner_id": user_id, "title": None},
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
		f"/v1/threads/{thread_id}/maintenance/run",
		json={"replace_metadata": False},
		headers=headers,
	)
	assert gen_resp.status_code == 200
	data = gen_resp.json()
	assert data["title"] == "🔧 fix login"
	assert data["tags"] == ["auth", "bug"]

	summary_resp = await client.get(
		f"/v1/threads/{thread_id}/summaries?purpose=catalog&include_superseded=false",
		headers=headers,
	)
	assert summary_resp.status_code == 200
	assert summary_resp.json()[0]["content"] == "the user needed help fixing login."


@pytest.mark.asyncio
async def test_run_thread_maintenance_does_not_replace_existing_metadata(
	client: AsyncClient,
	user_auth: dict[str, object],
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	headers = _headers(user_auth)
	user_id = _user_id(user_auth)

	async def fake_resolve_task_chat_model(*_args: object, **_kwargs: object) -> object:
		return object()

	async def fake_run_chat_model_json_schema(
		*_args: object, **_kwargs: object
	) -> dict[str, object]:
		return {
			"title": "new title",
			"tags": ["new"],
			"summary": "the existing metadata should stay put.",
			"emoji": "🧠",
		}

	monkeypatch.setattr(
		thread_maintenance_service,
		"resolve_task_chat_model",
		fake_resolve_task_chat_model,
	)
	monkeypatch.setattr(
		thread_maintenance_service,
		"run_chat_model_json_schema",
		fake_run_chat_model_json_schema,
	)

	thread_resp = await client.post(
		"/v1/threads",
		json={"owner_id": user_id, "title": "keep"},
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
		f"/v1/threads/{thread_id}/maintenance/run",
		json={"replace_metadata": False},
		headers=headers,
	)
	assert gen_resp.status_code == 200
	data = gen_resp.json()
	assert data["title"] == "keep"
	assert data["tags"] == ["keep"]

	summary_resp = await client.get(
		f"/v1/threads/{thread_id}/summaries?purpose=catalog&include_superseded=false",
		headers=headers,
	)
	assert summary_resp.status_code == 200
	assert summary_resp.json()[0]["content"] == "the existing metadata should stay put."


@pytest.mark.asyncio
async def test_run_thread_maintenance_replaces_metadata_when_requested(
	client: AsyncClient,
	user_auth: dict[str, object],
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	headers = _headers(user_auth)
	user_id = _user_id(user_auth)

	async def fake_resolve_task_chat_model(*_args: object, **_kwargs: object) -> object:
		return object()

	async def fake_run_chat_model_json_schema(
		*_args: object, **_kwargs: object
	) -> dict[str, object]:
		return {
			"title": "new title",
			"tags": ["new"],
			"summary": "the user wanted a replacement title.",
			"emoji": "🧠",
		}

	monkeypatch.setattr(
		thread_maintenance_service,
		"resolve_task_chat_model",
		fake_resolve_task_chat_model,
	)
	monkeypatch.setattr(
		thread_maintenance_service,
		"run_chat_model_json_schema",
		fake_run_chat_model_json_schema,
	)

	thread_resp = await client.post(
		"/v1/threads",
		json={"owner_id": user_id, "title": "keep"},
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
		f"/v1/threads/{thread_id}/maintenance/run",
		json={"replace_metadata": True},
		headers=headers,
	)
	assert gen_resp.status_code == 200
	data = gen_resp.json()
	assert data["title"] == "🧠 new title"
	assert data["tags"] == ["new"]

	summary_resp = await client.get(
		f"/v1/threads/{thread_id}/summaries?purpose=catalog&include_superseded=false",
		headers=headers,
	)
	assert summary_resp.status_code == 200
	assert summary_resp.json()[0]["content"] == "the user wanted a replacement title."
