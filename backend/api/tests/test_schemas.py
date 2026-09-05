"""Schema-specific unit tests for ORM-aware validators."""

from __future__ import annotations

import dataclasses
import importlib
import pkgutil
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import get_args

import pytest
from pydantic import BaseModel, ValidationError

import api.schemas
from api.constants import PRIVATE_METADATA_KEY
from api.models.message import MessageType
from api.models.message import UserMessage as MessageModel
from api.models.project import Project as ProjectModel
from api.models.thread import Thread as ThreadModel
from api.schemas.common import PrivateFacetModel
from api.schemas.event import Event as EventSchema
from api.schemas.file import FileUpdate
from api.schemas.message import Message as MessageSchema
from api.schemas.message import (
	MessageCreate,
	MessageUpdate,
	TextContent,
)
from api.schemas.project import Project as ProjectSchema
from api.schemas.prompt import PromptCreate, PromptUpdate
from api.schemas.runs import RunRequest, ThreadCreateAndRunRequest
from api.schemas.thread import Thread as ThreadSchema
from api.schemas.thread import ThreadSummary, ThreadUpdate
from api.v1.service.chat.message_metadata import (
	split_sdk_metadata,
	strip_private_sdk_metadata,
)
from api.v1.service.threads.drafts import MessageDraft
from nokodo_ai.utils.typeid import new_typeid


def _all_schema_models() -> list[type[BaseModel]]:
	"""every pydantic model defined anywhere under ``api.schemas``."""
	found: dict[str, type[BaseModel]] = {}
	for info in pkgutil.walk_packages(
		api.schemas.__path__, prefix=f"{api.schemas.__name__}."
	):
		module = importlib.import_module(info.name)
		for value in vars(module).values():
			if isinstance(value, type) and issubclass(value, BaseModel):
				found[f"{value.__module__}.{value.__qualname__}"] = value
	return list(found.values())


def _annotated_types(annotation: object) -> list[type]:
	"""flatten an annotation to the concrete classes it can hold."""
	if isinstance(annotation, type):
		return [annotation]
	return [t for arg in get_args(annotation) for t in _annotated_types(arg)]


def _annotated_models(
	annotation: object, seen: set[type[BaseModel]] | None = None
) -> set[type[BaseModel]]:
	"""every pydantic model an annotation can hold, including nested ones."""
	found = seen if seen is not None else set()
	for candidate in _annotated_types(annotation):
		if (
			isinstance(candidate, type)
			and issubclass(candidate, BaseModel)
			and candidate not in found
		):
			found.add(candidate)
			for field in candidate.model_fields.values():
				_annotated_models(field.annotation, found)
	return found


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


def test_split_sdk_metadata_separates_prefixed_keys() -> None:
	"""the SDK boundary splits its flat dict into the two stored halves."""
	public, private = split_sdk_metadata(
		{
			"run_id": "run_123",
			"steering_state": "queued",
			"_provider_data": {"provider": {"tool_call_id": "call_secret"}},
			"_citations_assigned": True,
		}
	)

	assert public == {"run_id": "run_123", "steering_state": "queued"}
	assert private == {
		"provider_data": {"provider": {"tool_call_id": "call_secret"}},
		"citations_assigned": True,
	}


def test_wire_cannot_use_the_row_metadata_alias() -> None:
	"""``public_metadata`` is an ORM accessor name, not part of the contract.

	regression: ``populate_by_name`` made the validation alias a second
	accepted request key, putting an internal SQLAlchemy workaround on the
	public API. reading a row through the alias must keep working.
	"""
	with pytest.raises(ValidationError):
		MessageCreate.model_validate({"content": "x", "public_metadata": {"a": 1}})

	now = datetime.now(UTC)
	row = MessageModel(
		id=new_typeid("msg"),
		thread_id=new_typeid("thread"),
		type=MessageType.USER,
		content=[],
		tool_calls=[],
		citations=[],
		created_at=now,
		updated_at=now,
	)
	row.set_metadata(public={"visible": 1}, private={"hidden": 2})
	assert MessageSchema.from_row(row).metadata == {"visible": 1}


def test_public_metadata_rejects_the_reserved_key() -> None:
	"""a client cannot address the private namespace through public metadata."""
	with pytest.raises(ValidationError):
		MessageCreate(content="x", metadata={PRIVATE_METADATA_KEY: {"forged": 1}})

	with pytest.raises(ValidationError):
		MessageUpdate(content="c", metadata={PRIVATE_METADATA_KEY: {"forged": 1}})


