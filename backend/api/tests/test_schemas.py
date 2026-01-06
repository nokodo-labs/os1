"""Schema-specific unit tests for ORM-aware validators."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from api.models.project import Project as ProjectModel
from api.models.thread import Thread as ThreadModel
from api.schemas.content import TextContent
from api.schemas.message import MessageCreate
from api.schemas.project import Project as ProjectSchema
from api.schemas.prompt import PromptCreate, PromptUpdate
from api.schemas.runs import ThreadRunRequest
from api.schemas.thread import Thread as ThreadSchema
from api.schemas.thread import ThreadSummary
from nokodo_ai.utils.typeid import new_typeid


def _stamp_project(project: ProjectModel, *, project_id: str) -> ProjectModel:
	project.id = project_id
	project.metadata_ = {}
	project.created_at = datetime.now(tz=UTC)
	project.updated_at = datetime.now(tz=UTC)
	return project


def _stamp_thread(thread: ThreadModel, *, thread_id: str) -> ThreadModel:
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


def test_project_schema_respects_existing_thread_ids() -> None:
	owner_id = new_typeid("user")
	preloaded_thread_id = new_typeid("thread")
	project = _stamp_project(
		ProjectModel(name="Schema", description="Test", owner_id=owner_id),
		project_id=new_typeid("proj"),
	)
	project.thread_ids = [preloaded_thread_id]
	project.threads = []

	serialized = ProjectSchema.model_validate(project)
	assert serialized.thread_ids == [preloaded_thread_id]


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
	from_list = MessageCreate(content=[part_dict, model_part])
	from_empty = MessageCreate(content="")

	assert from_str.content[0]["text"] == text
	assert from_list.content == [part_dict, model_part.model_dump()]
	assert from_empty.content == []


def test_prompt_schema_validates_and_normalizes() -> None:
	valid = PromptCreate(command="my-prompt", content="body")
	assert valid.command == "/my-prompt"

	updated = PromptUpdate(command="/next", content="x")
	assert updated.command == "/next"

	with pytest.raises(ValueError):
		PromptCreate(command="not ok!", content="bad")


def test_prompt_schema_none_and_blank_commands() -> None:
	update = PromptUpdate(command=None, content=None)
	assert update.command is None

	with pytest.raises(ValueError):
		PromptCreate(command="   ", content="x")


def test_thread_run_request_requires_agent_id() -> None:
	"""agent_id is now required for thread run requests."""
	with pytest.raises(ValueError):
		ThreadRunRequest()  # type: ignore[call-arg]

	req = ThreadRunRequest(agent_id=new_typeid("agent"))
	assert req.agent_id is not None
	assert req.stream is True
	assert req.input is None

	req_with_input = ThreadRunRequest(agent_id=new_typeid("agent"), input="hello")
	assert req_with_input.stream is True
	assert req_with_input.input == "hello"


def test_thread_schema_defaults_for_flags() -> None:
	thread = _stamp_thread(
		ThreadModel(owner_id=new_typeid("user")), thread_id=new_typeid("thread")
	)
	thread.is_temporary = None  # type: ignore[assignment]
	thread.is_archived = None  # type: ignore[assignment]

	serialized = ThreadSchema.model_validate(thread)
	assert serialized.is_temporary is False
	assert serialized.is_archived is False
