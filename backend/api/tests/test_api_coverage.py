"""Targeted coverage for API modules."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from api.models.message import MessageType as MessageTypeORM
from api.schemas.message import MessageCreate
from api.v1.routers import openai as openai_router
from api.v1.routers import prompts as prompts_router
from api.v1.routers import threads as threads_router
from api.v1.service import authorization, prompt_runtime
from api.v1.service import chat as chat_service
from api.v1.service import prompts as prompt_service
from api.v1.service import threads as thread_service
from nokodo_ai.messages import (
	AssistantMessage,
	SystemMessage,
	ToolMessage,
	Usage,
	UserMessage,
)
from nokodo_ai.utils.typeid import new_typeid


class _FakePrincipal:
	def __init__(
		self,
		*,
		is_admin: bool = False,
		user_id: str = "user",
		groups: list[str] | None = None,
	) -> None:
		self.is_admin = is_admin
		self.user = SimpleNamespace(id=user_id)
		self.group_ids = groups or []

	def has_permission(self, permission: str) -> bool:
		return permission == "any"


class _FakeResult:
	def __init__(self, value: object) -> None:
		self.value = value

	def scalar_one_or_none(self) -> object:
		return self.value

	def scalars(self):  # type: ignore[override]
		return self

	def one_or_none(self):  # type: ignore[override]
		return self.value

	def first(self):  # type: ignore[override]
		return self.value

	def all(self):  # type: ignore[override]
		if isinstance(self.value, list):
			return self.value
		return [self.value] if self.value is not None else []


class _FakeSession:
	def __init__(self, value: object | None = None) -> None:
		self.value = value
		self.last_stmt = None
		self.added: list[object] = []
		self.deleted: list[object] = []

	async def execute(self, stmt, *_, **__):  # type: ignore[override]
		self.last_stmt = stmt
		return _FakeResult(self.value)

	async def get(self, *_args, **_kwargs):  # type: ignore[override]
		return self.value

	async def commit(self):
		return None

	async def refresh(self, *_args, **_kwargs):  # type: ignore[override]
		return None

	async def flush(self):  # type: ignore[override]
		return None

	def add(self, obj):  # type: ignore[override]
		self.added.append(obj)

	async def delete(self, obj):  # type: ignore[override]
		self.deleted.append(obj)


async def _empty_branch(*_args, **_kwargs):
	return []


async def _resolved_model(*_args, **_kwargs):
	return "local:model"


async def test_openai_router_uses_chat_model(monkeypatch):
	captured = {}

	class FakeAssistant:
		def __init__(self) -> None:
			self.text = "hi"
			self.usage = Usage(input_tokens=1, output_tokens=2, total_tokens=3)

	class FakeChatModel:
		def __init__(self, model: str, *_, **__) -> None:
			captured["model"] = model

		async def generate(
			self,
			messages,
			*,
			stream: bool,
			temperature=None,
			max_tokens=None,
		):
			captured["messages"] = messages
			captured["stream"] = stream
			captured["temperature"] = temperature
			captured["max_tokens"] = max_tokens
			return FakeAssistant()

	monkeypatch.setattr(openai_router, "ChatModel", FakeChatModel)

	req = openai_router.OpenAIChatCompletionRequest(
		model="gpt",
		messages=[openai_router.OpenAIChatMessage(role="user", content="hi")],
		temperature=0.1,
		max_tokens=5,
	)
	principal = _FakePrincipal()

	resp = await openai_router.chat_completions(req, principal=principal, db=None)

	assert resp.model == "gpt"
	assert captured["stream"] is False
	assert captured["temperature"] == 0.1
	assert captured["max_tokens"] == 5
	assert resp.usage.total_tokens == 3


async def test_openai_router_handles_all_roles(monkeypatch):
	captured = {}

	class FakeAssistant:
		def __init__(self) -> None:
			self.text = "ok"
			self.usage = None

	class FakeChatModel:
		def __init__(self, *_args, **_kwargs):
			pass

		async def generate(
			self,
			messages,
			*,
			stream: bool,
			temperature=None,
			max_tokens=None,
		):
			captured["messages"] = messages
			captured["stream"] = stream
			captured["temperature"] = temperature
			captured["max_tokens"] = max_tokens
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
		req, principal=_FakePrincipal(), db=None
	)

	assert [m.role for m in captured["messages"]] == ["system", "assistant", "user"]
	assert captured["stream"] is False
	assert resp.usage.total_tokens == 0


async def test_prompts_router_delegates(monkeypatch):
	fake_prompt = SimpleNamespace(id="1", command="/a", content="hi")

	async def fake_create(prompt_in, db):
		return fake_prompt

	async def fake_list(
		db,
		*,
		skip=0,
		limit=50,
		sort_by="command",
		sort_dir="asc",
	):
		return [fake_prompt]

	async def fake_get(prompt_id, db):
		return fake_prompt

	async def fake_update(prompt_id, prompt_in, db):
		return fake_prompt

	async def fake_delete(prompt_id, db):
		fake_delete.called = prompt_id  # type: ignore[attr-defined]

	monkeypatch.setattr(prompts_router.prompt_service, "create_prompt", fake_create)
	monkeypatch.setattr(prompts_router.prompt_service, "list_prompts", fake_list)
	monkeypatch.setattr(prompts_router.prompt_service, "get_prompt", fake_get)
	monkeypatch.setattr(prompts_router.prompt_service, "update_prompt", fake_update)
	monkeypatch.setattr(prompts_router.prompt_service, "delete_prompt", fake_delete)

	out_create = await prompts_router.create_prompt(fake_prompt, db=None)
	out_list = await prompts_router.list_prompts(db=None)
	out_get = await prompts_router.get_prompt("1", db=None)
	out_update = await prompts_router.update_prompt("1", fake_prompt, db=None)
	await prompts_router.delete_prompt("1", db=None)

	assert out_create is fake_prompt
	assert out_list == [fake_prompt]
	assert out_get is fake_prompt
	assert out_update is fake_prompt
	assert fake_delete.called == "1"  # type: ignore[attr-defined]


async def test_threads_router_delegates(monkeypatch):
	principal = _FakePrincipal()
	fake_thread = SimpleNamespace(id=new_typeid("thread"))
	fake_message = SimpleNamespace(
		id=new_typeid("message"),
		thread_id=new_typeid("thread"),
		created_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
		updated_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
		content=[],
		tool_calls=[],
		usage=None,
		read_by=[],
		metadata_={},
		parent_id=None,
		task_id=None,
		sender_agent_id=None,
		sender_user_id=None,
	)

	async def _return_thread(*_args, **_kwargs):
		return fake_thread

	async def _return_thread_list(*_args, **_kwargs):
		return [fake_thread]

	async def _return_message_list(*_args, **_kwargs):
		return [fake_message]

	async def _return_message(*_args, **_kwargs):
		return fake_message

	async def _return_run(*_args, **_kwargs):
		return fake_message, [fake_message]

	async def _switch(*_args, **_kwargs):
		return SimpleNamespace(current_message_id=new_typeid("message"))

	async def _return_acl(*_args, **_kwargs):
		return ["acl"]

	monkeypatch.setattr(threads_router.thread_service, "create_thread", _return_thread)
	monkeypatch.setattr(
		threads_router.thread_service, "list_threads", _return_thread_list
	)
	monkeypatch.setattr(threads_router.thread_service, "get_thread", _return_thread)
	monkeypatch.setattr(threads_router.thread_service, "update_thread", _return_thread)
	monkeypatch.setattr(
		threads_router.thread_service, "list_messages", _return_message_list
	)
	monkeypatch.setattr(
		threads_router.thread_service, "get_current_branch", _return_message_list
	)
	monkeypatch.setattr(
		threads_router.thread_service, "list_message_tree", _return_message_list
	)
	monkeypatch.setattr(
		threads_router.thread_service, "create_message", _return_message
	)
	monkeypatch.setattr(threads_router.thread_service, "switch_branch", _switch)
	monkeypatch.setattr(threads_router.acl_service, "list_thread_acl", _return_acl)
	monkeypatch.setattr(threads_router.acl_service, "set_thread_acl", _return_acl)

	# patch the chat runner for /threads/{id}/run (streaming-only)
	async def _chat_run_agent(*_args, **_kwargs):
		if False:
			yield b""

	monkeypatch.setattr(threads_router, "chat_run_agent", _chat_run_agent)

	created = await threads_router.create_thread(
		SimpleNamespace(owner_id="u"),
		principal=principal,
		db=None,
	)
	listed = await threads_router.list_threads(principal=principal, db=None)
	fetched = await threads_router.get_thread("t", principal=principal, db=None)
	updated = await threads_router.update_thread(
		"t",
		SimpleNamespace(),
		principal=principal,
		db=None,
	)
	messages = await threads_router.list_messages("t", principal=principal, db=None)
	branch = await threads_router.get_current_branch("t", principal=principal, db=None)
	tree = await threads_router.get_message_tree("t", principal=principal, db=None)
	posted = await threads_router.create_message(
		"t",
		SimpleNamespace(type=None),
		principal=principal,
		db=None,
	)
	run_resp = await threads_router.run_thread(
		new_typeid("thread"),
		SimpleNamespace(
			agent_id=new_typeid("agent"),
			stream=True,
			input=None,
		),
		principal=principal,
		db=None,
	)
	switched = await threads_router.switch_branch(
		"t",
		SimpleNamespace(message_id="m"),
		principal=principal,
		db=None,
	)
	acl_list = await threads_router.list_thread_acl("t", principal=principal, db=None)
	acl_set = await threads_router.set_thread_acl("t", [], principal=principal, db=None)

	assert created is fake_thread
	assert listed == [fake_thread]
	assert fetched is fake_thread
	assert updated is fake_thread
	assert messages == [fake_message]
	assert branch == [fake_message]
	assert tree == [fake_message]
	assert posted is fake_message
	assert run_resp.media_type == "text/event-stream"
	assert run_resp.headers.get("X-Accel-Buffering") == "no"
	assert switched.current_message_id is not None
	assert acl_list == ["acl"]
	assert acl_set == ["acl"]


async def test_authorization_require_thread_access():
	principal = _FakePrincipal(is_admin=True)
	fake_session = _FakeSession("ok")

	await authorization.require_thread_access(
		"thread",
		fake_session,
		principal,
		include_hidden=True,
	)

	assert fake_session.last_stmt._execution_options.get("include_deleted") is True

	fake_session_none = _FakeSession(None)

	with pytest.raises(HTTPException) as exc:
		await authorization.require_thread_access(
			"thread",
			fake_session_none,
			principal,
		)
	assert exc.value.status_code == 404


def test_prompt_runtime_validation_errors():
	with pytest.raises(prompt_runtime.PromptValidationError):
		prompt_runtime.render_prompt_from_map({}, command="/missing")

	with pytest.raises(prompt_runtime.PromptValidationError) as exc:
		prompt_runtime.validate_prompt_content(
			all_prompts=[],
			command="/a",
			content="{{ PROMPTS.b }} {% include 'a' %}",
		)
	assert "does not exist" in str(exc.value)

	with pytest.raises(prompt_runtime.PromptValidationError) as exc:
		prompt_runtime.validate_prompt_content(
			all_prompts=[
				SimpleNamespace(id="1", command="/a", content="{{ PROMPTS.a }}")
			],
			command="/a",
			content="{{ PROMPTS.a }}",
		)
	assert "circular" in str(exc.value)


def test_prompt_runtime_template_not_found(monkeypatch):
	def _fake_env(_map):
		class _Env:
			def get_template(self, *_args, **_kwargs):
				raise prompt_runtime.TemplateNotFound("missing")

		return _Env()

	monkeypatch.setattr(prompt_runtime, "_build_env", _fake_env)

	with pytest.raises(prompt_runtime.PromptValidationError):
		prompt_runtime.render_prompt_from_map({"a": "hi"}, command="/a")


async def test_prompt_runtime_render_from_db(monkeypatch):
	async def exec_prompts(_stmt):
		return _FakeResult([("/cmd", "body")])

	session = _FakeSession()
	session.execute = exec_prompts  # type: ignore[assignment]

	rendered = await prompt_runtime.render_prompt_from_db(session, command="/cmd")
	assert rendered == "body"


async def test_prompts_service_validation_paths(monkeypatch):
	existing = SimpleNamespace(id="2", command="/dup", content="hi")

	async def exec_conflict(stmt):
		return _FakeResult(existing)

	session_conflict = _FakeSession()
	session_conflict.execute = exec_conflict  # type: ignore[assignment]

	with pytest.raises(HTTPException) as exc:
		await prompt_service._ensure_unique_command(session_conflict, command="/dup")
	assert exc.value.status_code == 409

	# template validation failure
	async def exec_prompts(stmt):
		return _FakeResult([existing])

	session_validate = _FakeSession()
	session_validate.execute = exec_prompts  # type: ignore[assignment]

	with pytest.raises(HTTPException) as exc:
		await prompt_service._validate_prompt_template(
			session_validate,
			prompt_id=None,
			command="/a",
			content="{{ PROMPTS.missing }}",
		)
	assert exc.value.status_code == 400

	# update without changes returns original
	prompt_obj = SimpleNamespace(id="3", command="/ok", content="fine")
	session_get = _FakeSession(prompt_obj)
	prompt_in = prompt_service.PromptUpdate()
	result = await prompt_service.update_prompt("3", prompt_in, session_get)
	assert result is prompt_obj


async def test_prompts_service_unique_exclude() -> None:
	session = _FakeSession()
	await prompt_service._ensure_unique_command(
		session, command="/ok", exclude_prompt_id="1"
	)


async def test_prompts_service_get_prompt_not_found() -> None:
	with pytest.raises(HTTPException):
		await prompt_service._get_prompt("missing", _FakeSession(None))


async def test_prompts_service_list_and_get(monkeypatch):
	prompt_obj = SimpleNamespace(id="1", command="/p", content="hi")

	async def exec_prompts(_stmt):
		return _FakeResult([prompt_obj])

	session = _FakeSession()
	session.execute = exec_prompts  # type: ignore[assignment]
	session.get = lambda *_args, **_kwargs: prompt_obj  # type: ignore[assignment]

	listed = await prompt_service.list_prompts(session)
	assert listed == [prompt_obj]

	async def fake_get_prompt(pid, s):
		return prompt_obj

	monkeypatch.setattr(prompt_service, "_get_prompt", fake_get_prompt)
	fetched = await prompt_service.get_prompt("1", session)
	assert fetched is prompt_obj


async def test_prompts_service_update_and_delete(monkeypatch):
	prompt_obj = SimpleNamespace(id="1", command="/p", content="hi")
	calls = {}

	async def fake_get(prompt_id, session):
		calls["prompt_id"] = prompt_id
		return prompt_obj

	async def fake_unique(session, *, command, exclude_prompt_id=None):
		calls["unique"] = (command, exclude_prompt_id)

	async def fake_validate(session, *, prompt_id, command, content):
		calls["validated"] = (prompt_id, command, content)

	monkeypatch.setattr(prompt_service, "_get_prompt", fake_get)
	monkeypatch.setattr(prompt_service, "_ensure_unique_command", fake_unique)
	monkeypatch.setattr(prompt_service, "_validate_prompt_template", fake_validate)

	session = _FakeSession()

	updated = await prompt_service.update_prompt(
		"1", prompt_service.PromptUpdate(command="/new", content="updated"), session
	)
	assert updated.command == "/new"
	assert calls["unique"] == ("/new", "1")
	assert calls["validated"] == ("1", "/new", "updated")

	await prompt_service.delete_prompt("1", session)
	assert session.deleted == [prompt_obj]


async def test_chat_service_conversions():
	user_sdk = UserMessage.from_text("hi")
	system_sdk = SystemMessage.from_text("sys")
	assistant_sdk = AssistantMessage.from_text("hey")
	assistant_sdk.usage = Usage(input_tokens=1, output_tokens=2, total_tokens=3)
	tool_sdk = ToolMessage(tool_call_id="t", tool_output="o", is_error=False)

	user_create = MessageCreate.from_sdk_message(
		user_sdk,
		sender_user_id=new_typeid("user"),
	)
	system_create = MessageCreate.from_sdk_message(system_sdk)
	assistant_create = MessageCreate.from_sdk_message(
		assistant_sdk,
		sender_agent_id=new_typeid("agent"),
	)
	tool_create = MessageCreate.from_sdk_message(tool_sdk)

	assert str(user_create.sender_user_id).startswith("user_")
	assert system_create.type.name == "SYSTEM"
	assert assistant_create.usage["total_tokens"] == 3
	assert tool_create.tool_call_id == "t"
	assert tool_create.is_error is False

	class _Provider:
		def __init__(
			self,
			adapter_type: str,
			*,
			base_url: str | None = None,
			encrypted_api_key: str | None = None,
		):
			self.adapter_type = adapter_type
			self.base_url = base_url
			self.encrypted_api_key = encrypted_api_key

		@property
		def api_key(self) -> str | None:
			return None

	class _Model:
		def __init__(self, provider, adapter: str | None = None):
			self.provider = provider
			self.name = "chat"
			self.adapter = adapter

	with pytest.raises(ValueError):
		chat_service.build_chat_model(_Model(_Provider("")))

	llm = chat_service.build_chat_model(
		_Model(
			_Provider("ollama", base_url="http://example.test:11434"), adapter="chat"
		)
	)
	assert llm.provider == "ollama"
	assert llm.variant == "chat"
	assert llm.model_name == "chat"
	assert llm.adapter.type == "ollama.chat"
	assert llm.adapter.base_url == "http://example.test:11434"

	with pytest.raises(HTTPException):
		await chat_service.resolve_model_for_run(_FakeSession(), model="local:foo")

	async def exec_model(stmt):
		return _FakeResult(_Model(_Provider("ollama"), adapter="chat"))

	session_model = _FakeSession()
	session_model.execute = exec_model  # type: ignore[assignment]
	resolved = await chat_service.resolve_model_for_run(
		session_model, model_id=new_typeid("model")
	)
	assert getattr(resolved, "name") == "chat"

	with pytest.raises(HTTPException):
		await chat_service.resolve_model_for_run(_FakeSession(), model=None)


def test_chat_service_orm_to_sdk_variants():
	from unittest.mock import MagicMock

	from api.models.message import (
		AssistantMessage as AssistantMessageORM,
	)
	from api.models.message import (
		Message as MessageORM,
	)
	from api.models.message import (
		SystemMessage as SystemMessageORM,
	)
	from api.models.message import (
		ToolMessage as ToolMessageORM,
	)
	from api.models.message import (
		UserMessage as UserMessageORM,
	)

	# Create mock Message ORM objects using the actual classes (without DB)
	user_orm = MagicMock(spec=UserMessageORM)
	user_orm.type = MessageTypeORM.USER
	user_orm.content = [{"type": "text", "text": "u"}]
	user_orm.metadata_ = {"meta": True}
	user_orm.to_sdk = lambda: UserMessageORM.to_sdk(user_orm)

	system_orm = MagicMock(spec=SystemMessageORM)
	system_orm.type = MessageTypeORM.SYSTEM
	system_orm.content = [{"type": "text", "text": "s"}]
	system_orm.metadata_ = {}
	system_orm.to_sdk = lambda: SystemMessageORM.to_sdk(system_orm)

	assistant_orm = MagicMock(spec=AssistantMessageORM)
	assistant_orm.type = MessageTypeORM.ASSISTANT
	assistant_orm.content = [{"type": "text", "text": "a"}]
	assistant_orm.tool_calls = [{"id": "t", "name": "fn", "arguments": {}}]
	assistant_orm.usage = {"input_tokens": 1, "output_tokens": 2, "total_tokens": 3}
	assistant_orm.metadata_ = {}
	assistant_orm.to_sdk = lambda: AssistantMessageORM.to_sdk(assistant_orm)

	tool_orm = MagicMock(spec=ToolMessageORM)
	tool_orm.type = MessageTypeORM.TOOL
	tool_orm.content = [{"type": "text", "text": "out"}]
	tool_orm.tool_call_id = "tc"
	tool_orm.is_error = True
	tool_orm.metadata_ = {}
	tool_orm.to_sdk = lambda: ToolMessageORM.to_sdk(tool_orm)

	tool_orm_empty = MagicMock(spec=ToolMessageORM)
	tool_orm_empty.type = MessageTypeORM.TOOL
	tool_orm_empty.content = []
	tool_orm_empty.tool_call_id = "tc_empty"
	tool_orm_empty.is_error = False
	tool_orm_empty.metadata_ = {}
	tool_orm_empty.to_sdk = lambda: ToolMessageORM.to_sdk(tool_orm_empty)

	unknown_orm = MagicMock(spec=MessageORM)
	unknown_orm.type = "other"
	unknown_orm.content = []
	unknown_orm.metadata_ = {}
	unknown_orm.to_sdk = lambda: MessageORM.to_sdk(unknown_orm)

	user_sdk = user_orm.to_sdk()
	system_sdk = system_orm.to_sdk()
	assistant_sdk = assistant_orm.to_sdk()
	tool_sdk = tool_orm.to_sdk()
	tool_sdk_empty = tool_orm_empty.to_sdk()
	fallback_sdk = unknown_orm.to_sdk()

	assert user_sdk.role == "user"
	assert system_sdk.role == "system"
	assert assistant_sdk.usage.total_tokens == 3
	assert tool_sdk.is_error is True
	assert tool_sdk.tool_output == "out"
	assert tool_sdk_empty.tool_output == ""
	assert tool_sdk_empty.tool_call_id == "tc_empty"
	assert tool_sdk_empty.is_error is False
	assert fallback_sdk.role == "user"

	# test converting branch messages using to_sdk method
	branch_msgs = [user_orm.to_sdk(), system_orm.to_sdk()]
	assert [m.role for m in branch_msgs] == ["user", "system"]

	sys_prompt = SystemMessage.from_text("hi")
	assert sys_prompt.role == "system"

	assistant_create = MessageCreate.from_sdk_message(
		AssistantMessage.from_text("assistant"),
		sender_agent_id=new_typeid("agent"),
	)
	assert str(assistant_create.sender_agent_id).startswith("agent_")

	class _BadMessage:
		role = "bad"
		content: list[object] = []

	with pytest.raises(ValueError):
		MessageCreate.from_sdk_message(_BadMessage())


async def test_chat_service_agent_resolution_paths():
	class _Provider:
		def __init__(
			self,
			adapter_type: str,
			*,
			base_url: str | None = None,
			encrypted_api_key: str | None = None,
		):
			self.adapter_type = adapter_type
			self.base_url = base_url
			self.encrypted_api_key = encrypted_api_key

	class _Model:
		def __init__(self, provider, adapter: str | None = None):
			self.provider = provider
			self.name = "chat"
			self.adapter = adapter

	class _Agent:
		def __init__(self, model):
			self.model = model

	valid_session = _FakeSession(
		_Agent(_Model(_Provider("openai"), adapter="chat_completions"))
	)
	resolved = await chat_service.resolve_model_for_run(
		valid_session, agent_id=new_typeid("agent")
	)
	assert getattr(resolved, "name") == "chat"

	with pytest.raises(HTTPException):
		await chat_service.resolve_model_for_run(
			_FakeSession(None), agent_id=new_typeid("agent")
		)

	with pytest.raises(HTTPException):
		await chat_service.resolve_model_for_run(
			_FakeSession(_Agent(None)), agent_id=new_typeid("agent")
		)

	with pytest.raises(HTTPException):
		await chat_service.resolve_model_for_run(
			_FakeSession(None), model_id=new_typeid("model")
		)


async def test_chat_runner_load_agent_not_found(monkeypatch):
	"""Test that _load_agent raises HTTPException when agent not found."""
	from api.v1.service.chat import agents as chat_runner

	class FakeResult:
		def scalars(self):
			return self

		def one_or_none(self):
			return None

	class FakeSession:
		async def execute(self, *_args, **_kwargs):
			return FakeResult()

	with pytest.raises(HTTPException) as exc_info:
		await chat_runner._load_agent(new_typeid("agent"), FakeSession())

	assert exc_info.value.status_code == 404


async def test_chat_runner_load_agent_no_model(monkeypatch):
	"""Test that _load_agent raises HTTPException when agent has no model."""
	from api.v1.service.chat import agents as chat_runner

	class FakeAgent:
		id = new_typeid("agent")
		model = None

	class FakeResult:
		def scalars(self):
			return self

		def one_or_none(self):
			return FakeAgent()

	class FakeSession:
		async def execute(self, *_args, **_kwargs):
			return FakeResult()

	with pytest.raises(HTTPException) as exc_info:
		await chat_runner._load_agent(new_typeid("agent"), FakeSession())

	assert exc_info.value.status_code == 400


def test_threads_helper_admin_guard():
	with pytest.raises(HTTPException):
		thread_service._ensure_admin_for_hidden(True, _FakePrincipal(is_admin=False))


async def test_prompt_runtime_render_inline(monkeypatch):
	async def exec_prompts(stmt):
		return _FakeResult([("/a", "hi")])

	session = _FakeSession()
	session.execute = exec_prompts  # type: ignore[assignment]

	rendered = await prompt_runtime.render_inline_with_prompts(
		session, text="{{ PROMPTS.a }}"
	)
	assert rendered == "hi"
