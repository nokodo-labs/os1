"""Targeted coverage for API modules."""

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from api.models.agent import Agent as AgentORM
from api.models.message import (
	AssistantMessage as AssistantMessageORM,
)
from api.models.message import (
	Message as MessageORM,
)
from api.models.message import MessageType as MessageTypeORM
from api.models.message import (
	SystemMessage as SystemMessageORM,
)
from api.models.message import (
	ToolMessage as ToolMessageORM,
)
from api.models.message import (
	UserMessage as UserMessageORM,
)
from api.models.model import Model as ModelORM
from api.models.provider import Provider as ProviderORM
from api.models.thread import Thread as ThreadORM
from api.schemas.message import MessageCreate
from api.schemas.prompt import PromptListFilters
from api.schemas.runs import RunRequest
from api.schemas.thread import Thread as ThreadSchema
from api.schemas.thread import ThreadListFilters
from api.v1.routers import openai as openai_router
from api.v1.routers import prompts as prompts_router
from api.v1.routers import runs as runs_router
from api.v1.routers import threads as threads_router
from api.v1.service.agents import runtime as agent_runtime
from api.v1.service.authorization import require_thread_access
from api.v1.service.chat import models as chat_service
from api.v1.service.chat.tools import external as external_tools
from api.v1.service.plugins import ResolvedPlugins
from api.v1.service.prompts import external as prompt_external
from api.v1.service.prompts import runtime as prompt_runtime
from api.v1.service.prompts import service as prompt_service
from api.v1.service.threads.common import ensure_admin_for_hidden_or_deleted
from api.v1.service.threads.drafts import MessageDraft
from nokodo_ai.messages import (
	AssistantMessage,
	SystemMessage,
	ToolMessage,
	Usage,
	UserMessage,
)
from nokodo_ai.utils.typeid import TypeID, new_typeid


class _FakePrincipal:
	def __init__(
		self,
		is_admin: bool = False,
		user_id: str = "user",
		groups: list[str] | None = None,
	) -> None:
		self.subject = SimpleNamespace(id=user_id, is_superuser=is_admin)
		self.user = self.subject
		self.group_ids = groups or []
		self.role_ids = ()
		self.role_resource_defaults: dict[str, str] = {}
		self.global_action_permissions: frozenset[str] = frozenset()

	def has_permission(self, permission: str) -> bool:
		if self.user.is_superuser:
			return True
		return permission == "any"

	def has_default_access(
		self, resource_type: object, required_level: object = None
	) -> bool:
		return self.user.is_superuser

	def is_resource_operator(self, resource_type: object) -> bool:
		return self.user.is_superuser


class _FakeResult:
	def __init__(self, value: object) -> None:
		self.value = value

	def scalar_one_or_none(self) -> object:
		return self.value

	def scalars(self) -> _FakeResult:  # type: ignore[override]
		return self

	def one_or_none(self) -> object:  # type: ignore[override]
		return self.value

	def first(self) -> object:  # type: ignore[override]
		return self.value

	def all(self) -> list[object]:  # type: ignore[override]
		if isinstance(self.value, list):
			return self.value
		return [self.value] if self.value is not None else []


class _FakeSession:
	def __init__(self, value: object | None = None) -> None:
		self.value = value
		self.last_stmt: object = None
		self.added: list[object] = []
		self.deleted: list[object] = []
		# every real session carries one, and the post-commit queue lives in it
		# (`enqueue_post_commit_action`). a service that enqueues repairable
		# after-commit work would otherwise fail here for the fake's reasons
		# rather than its own.
		self.info: dict[object, object] = {}

	async def execute(self, stmt: object, *_: object, **__: object) -> _FakeResult:  # type: ignore[override]
		self.last_stmt = stmt
		return _FakeResult(self.value)

	async def get(self, *_args: object, **_kwargs: object) -> object:  # type: ignore[override]
		return self.value

	async def commit(self) -> None:
		return None

	async def refresh(self, *_args: object, **_kwargs: object) -> None:  # type: ignore[override]
		return None

	async def flush(self) -> None:  # type: ignore[override]
		return None

	def add(self, obj: object) -> None:  # type: ignore[override]
		self.added.append(obj)

	async def delete(self, obj: object) -> None:  # type: ignore[override]
		self.deleted.append(obj)


async def _empty_branch(*_args: object, **_kwargs: object) -> list[object]:
	return []


async def _resolved_model(*_args: object, **_kwargs: object) -> str:
	return "local:model"


@pytest.mark.asyncio
async def test_openai_router_uses_chat_model(monkeypatch: pytest.MonkeyPatch) -> None:
	captured: dict[str, Any] = {}

	class FakeAssistant:
		def __init__(self) -> None:
			self.text = "hi"
			self.usage = Usage(input_tokens=1, output_tokens=2, total_tokens=3)
			self.finish_reason = "length"

	class FakeChatModel:
		@classmethod
		def create(cls, model_name: str, *_: object, **__: object) -> FakeChatModel:
			captured["model"] = model_name
			return cls()

		async def generate(
			self,
			messages: list[object],
			stream: bool,
			params: object | None = None,
		) -> object:
			captured["messages"] = messages
			captured["stream"] = stream
			captured["params"] = params
			return FakeAssistant()

	monkeypatch.setattr(openai_router, "ChatModel", FakeChatModel)

	req = openai_router.OpenAIChatCompletionRequest(
		model="gpt",
		messages=[openai_router.OpenAIChatMessage(role="user", content="hi")],
		temperature=0.1,
		max_tokens=5,
	)
	principal = _FakePrincipal()

	resp = await openai_router.chat_completions(req, principal=principal, db=None)  # type: ignore[arg-type]

	assert resp.model == "gpt"
	assert captured["stream"] is False
	assert captured["params"] == {"temperature": 0.1, "max_tokens": 5}
	assert resp.usage.total_tokens == 3
	# a truncated answer is reported as truncated: the compat client has no
	# other channel to learn it, since this endpoint neither streams nor errors.
	assert resp.choices[0].finish_reason == "length"