def test_wire_message_schemas_cannot_carry_a_private_facet() -> None:
	"""no wire message schema can express private metadata.

	regression: the router used to bind a type carrying ``private``, letting
	any thread editor forge backend-owned metadata.
	"""
	for schema in (MessageCreate, MessageUpdate):
		assert "private" not in schema.model_fields
		with pytest.raises(ValidationError):
			schema.model_validate(
				{"content": "x", "private": {"metadata": {"forged": 1}}}
			)

	# and a stray unknown field is a 422, never a silent drop.
	with pytest.raises(ValidationError):
		MessageCreate.model_validate({"content": "x", "bogus_field": 1})

	# the draft is what carries private metadata, and it is not a pydantic
	# model, so it can never be bound from a request body.
	draft = MessageDraft.from_request(MessageCreate(content="x"))
	draft.private_metadata["stamped"] = 1
	assert not isinstance(draft, BaseModel)


def test_message_draft_carries_every_wire_field() -> None:
	"""a new ``MessageCreate`` field must be copied by ``from_request``.

	the conversion is field-by-field, so an uncovered field would be accepted
	on the wire and silently dropped before persistence.
	"""
	carried = {field.name for field in dataclasses.fields(MessageDraft)}
	operation_fields = {"originated_resources"}
	assert set(MessageCreate.model_fields) <= carried | operation_fields


def test_touched_write_schemas_reject_stray_flat_private_fields() -> None:
	"""a field that moved into `private` must 422 at its old flat home."""
	with pytest.raises(ValidationError):
		FileUpdate.model_validate({"storage_key": "tenant/forged.bin"})

	with pytest.raises(ValidationError):
		ThreadUpdate.model_validate({"bogus_field": 1})


# schemas that tolerate unknown keys ON PURPOSE, each for a stated reason.
LENIENT_REQUEST_MODELS = {
	# stored as JSONB so the admin console can round-trip keys the backend
	# does not model yet.
	"AgentConfig",
	"AgentFeatures",
	"SteeringFeature",
	"UserMCPToolsFeature",
	"InvokeOnMentionFeature",
	# validated from stored columns that may predate a field being added.
	"UserPreferences",
	"UserPrivacy",
	"DefaultPermissions",
	"DefaultResourceAccess",
	# third-party openai clients send params we do not model.
	"OpenAIChatCompletionRequest",
	"OpenAIChatMessage",
}


def test_every_request_body_schema_forbids_unknown_fields() -> None:
	"""an unknown field in a request body is a 422, never a silent drop.

	pydantic's default is to IGNORE unknown keys, so a client that misspells
	a field, or sends one that has since moved, gets 200 and a no-op - it
	reports success while doing nothing. this walks the real route table so a
	schema added later is covered without being listed here; deliberate
	exceptions go in ``LENIENT_REQUEST_MODELS`` with a reason.
	"""
	from fastapi.routing import APIRoute

	from api.main import app

	models: set[type[BaseModel]] = set()
	for route in app.routes:
		if not isinstance(route, APIRoute):
			continue
		for param in route.dependant.body_params:
			for model in _annotated_models(param.field_info.annotation):
				models.add(model)

	offenders = sorted(
		f"{model.__module__}.{model.__name__}"
		for model in models
		if model.model_config.get("extra") != "forbid"
		and model.__name__ not in LENIENT_REQUEST_MODELS
	)
	assert not offenders, (
		"request-body schemas that silently drop unknown fields; add "
		'extra="forbid" (or an entry in LENIENT_REQUEST_MODELS): '
		+ ", ".join(offenders)
	)


# nested facets whose builder projects them itself, with the builder named.
SELF_PROJECTED_NESTED_FACETS = {
	# members.attach_last_messages runs the message through message_payloads
	# before assigning it, since project_private stops at the thread.
	"Thread.last_message",
}


def test_no_response_schema_nests_a_private_facet() -> None:
	"""``project_private`` only reaches the top level, so nesting is banned.

	return a nested resource through its own projected endpoint, embed only
	its id, or project the nested payload in its builder and list it in
	``SELF_PROJECTED_NESTED_FACETS``.
	"""
	offenders: list[str] = []
	for schema in _all_schema_models():
		# a parametrized generic (Page[Thread]) declares a type variable, so
		# the guard belongs on the generic class itself.
		generic = getattr(schema, "__pydantic_generic_metadata__", None)
		if generic and generic["origin"] is not None:
			continue
		for name, field in schema.model_fields.items():
			if schema is PrivateFacetModel or name == "private":
				continue
			if f"{schema.__name__}.{name}" in SELF_PROJECTED_NESTED_FACETS:
				continue
			for nested in _annotated_types(field.annotation):
				if issubclass(nested, PrivateFacetModel):
					offenders.append(f"{schema.__name__}.{name}: {nested.__name__}")

	assert not offenders, (
		"private facets nested inside another schema are never projected: "
		+ ", ".join(sorted(offenders))
	)


