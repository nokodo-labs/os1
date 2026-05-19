"""Tests for the Open WebUI integration service."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.models.agent import Agent
from api.models.file import File, FileSource
from api.models.memory import Memory
from api.models.message import Message, MessageType
from api.models.note import Note
from api.models.project import Project
from api.models.task import TaskType
from api.models.thread import Thread
from api.models.thread_participant import ThreadParticipant
from api.models.user import User
from api.open_webui import OpenWebUIClient
from api.permissions import ActionPermission, DefaultResourceAccess
from api.settings import OpenWebUIDeployment, settings
from api.v1.routers.integrations import open_webui as owui_router
from api.v1.service import tasks as task_service
from api.v1.service.auth import Principal
from api.v1.service.integrations import open_webui
from api.v1.service.integrations.open_webui import imports as owui_imports
from api.v1.tasks import open_webui as owui_tasks


def _owui_meta(metadata: Mapping[str, object]) -> dict[str, object]:
	value = metadata.get("open-webui")
	assert isinstance(value, dict)
	return {str(key): item for key, item in value.items()}


def _principal(*permissions: ActionPermission) -> Principal:
	user = User(
		email="open-webui-integration@example.com",
		username="open_webui_integration",
		hashed_password="pw",
		is_active=True,
	)
	return Principal(
		user=user,
		group_ids=(),
		role_ids=(),
		permissions=frozenset(permission.value for permission in permissions),
		role_resource_defaults=DefaultResourceAccess(),
	)


async def _persisted_principal(
	session: AsyncSession,
	*permissions: ActionPermission,
	email: str = "open-webui-import@example.com",
	username: str = "open_webui_import",
	is_superuser: bool = False,
) -> Principal:
	user = User(
		email=email,
		username=username,
		hashed_password="pw",
		is_active=True,
		is_superuser=is_superuser,
	)
	session.add(user)
	await session.flush()
	return Principal(
		user=user,
		group_ids=(),
		role_ids=(),
		permissions=frozenset(permission.value for permission in permissions),
		role_resource_defaults=DefaultResourceAccess(),
	)


def _allow_test_deployment(monkeypatch: pytest.MonkeyPatch) -> None:
	monkeypatch.setattr(settings.integrations.open_webui, "enabled", True)
	monkeypatch.setattr(
		settings.integrations.open_webui,
		"deployments",
		[
			OpenWebUIDeployment.model_validate(
				{
					"name": "test",
					"description": "test",
					"origin": "https://open-webui.example.com",
				}
			)
		],
	)


def _install_fake_open_webui_client(
	monkeypatch: pytest.MonkeyPatch,
	folders: list[dict[str, object]] | None = None,
	chats: list[dict[str, object]] | None = None,
	archived_chats: list[dict[str, object]] | None = None,
	memories: list[dict[str, object]] | None = None,
	notes: list[dict[str, object]] | None = None,
	models: list[dict[str, object]] | None = None,
	files: dict[str, tuple[dict[str, object], bytes, str | None]] | None = None,
) -> None:
	class FakeOpenWebUIClient:
		def __init__(self, **kwargs: object) -> None:
			_ = kwargs

		async def __aenter__(self) -> FakeOpenWebUIClient:
			return self

		async def __aexit__(self, *args: object) -> None:
			_ = args

		async def list_folders(self) -> list[dict[str, object]]:
			return folders or []

		async def list_all_chats(
			self,
			include_archived_chats: bool = False,
		) -> list[dict[str, object]]:
			return await self.list_bulk_chats(include_archived_chats)

		async def list_bulk_chats(
			self,
			include_archived_chats: bool = False,
		) -> list[dict[str, object]]:
			items = list(chats or [])
			if include_archived_chats:
				items.extend(archived_chats or [])
			return items

		async def list_chat_refs(
			self,
			include_archived_chats: bool = False,
		) -> list[dict[str, object]]:
			return await self.list_all_chats(include_archived_chats)

		async def get_chat(self, chat_id: str) -> dict[str, object] | None:
			for chat in [*(chats or []), *(archived_chats or [])]:
				if chat.get("id") == chat_id:
					return chat
			return None

		async def list_memories(self) -> list[dict[str, object]]:
			return memories or []

		async def list_models(self) -> list[dict[str, object]]:
			return models or []

		async def list_notes(self) -> list[dict[str, object]]:
			return notes or []

		async def get_file_metadata(self, file_id: str) -> dict[str, object] | None:
			if not files or file_id not in files:
				return None
			return files[file_id][0]

		async def download_file(self, file_id: str) -> tuple[bytes, str | None]:
			if not files or file_id not in files:
				raise AssertionError(f"unexpected file download: {file_id}")
			_, data, content_type = files[file_id]
			return data, content_type

	monkeypatch.setattr(owui_imports, "OpenWebUIClient", FakeOpenWebUIClient)


def _chat_with_messages(
	*,
	chat_id: str = "chat_1",
	folder_id: str | None = None,
	archived: bool = False,
	pinned: bool = False,
	messages: dict[str, dict[str, object]],
	current_id: str,
	models: list[str] | None = None,
) -> dict[str, object]:
	return {
		"id": chat_id,
		"title": "imported chat",
		"folder_id": folder_id,
		"archived": archived,
		"pinned": pinned,
		"created_at": 1_700_000_000,
		"updated_at": 1_700_000_100,
		"chat": {
			"models": models or [],
			"history": {
				"messages": messages,
				"currentId": current_id,
			},
		},
	}


def _all_import_permissions() -> tuple[ActionPermission, ...]:
	return (
		ActionPermission.THREADS_CREATE,
		ActionPermission.PROJECTS_CREATE,
		ActionPermission.FILES_CREATE,
	)


@pytest.mark.asyncio
async def test_open_webui_client_bulk_skips_archived_chats_by_default(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	client = OpenWebUIClient(
		origin="https://open-webui.example.com", credential="token"
	)
	calls: list[str] = []

	async def get_json(
		path: str, params: dict[str, str] | None = None
	) -> list[dict[str, object]]:
		calls.append(f"{path}?{params or {}}")
		return [{"id": "active", "archived": False}]

	monkeypatch.setattr(client, "_get_json", get_json)

	chats = await client.list_all_chats()

	assert calls == ["/api/v1/chats/all?{}"]
	assert chats == [{"id": "active", "archived": False}]


@pytest.mark.asyncio
async def test_open_webui_client_bulk_fetches_archived_chats_when_enabled(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	client = OpenWebUIClient(
		origin="https://open-webui.example.com", credential="token"
	)
	calls: list[str] = []

	async def get_json(
		path: str, params: dict[str, str] | None = None
	) -> list[dict[str, object]]:
		calls.append(f"{path}?{params or {}}")
		if path == "/api/v1/chats/all/archived":
			return [{"id": "archived_chat"}]
		return [{"id": "active", "archived": False}]

	monkeypatch.setattr(client, "_get_json", get_json)

	chats = await client.list_all_chats(include_archived_chats=True)

	assert calls == [
		"/api/v1/chats/all?{}",
		"/api/v1/chats/all/archived?{}",
	]
	assert chats == [
		{"id": "active", "archived": False},
		{"id": "archived_chat", "archived": True},
	]


@pytest.mark.asyncio
async def test_open_webui_client_lists_lightweight_chat_refs(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	client = OpenWebUIClient(
		origin="https://open-webui.example.com", credential="token"
	)
	calls: list[str] = []

	async def get_json(
		path: str, params: dict[str, str] | None = None
	) -> list[dict[str, object]]:
		calls.append(f"{path}?{params or {}}")
		if path == "/api/v1/chats/archived":
			return [{"id": "archived_chat"}]
		return [{"id": "active"}]

	monkeypatch.setattr(client, "_get_json", get_json)

	refs = await client.list_chat_refs(include_archived_chats=True)

	assert calls == [
		"/api/v1/chats/?{'include_pinned': 'true', 'include_folders': 'true'}",
		"/api/v1/chats/archived?{'page': '1'}",
	]
	assert refs == [
		{"id": "active"},
		{"id": "archived_chat", "archived": True},
	]


@pytest.mark.asyncio
async def test_open_webui_client_lists_full_notes(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	client = OpenWebUIClient(
		origin="https://open-webui.example.com", credential="token"
	)
	calls: list[str] = []

	async def get_json(
		path: str, params: dict[str, str] | None = None
	) -> dict[str, object] | list[dict[str, object]]:
		calls.append(f"{path}?{params or {}}")
		if path == "/api/v1/notes/" and params == {"page": "1"}:
			return [{"id": "note_1", "title": "short", "data": {}}]
		if path == "/api/v1/notes/note_1":
			return {
				"id": "note_1",
				"title": "full",
				"data": {"content": {"md": "complete markdown"}},
			}
		return []

	monkeypatch.setattr(client, "_get_json", get_json)

	notes = await client.list_notes()

	assert calls == [
		"/api/v1/notes/?{'page': '1'}",
		"/api/v1/notes/note_1?{}",
	]
	assert notes == [
		{
			"id": "note_1",
			"title": "full",
			"data": {"content": {"md": "complete markdown"}},
		}
	]


@pytest.mark.asyncio
async def test_open_webui_client_lists_models(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	client = OpenWebUIClient(
		origin="https://open-webui.example.com", credential="token"
	)

	async def get_json(
		path: str, params: dict[str, str] | None = None
	) -> dict[str, object]:
		assert path == "/api/models"
		assert params is None
		return {"data": [{"id": "gpt-4.1", "name": "helper"}]}

	monkeypatch.setattr(client, "_get_json", get_json)

	models = await client.list_models()

	assert models == [{"id": "gpt-4.1", "name": "helper"}]


def test_open_webui_sources_require_import_capability() -> None:
	with pytest.raises(HTTPException) as exc:
		open_webui.list_sources(_principal())

	assert exc.value.status_code == 403


def test_open_webui_sources_allow_memory_import_capability() -> None:
	sources = open_webui.list_sources(_principal(ActionPermission.MEMORIES_CREATE))

	assert isinstance(sources.enabled, bool)


def test_open_webui_sources_allow_note_import_capability() -> None:
	sources = open_webui.list_sources(_principal(ActionPermission.NOTES_CREATE))

	assert isinstance(sources.enabled, bool)


@pytest.mark.asyncio
async def test_open_webui_chat_import_requires_thread_permission(
	db_session: AsyncSession,
) -> None:
	with pytest.raises(HTTPException) as exc:
		await open_webui.import_from_open_webui(
			deployment_origin="https://open-webui.example.com",
			credential="token",
			include_chats=True,
			include_memories=False,
			session=db_session,
			principal=_principal(ActionPermission.MEMORIES_CREATE),
		)

	assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_open_webui_memory_import_requires_memory_permission(
	db_session: AsyncSession,
) -> None:
	with pytest.raises(HTTPException) as exc:
		await open_webui.import_from_open_webui(
			deployment_origin="https://open-webui.example.com",
			credential="token",
			include_chats=False,
			include_memories=True,
			session=db_session,
			principal=_principal(ActionPermission.THREADS_CREATE),
		)

	assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_open_webui_note_import_requires_note_permission(
	db_session: AsyncSession,
) -> None:
	with pytest.raises(HTTPException) as exc:
		await open_webui.import_from_open_webui(
			deployment_origin="https://open-webui.example.com",
			credential="token",
			include_chats=False,
			include_memories=False,
			include_notes=True,
			session=db_session,
			principal=_principal(ActionPermission.THREADS_CREATE),
		)

	assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_open_webui_import_converts_folders_to_projects(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	_allow_test_deployment(monkeypatch)
	_install_fake_open_webui_client(
		monkeypatch,
		folders=[
			{"id": "folder_1", "name": "client work", "created_at": 1_700_000_000}
		],
		chats=[
			_chat_with_messages(
				folder_id="folder_1",
				current_id="m2",
				messages={
					"m1": {"id": "m1", "role": "user", "content": "hello"},
					"m2": {
						"id": "m2",
						"parentId": "m1",
						"role": "assistant",
						"content": "hi",
					},
				},
			)
		],
	)
	principal = await _persisted_principal(db_session, *_all_import_permissions())

	summary = await open_webui.import_from_open_webui(
		deployment_origin="https://open-webui.example.com",
		credential="token",
		include_chats=True,
		include_memories=False,
		session=db_session,
		principal=principal,
	)

	project = (
		await db_session.scalars(select(Project).options(selectinload(Project.threads)))
	).one()
	thread = (
		await db_session.scalars(select(Thread).options(selectinload(Thread.projects)))
	).one()
	assert summary.projects_imported == 1
	assert summary.chats_imported == 1
	assert project.name == "client work"
	assert _owui_meta(project.metadata_)["folder_id"] == "folder_1"
	assert thread.projects == [project]
	assert project.threads == [thread]


@pytest.mark.asyncio
async def test_open_webui_import_maps_chat_tags_to_thread_tags(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	_allow_test_deployment(monkeypatch)
	_install_fake_open_webui_client(
		monkeypatch,
		chats=[
			{
				**_chat_with_messages(
					current_id="m1",
					messages={"m1": {"id": "m1", "role": "user", "content": "tags"}},
				),
				"meta": {"tags": ["Client Work", "none", "follow_up"]},
			}
		],
	)
	principal = await _persisted_principal(db_session, *_all_import_permissions())

	await open_webui.import_from_open_webui(
		deployment_origin="https://open-webui.example.com",
		credential="token",
		include_chats=True,
		include_memories=False,
		session=db_session,
		principal=principal,
	)

	thread = (await db_session.scalars(select(Thread))).one()
	assert thread.tags == ["client_work", "follow_up"]
	assert _owui_meta(thread.metadata_)["tags"] == ["client_work", "follow_up"]


@pytest.mark.asyncio
async def test_open_webui_import_placeholder_titles_as_untitled_threads(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	_allow_test_deployment(monkeypatch)
	_install_fake_open_webui_client(
		monkeypatch,
		chats=[
			{
				**_chat_with_messages(
					current_id="m1",
					messages={"m1": {"id": "m1", "role": "user", "content": "hola"}},
				),
				"title": "Nuevo Chat",
			}
		],
	)
	principal = await _persisted_principal(db_session, *_all_import_permissions())

	await open_webui.import_from_open_webui(
		deployment_origin="https://open-webui.example.com",
		credential="token",
		include_chats=True,
		include_memories=False,
		session=db_session,
		principal=principal,
	)

	thread = (await db_session.scalars(select(Thread))).one()
	assert thread.title is None
	assert _owui_meta(thread.metadata_)["untitled"] is True


@pytest.mark.asyncio
async def test_open_webui_import_maps_message_models_to_agents(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	_allow_test_deployment(monkeypatch)
	agent = Agent(
		name="GPT Helper",
		description=None,
		system_prompt=None,
	)
	db_session.add(agent)
	await db_session.flush()
	_install_fake_open_webui_client(
		monkeypatch,
		chats=[
			_chat_with_messages(
				current_id="m2",
				messages={
					"m1": {
						"id": "m1",
						"role": "user",
						"content": "hello",
					},
					"m2": {
						"id": "m2",
						"parentId": "m1",
						"role": "assistant",
						"content": "hi",
					},
				},
				models=["gpt-4.1"],
			)
		],
		models=[{"id": "gpt-4.1", "name": "GPT Helper"}],
	)
	principal = await _persisted_principal(db_session, *_all_import_permissions())

	await open_webui.import_from_open_webui(
		deployment_origin="https://open-webui.example.com",
		credential="token",
		include_chats=True,
		include_memories=False,
		session=db_session,
		principal=principal,
	)

	messages = (
		await db_session.scalars(select(Message).order_by(Message.created_at))
	).all()
	assert len(messages) == 2
	for message in messages:
		metadata = _owui_meta(message.metadata_)
		assert metadata["model_id"] == "gpt-4.1"
		assert metadata["model_name"] == "GPT Helper"
		assert metadata["agent_id"] == str(agent.id)
	assert messages[0].sender_user_id == principal.user_id
	assert messages[0].sender_agent_id is None
	assert messages[1].sender_agent_id == agent.id


@pytest.mark.asyncio
async def test_open_webui_import_skips_archived_chats_by_default(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	_allow_test_deployment(monkeypatch)
	_install_fake_open_webui_client(
		monkeypatch,
		chats=[
			_chat_with_messages(
				chat_id="chat_active",
				current_id="m1",
				messages={"m1": {"id": "m1", "role": "user", "content": "active"}},
			)
		],
		archived_chats=[
			_chat_with_messages(
				chat_id="chat_archived",
				archived=True,
				current_id="m1",
				messages={"m1": {"id": "m1", "role": "user", "content": "archived"}},
			)
		],
	)
	principal = await _persisted_principal(db_session, *_all_import_permissions())

	summary = await open_webui.import_from_open_webui(
		deployment_origin="https://open-webui.example.com",
		credential="token",
		include_chats=True,
		include_memories=False,
		session=db_session,
		principal=principal,
	)

	threads = (await db_session.scalars(select(Thread))).all()
	assert summary.chats_imported == 1
	assert len(threads) == 1
	assert _owui_meta(threads[0].metadata_)["chat_id"] == "chat_active"
	assert threads[0].is_archived is False


@pytest.mark.asyncio
async def test_open_webui_import_archived_chats_when_enabled(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	_allow_test_deployment(monkeypatch)
	_install_fake_open_webui_client(
		monkeypatch,
		archived_chats=[
			_chat_with_messages(
				chat_id="chat_archived",
				archived=True,
				current_id="m1",
				messages={"m1": {"id": "m1", "role": "user", "content": "archived"}},
			)
		],
	)
	principal = await _persisted_principal(db_session, *_all_import_permissions())

	summary = await open_webui.import_from_open_webui(
		deployment_origin="https://open-webui.example.com",
		credential="token",
		include_chats=True,
		include_memories=False,
		session=db_session,
		principal=principal,
		include_archived_chats=True,
	)

	thread = (await db_session.scalars(select(Thread))).one()
	assert summary.chats_imported == 1
	assert _owui_meta(thread.metadata_)["chat_id"] == "chat_archived"
	assert thread.is_archived is True


@pytest.mark.asyncio
async def test_open_webui_import_reports_progress(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	_allow_test_deployment(monkeypatch)
	_install_fake_open_webui_client(
		monkeypatch,
		chats=[
			_chat_with_messages(
				current_id="m1",
				messages={"m1": {"id": "m1", "role": "user", "content": "hello"}},
			)
		],
	)
	principal = await _persisted_principal(db_session, *_all_import_permissions())
	progress_updates: list[tuple[int, str]] = []

	async def progress_callback(progress: int, stage: str) -> None:
		progress_updates.append((progress, stage))

	await open_webui.import_from_open_webui(
		deployment_origin="https://open-webui.example.com",
		credential="token",
		include_chats=True,
		include_memories=False,
		session=db_session,
		principal=principal,
		progress_callback=progress_callback,
	)

	assert (15, "loading folders") in progress_updates
	assert (30, "loading chat list") in progress_updates
	assert any(stage == "importing chat 1/1" for _, stage in progress_updates)
	assert progress_updates[-1] == (90, "finalizing")


@pytest.mark.asyncio
async def test_open_webui_import_places_pinned_chats_in_project(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	_allow_test_deployment(monkeypatch)
	_install_fake_open_webui_client(
		monkeypatch,
		chats=[
			_chat_with_messages(
				pinned=True,
				current_id="m1",
				messages={"m1": {"id": "m1", "role": "user", "content": "pinned"}},
			)
		],
	)
	principal = await _persisted_principal(db_session, *_all_import_permissions())

	summary = await open_webui.import_from_open_webui(
		deployment_origin="https://open-webui.example.com",
		credential="token",
		include_chats=True,
		include_memories=False,
		session=db_session,
		principal=principal,
	)

	project = (
		await db_session.scalars(select(Project).options(selectinload(Project.threads)))
	).one()
	thread = (
		await db_session.scalars(select(Thread).options(selectinload(Thread.projects)))
	).one()
	assert summary.projects_imported == 1
	assert project.name == "pinned chats"
	assert _owui_meta(project.metadata_)["special_project"] == "pinned_chats"
	assert thread.projects == [project]
	assert _owui_meta(thread.metadata_)["pinned"] is True


@pytest.mark.asyncio
async def test_open_webui_import_task_enqueues_taskiq_job(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	_allow_test_deployment(monkeypatch)
	principal = await _persisted_principal(db_session)
	enqueued: list[tuple[str, dict[str, object]]] = []

	async def enqueue_started_task(
		task_id: object,
		runtime_payload: dict[str, object] | None = None,
	) -> None:
		enqueued.append((str(task_id), runtime_payload or {}))

	monkeypatch.setattr(task_service, "enqueue_started_task", enqueue_started_task)

	task = await owui_tasks.spawn_open_webui_import_task(
		db_session,
		principal=principal,
		deployment_origin="https://open-webui.example.com",
		credential="token",
		include_chats=True,
		include_memories=True,
		include_notes=True,
		include_archived_chats=True,
	)

	assert task.task_type == TaskType.IMPORT
	assert (
		task.metadata_[task_service.TASK_NAME_METADATA_KEY]
		== owui_tasks.OPEN_WEBUI_IMPORT_TASK
	)
	assert task.metadata_["integration"] == "open_webui"
	assert task.metadata_["include_notes"] is True
	assert task.metadata_["include_archived_chats"] is True
	assert task.metadata_["chat_import_mode"] == "batched"
	assert task.metadata_["started_by_user_id"] == principal.user_id
	assert enqueued == [(str(task.id), {"credential": "token"})]


@pytest.mark.asyncio
async def test_open_webui_import_task_can_be_started_for_target_user(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	_allow_test_deployment(monkeypatch)
	admin = await _persisted_principal(
		db_session,
		email="owui-admin@example.com",
		username="owui_admin",
		is_superuser=True,
	)
	target = await _persisted_principal(
		db_session,
		email="owui-target@example.com",
		username="owui_target",
	)
	enqueued: list[tuple[str, dict[str, object]]] = []

	async def enqueue_started_task(
		task_id: object,
		runtime_payload: dict[str, object] | None = None,
	) -> None:
		enqueued.append((str(task_id), runtime_payload or {}))

	monkeypatch.setattr(task_service, "enqueue_started_task", enqueue_started_task)

	task = await owui_tasks.spawn_open_webui_import_task(
		db_session,
		principal=target,
		deployment_origin="https://open-webui.example.com",
		credential="token",
		include_chats=True,
		include_memories=True,
		chat_import_mode="bulk",
		started_by_user_id=admin.user_id,
	)

	assert task.user_id == target.user_id
	assert task.metadata_["started_by_user_id"] == admin.user_id
	assert task.metadata_["include_notes"] is False
	assert task.metadata_["chat_import_mode"] == "bulk"
	assert enqueued == [(str(task.id), {"credential": "token"})]


@pytest.mark.asyncio
async def test_open_webui_import_request_resolves_admin_target_user(
	db_session: AsyncSession,
) -> None:
	admin = await _persisted_principal(
		db_session,
		email="owui-resolve-admin@example.com",
		username="owui_resolve_admin",
		is_superuser=True,
	)
	target = await _persisted_principal(
		db_session,
		email="owui-resolve-target@example.com",
		username="owui_resolve_target",
	)
	body = owui_router.OpenWebUIImportRequest.model_validate(
		{
			"deployment_origin": "https://open-webui.example.com",
			"jwt": "token",
			"user_id": target.user_id,
		}
	)

	resolved = await owui_router._resolve_import_principal(body, admin, db_session)

	assert resolved.user_id == target.user_id


@pytest.mark.asyncio
async def test_open_webui_import_request_rejects_non_admin_target_user(
	db_session: AsyncSession,
) -> None:
	principal = await _persisted_principal(
		db_session,
		email="owui-resolve-user@example.com",
		username="owui_resolve_user",
	)
	target = await _persisted_principal(
		db_session,
		email="owui-resolve-denied-target@example.com",
		username="owui_resolve_denied_target",
	)
	body = owui_router.OpenWebUIImportRequest.model_validate(
		{
			"deployment_origin": "https://open-webui.example.com",
			"jwt": "token",
			"user_id": target.user_id,
		}
	)

	with pytest.raises(HTTPException) as exc:
		await owui_router._resolve_import_principal(body, principal, db_session)

	assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_open_webui_import_converts_tool_output_messages(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	_allow_test_deployment(monkeypatch)
	_install_fake_open_webui_client(
		monkeypatch,
		chats=[
			_chat_with_messages(
				current_id="m2",
				messages={
					"m1": {"id": "m1", "role": "user", "content": "search"},
					"m2": {
						"id": "m2",
						"parentId": "m1",
						"role": "assistant",
						"output": [
							{
								"type": "function_call",
								"call_id": "call_1",
								"name": "web_search",
								"arguments": '{"query":"weather"}',
							},
							{
								"type": "function_call_output",
								"call_id": "call_1",
								"output": [{"type": "output_text", "text": "sunny"}],
							},
						],
					},
				},
			)
		],
	)
	principal = await _persisted_principal(db_session, *_all_import_permissions())

	summary = await open_webui.import_from_open_webui(
		deployment_origin="https://open-webui.example.com",
		credential="token",
		include_chats=True,
		include_memories=False,
		session=db_session,
		principal=principal,
	)

	messages = (await db_session.scalars(select(Message))).all()
	assistant = next(
		message for message in messages if message.type == MessageType.ASSISTANT
	)
	tool = next(message for message in messages if message.type == MessageType.TOOL)
	assert summary.messages_imported == 3
	assert assistant.tool_calls == [
		{"id": "call_1", "name": "web_search", "arguments": {"query": "weather"}}
	]
	assert tool.tool_call_id == "call_1"
	assert tool.parent_id == assistant.id
	assert tool.content == [{"type": "text", "text": "sunny"}]


@pytest.mark.asyncio
async def test_open_webui_import_downloads_chat_files_as_attachments(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	_allow_test_deployment(monkeypatch)
	_install_fake_open_webui_client(
		monkeypatch,
		folders=[{"id": "folder_1", "name": "research"}],
		files={
			"file_1": (
				{
					"id": "file_1",
					"filename": "notes.txt",
					"meta": {"content_type": "text/plain"},
				},
				b"hello from owui",
				"text/plain",
			)
		},
		chats=[
			_chat_with_messages(
				folder_id="folder_1",
				current_id="m1",
				messages={
					"m1": {
						"id": "m1",
						"role": "user",
						"content": "see attached",
						"files": [{"id": "file_1", "name": "notes.txt"}],
					}
				},
			)
		],
	)
	principal = await _persisted_principal(db_session, *_all_import_permissions())

	summary = await open_webui.import_from_open_webui(
		deployment_origin="https://open-webui.example.com",
		credential="token",
		include_chats=True,
		include_memories=False,
		session=db_session,
		principal=principal,
	)

	file = (
		await db_session.scalars(select(File).options(selectinload(File.projects)))
	).one()
	message = (await db_session.scalars(select(Message))).one()
	project = (await db_session.scalars(select(Project))).one()
	file_part = next(part for part in message.content if part.get("type") == "file")
	assert summary.files_imported == 1
	assert file.source == FileSource.IMPORT
	assert file.filename == "notes.txt"
	assert file.mime_type == "text/plain"
	assert file.message_id == message.id
	assert file.projects == [project]
	assert file_part["metadata"]["file_id"] == str(file.id)
	assert _owui_meta(file_part["metadata"])["file_id"] == "file_1"


@pytest.mark.asyncio
async def test_open_webui_import_uses_nested_file_metadata_for_filename(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	_allow_test_deployment(monkeypatch)
	_install_fake_open_webui_client(
		monkeypatch,
		files={
			"file_1": (
				{
					"id": "file_1",
					"meta": {
						"content_type": "text/markdown",
						"data": {"name": "nested-notes.md"},
					},
				},
				b"# hello from owui",
				None,
			)
		},
		chats=[
			_chat_with_messages(
				current_id="m1",
				messages={
					"m1": {
						"id": "m1",
						"role": "user",
						"content": "see attached",
						"files": [{"id": "file_1"}],
					}
				},
			)
		],
	)
	principal = await _persisted_principal(db_session, *_all_import_permissions())

	await open_webui.import_from_open_webui(
		deployment_origin="https://open-webui.example.com",
		credential="token",
		include_chats=True,
		include_memories=False,
		session=db_session,
		principal=principal,
	)

	file = (await db_session.scalars(select(File))).one()
	message = (await db_session.scalars(select(Message))).one()
	file_part = next(part for part in message.content if part.get("type") == "file")
	assert file.filename == "nested-notes.md"
	assert file.mime_type == "text/markdown"
	assert file_part["filename"] == "nested-notes.md"


@pytest.mark.asyncio
async def test_open_webui_import_downloads_generated_image_files(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	_allow_test_deployment(monkeypatch)
	_install_fake_open_webui_client(
		monkeypatch,
		files={
			"generated_file": (
				{
					"id": "generated_file",
					"meta": {
						"name": "generated-image.png",
						"content_type": "image/png",
					},
				},
				b"\x89PNG\r\n",
				"image/png",
			)
		},
		chats=[
			_chat_with_messages(
				current_id="m2",
				messages={
					"m1": {"id": "m1", "role": "user", "content": "make an image"},
					"m2": {
						"id": "m2",
						"parentId": "m1",
						"role": "assistant",
						"content": "done",
						"files": [
							{
								"type": "image",
								"url": "/api/v1/files/generated_file/content",
							}
						],
					},
				},
			)
		],
	)
	principal = await _persisted_principal(db_session, *_all_import_permissions())

	summary = await open_webui.import_from_open_webui(
		deployment_origin="https://open-webui.example.com",
		credential="token",
		include_chats=True,
		include_memories=False,
		session=db_session,
		principal=principal,
	)

	assert summary.files_imported == 1
	assert summary.chats_imported == 1
	file = (await db_session.scalars(select(File))).one()
	assistant = (
		await db_session.scalars(
			select(Message).where(Message.type == MessageType.ASSISTANT)
		)
	).one()
	file_part = next(part for part in assistant.content if part.get("type") == "image")
	assert file.filename == "generated-image.png"
	assert file.mime_type == "image/png"
	assert file.message_id == assistant.id
	assert file_part["filename"] == "generated-image.png"
	assert file_part["metadata"]["file_id"] == str(file.id)


@pytest.mark.asyncio
async def test_open_webui_import_skips_failed_file_storage_without_skipping_chat(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	_allow_test_deployment(monkeypatch)
	_install_fake_open_webui_client(
		monkeypatch,
		files={
			"file_1": (
				{
					"id": "file_1",
					"filename": "notes.txt",
					"meta": {"content_type": "text/plain"},
				},
				b"hello from owui",
				"text/plain",
			)
		},
		chats=[
			_chat_with_messages(
				current_id="m1",
				messages={
					"m1": {
						"id": "m1",
						"role": "user",
						"content": "see attached",
						"files": [{"id": "file_1", "name": "notes.txt"}],
					}
				},
			)
		],
	)

	async def fail_store_file(**kwargs: object) -> File:
		_ = kwargs
		raise ValueError(
			"storage backend not registered: 'local'. registered backends: []"
		)

	monkeypatch.setattr(owui_imports, "store_file", fail_store_file)
	principal = await _persisted_principal(db_session, *_all_import_permissions())

	summary = await open_webui.import_from_open_webui(
		deployment_origin="https://open-webui.example.com",
		credential="token",
		include_chats=True,
		include_memories=False,
		session=db_session,
		principal=principal,
	)

	threads = (await db_session.scalars(select(Thread))).all()
	messages = (await db_session.scalars(select(Message))).all()
	files = (await db_session.scalars(select(File))).all()
	assert summary.chats_imported == 1
	assert summary.files_imported == 0
	assert summary.files_skipped == 1
	assert summary.errors is not None
	assert len(summary.errors) == 1
	assert len(threads) == 1
	assert len(messages) == 1
	assert files == []


@pytest.mark.asyncio
async def test_open_webui_import_preserves_timestamps_and_marks_thread_read(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	_allow_test_deployment(monkeypatch)
	_install_fake_open_webui_client(
		monkeypatch,
		chats=[
			{
				**_chat_with_messages(
					current_id="m2",
					messages={
						"m1": {
							"id": "m1",
							"role": "user",
							"content": "hello",
							"timestamp": "2023-11-14T22:13:20Z",
						},
						"m2": {
							"id": "m2",
							"parentId": "m1",
							"role": "assistant",
							"content": "hi",
							"timestamp": 1_700_000_200_000,
						},
					},
				),
				"created_at": "2023-11-14T22:13:00Z",
				"updated_at": 1_700_000_200_000,
			}
		],
	)
	principal = await _persisted_principal(db_session, *_all_import_permissions())

	await open_webui.import_from_open_webui(
		deployment_origin="https://open-webui.example.com",
		credential="token",
		include_chats=True,
		include_memories=False,
		session=db_session,
		principal=principal,
	)

	thread = (await db_session.scalars(select(Thread))).one()
	participant = (await db_session.scalars(select(ThreadParticipant))).one()
	messages = (
		await db_session.scalars(select(Message).order_by(Message.created_at))
	).all()
	created_at = datetime(2023, 11, 14, 22, 13, tzinfo=UTC)
	updated_at = datetime(2023, 11, 14, 22, 16, 40, tzinfo=UTC)
	assert thread.created_at == created_at
	assert thread.updated_at == updated_at
	assert thread.last_activity_at == updated_at
	assert messages[0].created_at == datetime(2023, 11, 14, 22, 13, 20, tzinfo=UTC)
	assert messages[1].created_at == updated_at
	assert thread.current_message_id == messages[1].id
	assert participant.last_read_message_id == messages[1].id


@pytest.mark.asyncio
async def test_open_webui_import_deduplicates_chats_projects_messages_and_files(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	_allow_test_deployment(monkeypatch)
	_install_fake_open_webui_client(
		monkeypatch,
		folders=[{"id": "folder_1", "name": "research"}],
		files={
			"file_1": (
				{
					"id": "file_1",
					"filename": "notes.txt",
					"meta": {"content_type": "text/plain"},
				},
				b"hello from owui",
				"text/plain",
			)
		},
		chats=[
			_chat_with_messages(
				chat_id="chat_1",
				folder_id="folder_1",
				current_id="m1",
				messages={
					"m1": {
						"id": "m1",
						"role": "user",
						"content": "see attached",
						"files": [{"id": "file_1", "name": "notes.txt"}],
					}
				},
			)
		],
	)
	principal = await _persisted_principal(db_session, *_all_import_permissions())

	first = await open_webui.import_from_open_webui(
		deployment_origin="https://open-webui.example.com",
		credential="token",
		include_chats=True,
		include_memories=False,
		session=db_session,
		principal=principal,
	)
	second = await open_webui.import_from_open_webui(
		deployment_origin="https://open-webui.example.com",
		credential="token",
		include_chats=True,
		include_memories=False,
		session=db_session,
		principal=principal,
	)

	projects = (await db_session.scalars(select(Project))).all()
	threads = (await db_session.scalars(select(Thread))).all()
	messages = (await db_session.scalars(select(Message))).all()
	files = (await db_session.scalars(select(File))).all()
	assert first.projects_imported == 1
	assert first.chats_imported == 1
	assert first.messages_imported == 1
	assert first.files_imported == 1
	assert second.projects_imported == 0
	assert second.projects_skipped == 1
	assert second.chats_imported == 0
	assert second.chats_skipped == 1
	assert second.messages_imported == 0
	assert second.files_imported == 0
	assert len(projects) == 1
	assert len(threads) == 1
	assert len(messages) == 1
	assert len(files) == 1
	assert _owui_meta(projects[0].metadata_)["id"] == "folder_1"
	assert _owui_meta(threads[0].metadata_)["id"] == "chat_1"
	assert _owui_meta(messages[0].metadata_)["message_id"] == "m1"
	assert _owui_meta(files[0].metadata_)["id"] == "file_1"


@pytest.mark.asyncio
async def test_open_webui_import_deduplicates_memories(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	_allow_test_deployment(monkeypatch)
	_install_fake_open_webui_client(
		monkeypatch,
		memories=[{"id": "memory_1", "content": "likes concise imports"}],
	)
	principal = await _persisted_principal(db_session, ActionPermission.MEMORIES_CREATE)

	first = await open_webui.import_from_open_webui(
		deployment_origin="https://open-webui.example.com",
		credential="token",
		include_chats=False,
		include_memories=True,
		session=db_session,
		principal=principal,
	)
	second = await open_webui.import_from_open_webui(
		deployment_origin="https://open-webui.example.com",
		credential="token",
		include_chats=False,
		include_memories=True,
		session=db_session,
		principal=principal,
	)

	memories = (await db_session.scalars(select(Memory))).all()
	assert first.memories_imported == 1
	assert second.memories_imported == 0
	assert second.memories_skipped == 1
	assert len(memories) == 1
	assert _owui_meta(memories[0].metadata_)["id"] == "memory_1"


@pytest.mark.asyncio
async def test_open_webui_import_deduplicates_notes(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	_allow_test_deployment(monkeypatch)
	_install_fake_open_webui_client(
		monkeypatch,
		notes=[
			{
				"id": "note_1",
				"title": "weekly plan",
				"data": {"content": {"md": "- ship imports"}},
				"meta": {"labels": ["Planning"]},
				"is_pinned": True,
				"created_at": 1_700_000_000_000_000_000,
				"updated_at": 1_700_000_100_000_000_000,
			}
		],
	)
	principal = await _persisted_principal(db_session, ActionPermission.NOTES_CREATE)

	first = await open_webui.import_from_open_webui(
		deployment_origin="https://open-webui.example.com",
		credential="token",
		include_chats=False,
		include_memories=False,
		include_notes=True,
		session=db_session,
		principal=principal,
	)
	second = await open_webui.import_from_open_webui(
		deployment_origin="https://open-webui.example.com",
		credential="token",
		include_chats=False,
		include_memories=False,
		include_notes=True,
		session=db_session,
		principal=principal,
	)

	notes = (await db_session.scalars(select(Note))).all()
	assert first.notes_imported == 1
	assert second.notes_imported == 0
	assert second.notes_skipped == 1
	assert len(notes) == 1
	assert notes[0].title == "weekly plan"
	assert notes[0].content == "- ship imports"
	assert notes[0].labels == ["planning"]
	assert notes[0].created_at == datetime(2023, 11, 14, 22, 13, 20, tzinfo=UTC)
	assert notes[0].updated_at == datetime(2023, 11, 14, 22, 15, tzinfo=UTC)
	assert _owui_meta(notes[0].metadata_)["id"] == "note_1"
	assert _owui_meta(notes[0].metadata_)["is_pinned"] is True