@pytest.mark.asyncio
async def test_openai_router_handles_all_roles(monkeypatch: pytest.MonkeyPatch) -> None:
	captured: dict[str, Any] = {}

	class FakeAssistant:
		def __init__(self) -> None:
			self.text = "ok"
			self.usage = None
			self.finish_reason = "completed"

	class FakeChatModel:
		@classmethod
		def create(cls, *_args: object, **_kwargs: object) -> FakeChatModel:
			return cls()

		async def generate(
			self,
			messages: list[object],
			stream: bool,
			params: object | None = None,
		) -> object:
			captured["messages"] = messages
			captured["stream"] = stream
			captured["params"] = params
			return FakeAssistant()

	monkeypatch.setattr(openai_router, "ChatModel", FakeChatModel)

	req = openai_router.OpenAIChatCompletionRequest(
		model="gpt",
		messages=[
			openai_router.OpenAIChatMessage(role="system", content="sys"),
			openai_router.OpenAIChatMessage(role="assistant", content="asst"),
			openai_router.OpenAIChatMessage(role="user", content="hi"),
		],
	)
	resp = await openai_router.chat_completions(
		req,
		principal=_FakePrincipal(),  # type: ignore[arg-type]
		db=None,  # type: ignore[arg-type]
	)  # type: ignore[arg-type]

	assert [m.role for m in captured["messages"]] == ["system", "assistant", "user"]
	assert captured["stream"] is False
	assert resp.usage.total_tokens == 0
	assert resp.choices[0].finish_reason == "stop"