def test_metadata_dumps_use_the_plain_field_name() -> None:
	"""the SQLAlchemy `metadata_` workaround no longer reaches the wire."""
	message = MessageCreate(content="x", metadata={"client_key": "value"})
	assert message.model_dump()["metadata"] == {"client_key": "value"}

	# unset metadata stays excluded from partial dumps
	empty = MessageUpdate(content="c")
	assert "metadata" not in empty.model_dump(exclude_unset=True)


def test_strip_private_sdk_metadata_walks_nested_payloads() -> None:
	"""SSE deltas are SDK-shaped, so prefixed keys are dropped on the way out."""
	payload = {
		"metadata": {"_provider_data": 1, "public": 2},
		"tool_calls": [{"id": "tc", "metadata": {"_provider_data": {}, "run_id": "r"}}],
		"text": "hi",
	}

	assert strip_private_sdk_metadata(payload) == {
		"metadata": {"public": 2},
		"tool_calls": [{"id": "tc", "metadata": {"run_id": "r"}}],
		"text": "hi",
	}


def test_message_payload_defaults_to_the_public_view() -> None:
	"""a payload built without ``from_row`` carries no private facet."""
	now = datetime.now(tz=UTC)
	message = MessageSchema(
		id=new_typeid("msg"),
		thread_id=new_typeid("thread"),
		type=MessageType.TOOL,
		content=[],
		tool_call_id="call_123",
		is_error=False,
		metadata={"run_id": "run_123"},
		created_at=now,
		updated_at=now,
	)

	payload = message.model_dump(mode="json")

	assert payload["metadata"] == {"run_id": "run_123"}
	assert payload["private"] is None


def test_prompt_schema_validates_and_normalizes() -> None:
	valid = PromptCreate(command="my-prompt", content="body")
	assert valid.command == "my-prompt"

	updated = PromptUpdate(command="/next", content="x")
	assert updated.command == "next"

	with pytest.raises(ValueError):
		PromptCreate(command="not ok!", content="bad")


def test_prompt_schema_omits_and_rejects_null_commands() -> None:
	update = PromptUpdate()
	assert update.model_dump(exclude_unset=True) == {}

	with pytest.raises(ValueError):
		PromptUpdate(command=None, content=None)

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

	req_with_input = RunRequest(
		agent_id=new_typeid("agent"),
		input=MessageCreate(content=[TextContent(text="hello")]),
	)
	assert req_with_input.input is not None
	assert req_with_input.input.content == [TextContent(text="hello")]

	# ThreadCreateAndRunRequest

	car_req = ThreadCreateAndRunRequest(
		agent_id=new_typeid("agent"),
		input=MessageCreate(content=[TextContent(text="hi")]),
	)
	assert car_req.is_temporary is False
	assert car_req.tags == []


def test_thread_schema_defaults_for_flags() -> None:
	thread = _stamp_thread(
		ThreadModel(owner_id=new_typeid("user")), thread_id=new_typeid("thread")
	)
	thread.is_temporary = None  # type: ignore[assignment]

	serialized = ThreadSchema.model_validate(thread)
	assert serialized.is_temporary is False


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
		MessageCreate(
			type=MessageType.USER,
			content="hi",
			tool_calls=[{"id": "x", "name": "tool", "arguments": {}}],
		)

	with pytest.raises(ValueError, match="usage is only valid"):
		MessageCreate(
			type=MessageType.SYSTEM,
			content="sys",
			usage={"input_tokens": 1},
		)

	# tool_calls/usage forbidden on tool messages
	with pytest.raises(ValueError, match="tool_calls is not valid"):
		MessageCreate(
			type=MessageType.TOOL,
			content="out",
			tool_call_id="tc",
			is_error=False,
			tool_calls=[{"id": "x", "name": "tool", "arguments": {}}],
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

	with pytest.raises(ValueError, match="String should have at most 90 characters"):
		MessageCreate(
			type=MessageType.TOOL,
			content="output",
			tool_call_id="x" * 91,
			is_error=False,
		)


@pytest.mark.parametrize(
	"key",
	[
		"run_id",
		"agent_id",
		"steering_state",
		"steering_enqueued_at",
		"steering_injected_at",
		"steering_dropped_at",
	],
)
def test_message_create_rejects_server_owned_run_metadata(key: str) -> None:
	with pytest.raises(ValueError, match="server-owned run fields"):
		MessageCreate(content="hello", metadata={key: "forged"})
