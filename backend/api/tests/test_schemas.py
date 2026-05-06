"""Schema-specific unit tests for ORM-aware validators."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from api.models.message import MessageType
from api.models.project import Project as ProjectModel
from api.models.thread import Thread as ThreadModel
from api.schemas.content import TextContent
from api.schemas.event import Event as EventSchema
from api.schemas.message import Message as MessageSchema
from api.schemas.message import MessageCreate, public_message_metadata
from api.schemas.project import Project as ProjectSchema
from api.schemas.prompt import PromptCreate, PromptUpdate
from api.schemas.runs import RunInput, RunRequest, ThreadCreateAndRunRequest
from api.schemas.thread import Thread as ThreadSchema
from api.schemas.thread import ThreadSummary
from api.v1.service.chat.run_helpers import message_to_sse_data
from nokodo_ai.utils.typeid import new_typeid


def _stamp_project(project: ProjectModel, project_id: str) -> ProjectModel:
	project.id = project_id
	project.metadata_ = {}
	project.created_at = datetime.now(tz=UTC)
	project.updated_at = datetime.now(tz=UTC)
	return project


def _stamp_thread(thread: ThreadModel, thread_id: str) -> ThreadModel:
	thread.id = thread_id
	thread.metadata_ = {}
	thread.tags = []
	thread.is_archived = False
	thread.last_activity_at = datetime.now(tz=UTC)
	thread.created_at = datetime.now(tz=UTC)
	thread.updated_at = datetime.now(tz=UTC)
	return thread


def test_project_schema_populates_thread_ids() -> None:
	owner_id = new_typeid("user")
	project_id = new_typeid("proj")
	thread_id = new_typeid("thread")
	project = _stamp_project(
		ProjectModel(name="Schema", description="Test", owner_id=owner_id),
		project_id=project_id,
	)
	thread = _stamp_thread(ThreadModel(owner_id=owner_id), thread_id=thread_id)
	project.threads = [thread]

	serialized = ProjectSchema.model_validate(project)
	assert serialized.thread_ids == [thread_id]


def test_project_schema_handles_empty_threads() -> None:
	owner_id = new_typeid("user")
	project = _stamp_project(
		ProjectModel(name="Schema", description="Test", owner_id=owner_id),
		project_id=new_typeid("proj"),
	)
	project.threads = []

	serialized = ProjectSchema.model_validate(project)
	assert serialized.thread_ids == []


def test_project_schema_handles_unloaded_threads() -> None:
	owner_id = new_typeid("user")
	project = _stamp_project(
		ProjectModel(name="Schema", description="Test", owner_id=owner_id),
		project_id=new_typeid("proj"),
	)

	serialized = ProjectSchema.model_validate(project)
	assert serialized.thread_ids == []


def test_thread_schema_populates_project_ids() -> None:
	owner_id = new_typeid("user")
	thread_id = new_typeid("thread")
	project_id = new_typeid("proj")
	thread = _stamp_thread(ThreadModel(owner_id=owner_id), thread_id=thread_id)
	project = _stamp_project(
		ProjectModel(name="Schema", description="Test", owner_id=owner_id),
		project_id=project_id,
	)
	thread.projects = [project]

	detailed = ThreadSchema.model_validate(thread)
	summary = ThreadSummary.model_validate(thread)

	assert detailed.project_ids == [project_id]
	assert summary.project_ids == [project_id]


def test_message_create_normalizes_content_variants() -> None:
	text = "hello"
	part_dict = {"type": "text", "text": "world"}
	model_part = TextContent(text="model")

	from_str = MessageCreate(content=text)
	from_list = MessageCreate.model_validate(
		{"content": [part_dict, model_part.model_dump()]}
	)
	from_empty = MessageCreate(content="")

	first = from_str.content[0]
	assert isinstance(first, TextContent)
	assert first.text == text

	assert len(from_list.content) == 2
	part_0 = from_list.content[0]
	part_1 = from_list.content[1]
	assert isinstance(part_0, TextContent)
	assert isinstance(part_1, TextContent)
	assert part_0.text == "world"
	assert part_1.text == "model"
	assert from_empty.content == []


def test_public_message_metadata_strips_private_underscore_keys() -> None:
	metadata = {
		"run_id": "run_123",
		"steering_state": "queued",
		"custom_public": "visible",
		"model_id": "public_if_present",
		"message_id": "public_if_present",
		"_provider_data": {"provider": {"tool_call_id": "call_secret"}},
		"_citations_assigned": True,
		"_citable_sources": [{"source_type": "url", "source_id": "secret"}],
		"_web_fetch": {"domain": "example.com"},
		"_web_search": {"engine": "perplexity"},
	}

	assert public_message_metadata(metadata) == {
		"run_id": "run_123",
		"steering_state": "queued",
		"custom_public": "visible",
		"model_id": "public_if_present",
		"message_id": "public_if_present",
	}


def test_message_schema_serializes_public_tool_metadata() -> None:
	now = datetime.now(tz=UTC)
	message = MessageSchema(
		id=new_typeid("msg"),
		thread_id=new_typeid("thread"),
		type=MessageType.TOOL,
		content=[],
		tool_call_id="call_123",
		is_error=False,
		metadata_={
			"run_id": "run_123",
			"_provider_data": {"provider": {"tool_call_id": "call_secret"}},
			"_web_search": {"engine": "perplexity"},
		},
		created_at=now,
		updated_at=now,
	)

	payload = message.model_dump(mode="json", by_alias=True)

	assert payload["metadata_"] == {"run_id": "run_123"}


def test_message_to_sse_data_serializes_public_tool_metadata() -> None:
	now = datetime.now(tz=UTC)
	message = SimpleNamespace(
		id=new_typeid("msg"),
		thread_id=new_typeid("thread"),
		parent_id=None,
		type=MessageType.TOOL,
		content=[],
		metadata_={
			"run_id": "run_123",
			"_message_id": "msg_internal",
			"_provider_data": {"provider": {"tool_call_id": "call_secret"}},
			"_web_search": {"engine": "perplexity"},
		},
		sender_agent_id=None,
		sender_user_id=None,
		created_at=now,
	)

	assert message_to_sse_data(message)["metadata_"] == {"run_id": "run_123"}


def test_prompt_schema_validates_and_normalizes() -> None:
	valid = PromptCreate(command="my-prompt", content="body")
	assert valid.command == "my-prompt"

	updated = PromptUpdate(command="/next", content="x")
	assert updated.command == "next"

	with pytest.raises(ValueError):
		PromptCreate(command="not ok!", content="bad")


def test_prompt_schema_none_and_blank_commands() -> None:
	update = PromptUpdate(command=None, content=None)
	assert update.command is None

	with pytest.raises(ValueError):
		PromptCreate(command="   ", content="x")


def test_run_request_requires_agent_id() -> None:
	"""agent_id is required for run requests."""
	with pytest.raises(ValueError):
		RunRequest()  # type: ignore[call-arg]

	req = RunRequest(agent_id=new_typeid("agent"))
	assert req.agent_id is not None
	assert req.input is None
	assert req.thread_id is None
	assert req.stream is True

	req_with_input = RunRequest(
		agent_id=new_typeid("agent"),
		input=RunInput(text="hello"),
	)
	assert req_with_input.input is not None
	assert req_with_input.input.text == "hello"

	# ThreadCreateAndRunRequest

	car_req = ThreadCreateAndRunRequest(
		agent_id=new_typeid("agent"),
		input=RunInput(text="hi"),
	)
	assert car_req.is_temporary is False
	assert car_req.tags == []
	assert car_req.stream is True


def test_thread_schema_defaults_for_flags() -> None:
	thread = _stamp_thread(
		ThreadModel(owner_id=new_typeid("user")), thread_id=new_typeid("thread")
	)
	thread.is_temporary = None  # type: ignore[assignment]
	thread.is_archived = None  # type: ignore[assignment]

	serialized = ThreadSchema.model_validate(thread)
	assert serialized.is_temporary is False
	assert serialized.is_archived is False


def test_schema_coerces_none_metadata_to_empty_dict() -> None:
	now = datetime.now(tz=UTC)
	event = SimpleNamespace(
		id=new_typeid("event"),
		type="test",
		metadata_=None,
		created_at=now,
		updated_at=now,
	)

	serialized = EventSchema.model_validate(event)
	assert serialized.metadata == {}


def test_message_create_validates_type_specific_fields() -> None:
	# tool messages require tool_call_id and is_error
	with pytest.raises(ValueError, match="tool_call_id is required"):
		MessageCreate(type=MessageType.TOOL, content="output")

	with pytest.raises(ValueError, match="is_error is required"):
		MessageCreate(type=MessageType.TOOL, content="output", tool_call_id="tc")

	# valid tool message
	tool_msg = MessageCreate(
		type=MessageType.TOOL,
		content="output",
		tool_call_id="tc_123",
		is_error=False,
	)
	assert tool_msg.tool_call_id == "tc_123"

	# tool fields forbidden on user/system
	with pytest.raises(ValueError, match="tool_call_id is only valid"):
		MessageCreate(type=MessageType.USER, content="hi", tool_call_id="tc")

	with pytest.raises(ValueError, match="is_error is only valid"):
		MessageCreate(type=MessageType.SYSTEM, content="sys", is_error=False)

	# tool_calls/usage forbidden on user/system
	with pytest.raises(ValueError, match="tool_calls is only valid"):
		MessageCreate(type=MessageType.USER, content="hi", tool_calls=[{"id": "x"}])

	with pytest.raises(ValueError, match="usage is only valid"):
		MessageCreate(type=MessageType.SYSTEM, content="sys", usage={"tokens": 1})

	# tool_calls/usage forbidden on tool messages
	with pytest.raises(ValueError, match="tool_calls is not valid"):
		MessageCreate(
			type=MessageType.TOOL,
			content="out",
			tool_call_id="tc",
			is_error=False,
			tool_calls=[{"id": "x"}],
		)

	# assistant allows tool_calls and usage
	assistant_msg = MessageCreate(
		type=MessageType.ASSISTANT,
		content="hi",
		tool_calls=[{"id": "tc", "name": "fn", "arguments": {}}],
		usage={"input_tokens": 1, "output_tokens": 2, "total_tokens": 3},
	)
	assert len(assistant_msg.tool_calls) == 1
	assert assistant_msg.usage is not None