@pytest.mark.asyncio
async def test_prompts_router_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
	fake_prompt = SimpleNamespace(id="1", command="/a", content="hi")
	admin = _FakePrincipal(is_admin=True)

	async def fake_create(prompt_in: object, db: object, principal: object) -> object:
		return fake_prompt

	async def fake_list(
		db: object,
		principal: object,
		skip: int = 0,
		limit: int = 50,
		sort_by: str = "command",
		sort_dir: str = "asc",
		filters: PromptListFilters | None = None,
	) -> list[object]:
		return [fake_prompt]

	async def fake_get(prompt_id: object, db: object, principal: object) -> object:
		return fake_prompt

	async def fake_update(
		prompt_id: object, prompt_in: object, db: object, principal: object
	) -> object:
		return fake_prompt

	async def fake_delete(prompt_id: object, db: object, principal: object) -> None:
		fake_delete.called = prompt_id  # type: ignore[attr-defined]

	monkeypatch.setattr(prompts_router, "create_prompt_service", fake_create)
	monkeypatch.setattr(prompts_router, "list_prompts_service", fake_list)
	monkeypatch.setattr(prompts_router, "get_prompt_service", fake_get)
	monkeypatch.setattr(prompts_router, "update_prompt_service", fake_update)  # type: ignore[arg-type]
	monkeypatch.setattr(prompts_router, "delete_prompt_service", fake_delete)

	out_create = await prompts_router.create_prompt(
		fake_prompt,  # type: ignore[arg-type]
		principal=admin,  # type: ignore[arg-type]
		db=None,  # type: ignore[arg-type]
	)  # type: ignore[arg-type]
	out_list = await prompts_router.list_prompts(
		filters=PromptListFilters(), principal=admin, db=None
	)  # type: ignore[arg-type]
	out_get = await prompts_router.get_prompt("1", principal=admin, db=None)  # type: ignore[arg-type]
	out_update = await prompts_router.update_prompt(
		"1",  # type: ignore[arg-type]
		fake_prompt,  # type: ignore[arg-type]
		principal=admin,  # type: ignore[arg-type]
		db=None,  # type: ignore[arg-type]
	)  # type: ignore[arg-type]
	await prompts_router.delete_prompt("1", principal=admin, db=None)  # type: ignore[arg-type]

	assert out_create is fake_prompt
	assert out_list == [fake_prompt]
	assert out_get is fake_prompt
	assert out_update is fake_prompt
	assert fake_delete.called == "1"  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_threads_router_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
	principal = _FakePrincipal()
	_now = datetime.now(UTC)
	fake_thread = ThreadORM(
		id=new_typeid("thread"),
		owner_id=new_typeid("user"),
		title="t",
		tags=[],
		is_temporary=False,
		current_message_id=None,
		last_activity_at=_now,
		created_at=_now,
		updated_at=_now,
		metadata_={},
	)
	fake_thread.projects = []
	fake_thread.participants = []
	fake_message = SimpleNamespace(
		id=new_typeid("message"),
		thread_id=new_typeid("thread"),
		created_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
		updated_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
		content=[],
		tool_calls=[],
		usage=None,
		metadata_={},
		parent_id=None,
		task_id=None,
		sender_agent_id=None,
		sender_user_id=None,
	)

	async def _return_thread(*_args: object, **_kwargs: object) -> object:
		return fake_thread

	async def _return_thread_list(*_args: object, **_kwargs: object) -> list[object]:
		return [fake_thread]

	async def _return_message_list(*_args: object, **_kwargs: object) -> list[object]:
		return [fake_message]

	async def _return_message(*_args: object, **_kwargs: object) -> object:
		return fake_message

	async def _return_run(*_args: object, **_kwargs: object) -> object:
		return fake_message, [fake_message]

	async def _switch(*_args: object, **_kwargs: object) -> object:
		return SimpleNamespace(current_message_id=new_typeid("message"))

	async def _return_payload_list(*_args: object, **_kwargs: object) -> list[object]:
		return [ThreadSchema.model_validate(fake_thread)]

	monkeypatch.setattr(threads_router, "create_thread_service", _return_thread)
	monkeypatch.setattr(threads_router, "thread_payloads", _return_payload_list)
	monkeypatch.setattr(threads_router, "list_threads_service", _return_thread_list)
	monkeypatch.setattr(threads_router, "get_thread_payload", _return_thread)
	monkeypatch.setattr(threads_router, "update_thread_service", _return_thread)
	monkeypatch.setattr(threads_router, "list_messages_service", _return_message_list)

	async def _return_branch_page(*_args: object, **_kwargs: object) -> object:
		return SimpleNamespace(
			messages=[fake_message],
			total=1,
			skip=0,
			has_toward_root=False,
			has_toward_leaf=False,
			siblings=[],
			sibling_counts=[],
			cursor_toward_root=None,
			cursor_toward_leaf=None,
		)

	monkeypatch.setattr(threads_router, "get_branch_page_service", _return_branch_page)
	monkeypatch.setattr(threads_router, "list_message_tree", _return_message_list)
	monkeypatch.setattr(
		threads_router,
		"create_message_and_dispatch_invocations",
		_return_message,
	)
	monkeypatch.setattr(threads_router, "switch_branch_service", _switch)
	created = await threads_router.create_thread(
		SimpleNamespace(owner_id="u"),  # type: ignore[arg-type]
		principal=principal,  # type: ignore[arg-type]
		db=None,  # type: ignore[arg-type]
	)  # type: ignore[arg-type]
	listed = await threads_router.list_threads(  # type: ignore[arg-type]
		filters=ThreadListFilters(),
		principal=principal,  # type: ignore[arg-type]
		db=None,  # type: ignore[arg-type]
	)
	fetched = await threads_router.get_thread("t", principal=principal, db=None)  # type: ignore[arg-type]
	updated = await threads_router.update_thread(  # type: ignore[arg-type]
		"t",  # type: ignore[arg-type]
		SimpleNamespace(),  # type: ignore[arg-type]
		principal=principal,  # type: ignore[arg-type]
		db=None,  # type: ignore[arg-type]
	)  # type: ignore[arg-type]
	messages = await threads_router.list_messages("t", principal=principal, db=None)  # type: ignore[arg-type]
	branch = await threads_router.get_branch_page("t", principal=principal, db=None)  # type: ignore[arg-type]
	tree = await threads_router.get_message_tree(
		"t",  # type: ignore[arg-type]
		principal=_FakePrincipal(is_admin=True),  # type: ignore[arg-type]
		db=None,  # type: ignore[arg-type]
	)
	posted = await threads_router.create_message(  # type: ignore[arg-type]
		"t",  # type: ignore[arg-type]
		MessageCreate(content="x"),
		principal=principal,  # type: ignore[arg-type]
		db=None,  # type: ignore[arg-type]
	)  # type: ignore[arg-type]
	switched = await threads_router.switch_branch(  # type: ignore[arg-type]
		"t",  # type: ignore[arg-type]
		SimpleNamespace(message_id="m"),  # type: ignore[arg-type]
		principal=principal,  # type: ignore[arg-type]
		db=None,  # type: ignore[arg-type]
	)  # type: ignore[arg-type]
	# create + list embed participants via build_thread_payload, so these are
	# schema payloads rather than the raw ORM objects the service returned.
	assert isinstance(created, ThreadSchema)
	assert created.id == fake_thread.id
	assert [t.id for t in listed] == [fake_thread.id]
	assert all(isinstance(t, ThreadSchema) for t in listed)
	assert fetched is fake_thread
	assert updated.id == fake_thread.id
	assert [m.id for m in messages] == [fake_message.id]
	assert [m.id for m in branch.messages] == [fake_message.id]
	assert branch.total == 1
	assert [m.id for m in tree] == [fake_message.id]
	assert posted.id == fake_message.id
	assert switched.current_message_id is not None


@pytest.mark.asyncio
async def test_runs_router_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
	principal = _FakePrincipal()

	async def _fake_stream() -> AsyncGenerator[bytes]:
		if False:
			yield b""

	async def _fake_launch_thread_run(*_args: object, **_kwargs: object) -> TypeID:
		return TypeID(new_typeid("run"))

	monkeypatch.setattr(
		runs_router,
		"launch_thread_run",
		_fake_launch_thread_run,
	)
	monkeypatch.setattr(
		runs_router,
		"subscribe_run_stream",
		lambda _run_id, _subscriber_id: _fake_stream(),
	)

	run_resp = await runs_router.create_run(
		RunRequest(
			agent_id=new_typeid("agent"),
			thread_id=new_typeid("thread"),
		),
		principal=principal,  # type: ignore[arg-type]
		db=None,  # type: ignore[arg-type]
	)
	assert run_resp.media_type == "text/event-stream"
	assert run_resp.headers.get("X-Accel-Buffering") == "no"


@pytest.mark.asyncio
async def test_authorization_require_thread_access() -> None:  # type: ignore[arg-type]
	principal = _FakePrincipal(is_admin=True)  # type: ignore[arg-type]
	fake_session = _FakeSession("ok")

	await require_thread_access(
		"thread",  # type: ignore[arg-type]
		fake_session,  # type: ignore[arg-type]
		principal,  # type: ignore[arg-type]
		include_deleted=True,
	)

	assert fake_session.last_stmt._execution_options.get("include_deleted") is True  # type: ignore[attr-defined]
	# type: ignore[arg-type]
	fake_session_none = _FakeSession(None)  # type: ignore[arg-type]

	with pytest.raises(HTTPException) as exc:
		await require_thread_access(
			TypeID("thread"),
			fake_session_none,  # type: ignore[arg-type]
			principal,  # type: ignore[arg-type]
		)
	assert exc.value.status_code == 404


def test_prompt_runtime_validation_errors() -> None:
	with pytest.raises(prompt_runtime.PromptValidationError):
		prompt_runtime.render_prompt_from_map({}, command="/missing")

	with pytest.raises(prompt_runtime.PromptValidationError) as exc:
		prompt_runtime.validate_prompt_content(
			all_prompts=[],
			command="/a",
			content="{{ PROMPTS.b }} {% include 'a' %}",
		)  # type: ignore[arg-type]
	assert "does not exist" in str(exc.value)

	with pytest.raises(prompt_runtime.PromptValidationError) as exc:
		prompt_runtime.validate_prompt_content(
			all_prompts=[
				SimpleNamespace(id="1", command="/a", content="{{ PROMPTS.a }}")  # type: ignore[list-item]
			],
			command="/a",
			content="{{ PROMPTS.a }}",
		)
	assert "circular" in str(exc.value)


def test_prompt_runtime_template_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
	def _fake_env(_map: object) -> object:
		class _Env:
			def get_template(self, *_args: object, **_kwargs: object) -> None:
				raise prompt_runtime.TemplateNotFound("missing")

		return _Env()

	monkeypatch.setattr(prompt_runtime, "_build_env", _fake_env)

	with pytest.raises(prompt_runtime.PromptValidationError):
		prompt_runtime.render_prompt_from_map({"a": "hi"}, command="/a")


@pytest.mark.asyncio
async def test_prompt_runtime_render_from_db(monkeypatch: pytest.MonkeyPatch) -> None:
	async def exec_prompts(_stmt: object) -> _FakeResult:  # type: ignore[arg-type]
		return _FakeResult([("/cmd", "body")])

	session = _FakeSession()
	session.execute = exec_prompts  # type: ignore[assignment]

	rendered = await prompt_runtime.render_prompt_from_db(session, command="/cmd")  # type: ignore[arg-type]
	assert rendered == "body"


@pytest.mark.asyncio
async def test_prompts_service_validation_paths(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	existing = SimpleNamespace(id="2", command="/dup", content="hi")

	async def load_external_prompt_placeholders(_session: object) -> dict[str, str]:
		"""return no external prompts for local validation coverage."""
		return {}

	monkeypatch.setattr(
		prompt_service,
		"load_external_prompt_placeholders",
		load_external_prompt_placeholders,
	)

	# type: ignore[arg-type]
	async def exec_conflict(stmt: object) -> _FakeResult:
		return _FakeResult(existing)

	session_conflict = _FakeSession()
	session_conflict.execute = exec_conflict  # type: ignore[assignment]

	with pytest.raises(HTTPException) as exc:
		await prompt_service._ensure_unique_command(session_conflict, command="/dup")  # type: ignore[arg-type]
	assert exc.value.status_code == 409

	# template validation failure
	async def exec_prompts(stmt: object) -> _FakeResult:  # type: ignore[arg-type]
		return _FakeResult([existing])

	session_validate = _FakeSession()
	session_validate.execute = exec_prompts  # type: ignore[assignment]

	with pytest.raises(HTTPException) as exc:
		await prompt_service._validate_prompt_template(
			session_validate,  # type: ignore[arg-type]
			prompt_id=None,
			command="/a",
			content="{{ PROMPTS.missing }}",
		)  # type: ignore[arg-type]
	assert exc.value.status_code == 400

	# update without changes returns original
	prompt_obj = SimpleNamespace(id="3", command="/ok", content="fine")
	session_get = _FakeSession(prompt_obj)
	prompt_in = prompt_service.PromptUpdate()
	result = await prompt_service.update_prompt(
		"3",  # type: ignore[arg-type]
		prompt_in,
		session_get,  # type: ignore[arg-type]
		principal=_FakePrincipal(is_admin=True),  # type: ignore[arg-type]
	)
	assert result is prompt_obj


@pytest.mark.asyncio
async def test_prompts_service_unique_exclude() -> None:
	session = _FakeSession()
	await prompt_service._ensure_unique_command(
		session,  # type: ignore[arg-type]
		command="/ok",
		exclude_prompt_id=TypeID("1"),
	)


@pytest.mark.asyncio
async def test_prompts_service_get_prompt_not_found() -> None:
	with pytest.raises(HTTPException):
		await prompt_service._get_prompt(TypeID("missing"), _FakeSession(None))  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_prompts_service_list_and_get(monkeypatch: pytest.MonkeyPatch) -> None:
	monkeypatch.setattr(prompt_external, "_SOURCES_BY_NAME", {})
	now = datetime.now(UTC)
	prompt_obj = SimpleNamespace(
		id="1", command="/p", content="hi", created_at=now, updated_at=now
	)

	async def exec_prompts(_stmt: object) -> _FakeResult:  # type: ignore[arg-type]
		return _FakeResult([prompt_obj])

	session = _FakeSession()
	session.execute = exec_prompts  # type: ignore[assignment]
	session.get = lambda *_args, **_kwargs: prompt_obj  # type: ignore[assignment]

	admin = _FakePrincipal(is_admin=True)  # type: ignore[arg-type]
	listed = await prompt_service.list_prompts(session, principal=admin)  # type: ignore[arg-type]
	assert len(listed) == 1
	assert listed[0].id == prompt_obj.id

	async def fake_get_prompt(pid: object, s: object) -> object:
		return prompt_obj

	monkeypatch.setattr(prompt_service, "_get_prompt", fake_get_prompt)
	fetched = await prompt_service.get_prompt("1", session, principal=admin)  # type: ignore[arg-type]
	assert fetched.id == prompt_obj.id
	assert fetched.command == "p"
	assert fetched.content == prompt_obj.content


@pytest.mark.asyncio
async def test_prompts_service_update_and_delete(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	prompt_obj = SimpleNamespace(id="1", command="/p", content="hi")
	calls = {}

	async def fake_get(prompt_id: object, session: object) -> object:
		calls["prompt_id"] = prompt_id
		return prompt_obj

	async def fake_unique(
		session: object, command: object, exclude_prompt_id: object = None
	) -> None:
		calls["unique"] = (command, exclude_prompt_id)
		# type: ignore[arg-type]

	async def fake_validate(
		session: object,
		prompt_id: object,
		command: object,
		content: object,  # type: ignore[arg-type]
	) -> None:  # type: ignore[arg-type]
		calls["validated"] = (prompt_id, command, content)

	monkeypatch.setattr(prompt_service, "_get_prompt", fake_get)
	monkeypatch.setattr(prompt_service, "_ensure_unique_command", fake_unique)
	monkeypatch.setattr(prompt_service, "_validate_prompt_template", fake_validate)
	# type: ignore[arg-type]
	session = _FakeSession()

	admin = _FakePrincipal(is_admin=True)
	updated = await prompt_service.update_prompt(
		"1",  # type: ignore[arg-type]
		prompt_service.PromptUpdate(command="/new", content="updated"),
		session,  # type: ignore[arg-type]
		principal=admin,  # type: ignore[arg-type]
	)
	assert updated.command == "new"
	assert calls["unique"] == ("new", "1")
	assert calls["validated"] == ("1", "new", "updated")

	await prompt_service.delete_prompt("1", session, principal=admin)  # type: ignore[arg-type]
	assert session.deleted == [prompt_obj]


@pytest.mark.asyncio
async def test_chat_service_conversions() -> None:
	user_sdk = UserMessage.from_text("hi")
	system_sdk = SystemMessage.from_text("sys")
	assistant_sdk = AssistantMessage.from_text("hey")
	assistant_sdk.usage = Usage(input_tokens=1, output_tokens=2, total_tokens=3)
	tool_sdk = ToolMessage(tool_call_id="t", tool_output="o", is_error=False)
	user_create = MessageDraft.from_sdk_message(user_sdk)
	system_create = MessageDraft.from_sdk_message(system_sdk)
	assistant_create = MessageDraft.from_sdk_message(
		assistant_sdk,
		sender_agent_id=new_typeid("agent"),
	)
	tool_create = MessageDraft.from_sdk_message(tool_sdk)

	assert user_create.type.name == "USER"
	assert user_create.sender_user_id is None
	assert system_create.type.name == "SYSTEM"
	assert assistant_create.usage["total_tokens"] == 3  # type: ignore[index]
	assert tool_create.tool_call_id == "t"
	assert tool_create.is_error is False

	class _Provider:
		def __init__(
			self,
			adapter_type: str,
			base_url: str | None = None,
			encrypted_api_key: str | None = None,
		):
			self.adapter_type = adapter_type
			self.base_url = base_url  # type: ignore[arg-type]
			self.encrypted_api_key = encrypted_api_key

		@property  # type: ignore[arg-type]
		def api_key(self) -> str | None:
			return None

	class _Model:
		def __init__(self, provider: object, adapter: str | None = None) -> None:
			self.provider = provider
			self.name = "chat"
			self.adapter = adapter
			self.input_modalities = ["text"]

		# type: ignore[arg-type]

	with pytest.raises(ValueError):
		chat_service.build_chat_model(_Model(_Provider("")))  # type: ignore[arg-type]

	chat_model = chat_service.build_chat_model(
		_Model(  # type: ignore[arg-type]
			_Provider("ollama", base_url="http://example.test:11434"), adapter="chat"
		)
	)  # type: ignore[arg-type]
	assert chat_model.model_name == "chat"
	assert chat_model.adapter.type == "ollama.chat"
	assert chat_model.adapter.base_url == "http://example.test:11434"

	with pytest.raises(HTTPException):  # type: ignore[arg-type]
		await chat_service.resolve_model_for_run(_FakeSession(), model="local:foo")  # type: ignore[arg-type]

	async def exec_model(stmt: object) -> _FakeResult:
		return _FakeResult(_Model(_Provider("ollama"), adapter="chat"))

	session_model = _FakeSession()
	session_model.execute = exec_model  # type: ignore[assignment]
	resolved = await chat_service.resolve_model_for_run(
		session_model,  # type: ignore[arg-type]
		model_id=new_typeid("model"),  # type: ignore[arg-type]
	)
	assert getattr(resolved, "name") == "chat"

	with pytest.raises(HTTPException):
		await chat_service.resolve_model_for_run(_FakeSession(), model=None)  # type: ignore[arg-type]


def test_chat_service_build_chat_model_applies_full_param_set() -> None:
	provider = ProviderORM()
	provider.adapter_type = "openai"
	provider.base_url = None
	provider.encrypted_api_key = None

	model = ModelORM()
	model.name = "chat"
	model.adapter = None
	model.input_modalities = ["text", "images"]
	model.provider = provider

	chat_model = chat_service.build_chat_model(
		model,
		params={
			"temperature": 0.25,
			"max_tokens": 512,
			"top_p": 0.8,
			"stop": ["END"],
			"reasoning_effort": "none",
		},
	)

	assert chat_model.temperature == 0.25
	assert chat_model.max_tokens == 512
	assert chat_model.top_p == 0.8
	assert chat_model.stop == ["END"]
	assert chat_model.reasoning_effort == "none"


@pytest.mark.asyncio
async def test_build_agent_from_orm_uses_chat_model_config(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	provider = ProviderORM()
	provider.adapter_type = "openai"
	provider.base_url = None
	provider.encrypted_api_key = None

	model = ModelORM()
	model.name = "chat"
	model.adapter = None
	model.provider = provider

	agent_orm = AgentORM()
	agent_orm.model = model
	agent_orm.plugin_ids = []
	agent_orm.config = {
		"chat_model": {
			"temperature": 0.4,
			"max_tokens": 256,
			"top_p": 0.9,
			"reasoning_effort": "none",
		},
		"max_iterations": 7,
	}

	async def _resolve_plugins(
		plugin_ids: list[str],
		app_context: object,
		agent_config: object,
		extra_plugins: list[str] | None = None,
	) -> ResolvedPlugins:
		_ = (app_context, agent_config, extra_plugins)
		assert plugin_ids == []
		return ResolvedPlugins(tools=[], filters=[], hooks=[])

	monkeypatch.setattr(agent_runtime, "resolve_plugins", _resolve_plugins)

	sdk_agent = await agent_runtime.build_agent_from_orm(
		agent_orm,
		context=MagicMock(),
	)

	assert sdk_agent.chat_model.temperature == 0.4
	assert sdk_agent.chat_model.max_tokens == 256
	assert sdk_agent.chat_model.top_p == 0.9
	assert sdk_agent.chat_model.reasoning_effort == "none"
	assert sdk_agent.max_iterations == 7
	assert sdk_agent.filters == []
	assert sdk_agent.hooks == []
	assert sdk_agent.tools == []


def test_chat_service_orm_to_sdk_variants() -> None:
	# Create mock Message ORM objects using the actual classes (without DB)
	user_orm = MagicMock(spec=UserMessageORM)
	user_orm.type = MessageTypeORM.USER
	user_orm.content = [{"type": "text", "text": "u"}]
	user_orm.metadata_ = {"meta": True}
	user_orm._sdk_metadata = lambda: MessageORM._sdk_metadata(user_orm)
	user_orm.to_sdk = lambda: UserMessageORM.to_sdk(user_orm)

	system_orm = MagicMock(spec=SystemMessageORM)
	system_orm.type = MessageTypeORM.SYSTEM
	system_orm.content = [{"type": "text", "text": "s"}]
	system_orm.metadata_ = {}
	system_orm._sdk_metadata = lambda: MessageORM._sdk_metadata(system_orm)
	system_orm.to_sdk = lambda: SystemMessageORM.to_sdk(system_orm)

	assistant_orm = MagicMock(spec=AssistantMessageORM)
	assistant_orm.type = MessageTypeORM.ASSISTANT
	assistant_orm.content = [{"type": "text", "text": "a"}]
	assistant_orm.tool_calls = [{"id": "t", "name": "fn", "arguments": {}}]
	assistant_orm.finish_reason = "completed"
	assistant_orm.usage = {"input_tokens": 1, "output_tokens": 2, "total_tokens": 3}
	assistant_orm.metadata_ = {}
	assistant_orm._sdk_metadata = lambda: MessageORM._sdk_metadata(assistant_orm)
	assistant_orm.to_sdk = lambda: AssistantMessageORM.to_sdk(assistant_orm)

	tool_orm = MagicMock(spec=ToolMessageORM)
	tool_orm.type = MessageTypeORM.TOOL
	tool_orm.content = [{"type": "text", "text": "out"}]
	tool_orm.tool_call_id = "tc"
	tool_orm.is_error = True
	tool_orm.metadata_ = {}
	tool_orm._sdk_metadata = lambda: MessageORM._sdk_metadata(tool_orm)
	tool_orm.to_sdk = lambda: ToolMessageORM.to_sdk(tool_orm)

	tool_orm_empty = MagicMock(spec=ToolMessageORM)
	tool_orm_empty.type = MessageTypeORM.TOOL
	tool_orm_empty.content = []
	tool_orm_empty.tool_call_id = "tc_empty"
	tool_orm_empty.is_error = False
	tool_orm_empty.metadata_ = {}
	tool_orm_empty._sdk_metadata = lambda: MessageORM._sdk_metadata(tool_orm_empty)
	tool_orm_empty.to_sdk = lambda: ToolMessageORM.to_sdk(tool_orm_empty)

	user_sdk = user_orm.to_sdk()
	system_sdk = system_orm.to_sdk()
	assistant_sdk = assistant_orm.to_sdk()
	tool_sdk = tool_orm.to_sdk()
	tool_sdk_empty = tool_orm_empty.to_sdk()

	assert user_sdk.role == "user"
	assert system_sdk.role == "system"
	assert assistant_sdk.usage.total_tokens == 3
	assert assistant_sdk.finish_reason == "completed"
	assert tool_sdk.is_error is True
	assert tool_sdk.tool_output == "out"
	assert tool_sdk_empty.tool_output == ""
	assert tool_sdk_empty.tool_call_id == "tc_empty"
	assert tool_sdk_empty.is_error is False
	# test converting branch messages using to_sdk method
	branch_msgs = [user_orm.to_sdk(), system_orm.to_sdk()]
	assert [m.role for m in branch_msgs] == ["user", "system"]

	sys_prompt = SystemMessage.from_text("hi")  # type: ignore[arg-type]
	assert sys_prompt.role == "system"

	assistant_create = MessageDraft.from_sdk_message(
		AssistantMessage.from_text("assistant"),
		sender_agent_id=new_typeid("agent"),
	)
	assert str(assistant_create.sender_agent_id).startswith("agent_")

	class _BadMessage:
		role = "bad"
		content: list[object] = []
		metadata: dict[str, object] = {}

	with pytest.raises(ValueError):
		MessageDraft.from_sdk_message(_BadMessage())  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_chat_service_agent_resolution_paths() -> None:
	class _Provider:
		def __init__(
			self,
			adapter_type: str,
			base_url: str | None = None,
			encrypted_api_key: str | None = None,
		):
			self.adapter_type = adapter_type
			self.base_url = base_url
			self.encrypted_api_key = encrypted_api_key

	class _Model:  # type: ignore[arg-type]
		def __init__(self, provider: object, adapter: str | None = None) -> None:
			self.provider = provider
			self.name = "chat"
			self.adapter = adapter

	class _Agent:  # type: ignore[arg-type]
		def __init__(self, model: object) -> None:
			self.model = model

	valid_session = _FakeSession(
		_Agent(_Model(_Provider("openai"), adapter="chat_completions"))  # type: ignore[arg-type]
	)
	resolved = await chat_service.resolve_model_for_run(
		valid_session,  # type: ignore[arg-type]
		agent_id=new_typeid("agent"),  # type: ignore[arg-type]
	)
	assert getattr(resolved, "name") == "chat"  # type: ignore[arg-type]

	with pytest.raises(HTTPException):
		await chat_service.resolve_model_for_run(
			_FakeSession(None),  # type: ignore[arg-type]
			agent_id=new_typeid("agent"),  # type: ignore[arg-type]
		)

	with pytest.raises(HTTPException):
		await chat_service.resolve_model_for_run(
			_FakeSession(_Agent(None)),  # type: ignore[arg-type]
			agent_id=new_typeid("agent"),  # type: ignore[arg-type]
		)

	with pytest.raises(HTTPException):
		await chat_service.resolve_model_for_run(
			_FakeSession(None),  # type: ignore[arg-type]
			model_id=new_typeid("model"),  # type: ignore[arg-type]
		)


@pytest.mark.asyncio
async def test_agent_runtime_load_agent_not_found() -> None:  # type: ignore[arg-type]
	"""Test that _load_agent raises HTTPException when agent not found."""

	class FakeResult:
		def scalars(self) -> FakeResult:
			return self

		def one_or_none(self) -> None:
			return None

	class FakeSession:
		async def execute(self, *_args: object, **_kwargs: object) -> FakeResult:
			return FakeResult()

	principal = _FakePrincipal()  # type: ignore[arg-type]
	with pytest.raises(HTTPException) as exc_info:
		await agent_runtime.load_agent_for_run(
			new_typeid("agent"), FakeSession(), principal
		)  # type: ignore[arg-type]

	assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_agent_runtime_load_agent_no_model() -> None:
	"""Test that _load_agent raises HTTPException when agent has no model."""

	class FakeAgent:  # type: ignore[arg-type]
		id = new_typeid("agent")
		model = None

	class FakeResult:
		def scalars(self) -> FakeResult:
			return self

		# type: ignore[arg-type]
		def one_or_none(self) -> FakeAgent:
			return FakeAgent()

	class FakeSession:
		async def execute(self, *_args: object, **_kwargs: object) -> FakeResult:
			return FakeResult()

	principal = _FakePrincipal()  # type: ignore[arg-type]
	with pytest.raises(HTTPException) as exc_info:
		await agent_runtime.load_agent_for_run(
			new_typeid("agent"), FakeSession(), principal
		)  # type: ignore[arg-type]

	assert exc_info.value.status_code == 400
	# type: ignore[arg-type]


def test_threads_helper_admin_guard() -> None:
	with pytest.raises(HTTPException):
		ensure_admin_for_hidden_or_deleted(
			True,
			False,
			_FakePrincipal(is_admin=False),  # type: ignore[arg-type]
		)


@pytest.mark.asyncio
async def test_prompt_runtime_render_inline(monkeypatch: pytest.MonkeyPatch) -> None:
	async def exec_prompts(stmt: object) -> _FakeResult:
		return _FakeResult([("/a", "hi")])

	session = _FakeSession()
	session.execute = exec_prompts  # type: ignore[assignment]

	rendered = await prompt_runtime.render_inline_with_prompts(
		session,  # type: ignore[arg-type]
		text="{{ PROMPTS.a }}",  # type: ignore[arg-type]
	)
	assert rendered == "hi"


@pytest.mark.asyncio
async def test_external_prompt_source_registry_routes_prefix(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	monkeypatch.setattr(prompt_external, "_SOURCES_BY_NAME", {})
	render_calls: list[set[str]] = []

	async def load_placeholders(_session: object) -> dict[str, str]:
		return {"covprompt-one": ""}

	async def render_content_map(
		_session: object,
		commands: set[str],
	) -> dict[str, str]:
		render_calls.append(commands)
		return {command: "rendered" for command in commands}

	async def list_prompts(_session: object) -> list[object]:
		return []

	async def get_prompt(_prompt_id: str, _session: object) -> object | None:
		return None

	prompt_external.register_external_prompt_source(
		prompt_external.ExternalPromptSource(
			name="coverage-prompts",
			prefix="covprompt-",
			load_placeholders=load_placeholders,
			render_content_map=render_content_map,
			list_prompts=list_prompts,
			get_prompt=get_prompt,
		)
	)

	placeholders = await prompt_external.load_external_prompt_placeholders(object())
	rendered = await prompt_external.render_external_prompt_content_map(
		object(),
		{"covprompt-one", "local"},
	)

	assert placeholders == {"covprompt-one": ""}
	assert render_calls == [{"covprompt-one"}]
	assert rendered == {"covprompt-one": "rendered"}


def test_external_prompt_source_registry_rejects_prefix_conflict(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	monkeypatch.setattr(prompt_external, "_SOURCES_BY_NAME", {})

	async def load_placeholders(_session: object) -> dict[str, str]:
		return {}

	async def render_content_map(
		_session: object,
		_commands: set[str],
	) -> dict[str, str]:
		return {}

	async def list_prompts(_session: object) -> list[object]:
		return []

	async def get_prompt(_prompt_id: str, _session: object) -> object | None:
		return None

	prompt_external.register_external_prompt_source(
		prompt_external.ExternalPromptSource(
			name="coverage-prompts",
			prefix="covprompt-",
			load_placeholders=load_placeholders,
			render_content_map=render_content_map,
			list_prompts=list_prompts,
			get_prompt=get_prompt,
		)
	)
	with pytest.raises(ValueError, match="prefix conflicts"):
		prompt_external.register_external_prompt_source(
			prompt_external.ExternalPromptSource(
				name="coverage-prompts-other",
				prefix="covprompt-one-",
				load_placeholders=load_placeholders,
				render_content_map=render_content_map,
				list_prompts=list_prompts,
				get_prompt=get_prompt,
			)
		)


@pytest.mark.asyncio
async def test_external_tool_source_registry_routes_prefix(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	monkeypatch.setattr(external_tools, "_SOURCES_BY_NAME", {})
	context = object()
	resolve_calls: list[list[str]] = []

	async def resolve_tools(
		tool_ids: list[str],
		app_context: object,
	) -> list[object]:
		resolve_calls.append(tool_ids)
		assert app_context is context
		return []

	async def list_plugins(
		_session: object,
		_plugin_type: object = None,
		_principal: object = None,
	) -> list[object]:
		return []

	async def get_plugin(
		_plugin_id: str,
		_session: object,
		_principal: object,
	) -> object | None:
		return None

	external_tools.register_external_tool_source(
		external_tools.ExternalToolSource(
			name="coverage-tools",
			prefix="covtool:",
			resolve_tools=resolve_tools,
			list_plugins=list_plugins,
			get_plugin=get_plugin,
		)
	)

	assert external_tools.has_external_tool_source("covtool:item")
	assert not external_tools.has_external_tool_source("native")
	resolved = await external_tools.resolve_external_tools(
		["covtool:item", "native"], context
	)
	assert resolved == []
	assert resolve_calls == [["covtool:item"]]
