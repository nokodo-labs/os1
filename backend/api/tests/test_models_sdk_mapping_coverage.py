"""Targeted coverage for ORM → SDK mapping helpers."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.message import Message, MessageType
from api.models.thread import Thread
from api.models.user import User
from nokodo_ai.messages import AssistantMessage as SDKAssistantMessage
from nokodo_ai.messages import ToolMessage as SDKToolMessage
from nokodo_ai.utils.typeid import TypeID, new_typeid


def _make_message(
	msg_type: MessageType,
	content: list[dict[str, object]] | None = None,
) -> Message:
	content_value = content if content is not None else [{"type": "text", "text": "hi"}]
	message_cls = Message.__mapper__.polymorphic_map[msg_type].class_
	return message_cls(
		id=TypeID(new_typeid("msg")),
		thread_id=TypeID(new_typeid("thread")),
		parent_id=None,
		task_id=None,
		sender_agent_id=None,
		sender_user_id=None,
		type=msg_type,
		content=content_value,
		tool_call_id=None,
		is_error=None,
		tool_calls=[],
		usage=None,
		metadata_={},
	)


def test_message_to_sdk_all_types() -> None:
	user = _make_message(msg_type=MessageType.USER)
	system = _make_message(msg_type=MessageType.SYSTEM)
	assistant = _make_message(
		msg_type=MessageType.ASSISTANT,
		content=[{"type": "text", "text": "ok"}],
	)
	assistant.tool_calls = [
		{"id": "tc_1", "name": "t", "arguments": {"a": 1}, "metadata": None}
	]
	assistant.usage = {"input_tokens": 1, "output_tokens": 2, "total_tokens": 3}

	tool = _make_message(
		msg_type=MessageType.TOOL,
		content=[{"type": "text", "text": "tool output"}],
	)
	tool.tool_call_id = "tc_1"
	tool.is_error = True

	assert user.to_sdk().role == "user"
	assert system.to_sdk().role == "system"
	assistant_sdk = assistant.to_sdk()
	assert assistant_sdk.role == "assistant"
	assert assistant_sdk.usage is not None
	assert assistant_sdk.usage.total_tokens == 3
	assert len(assistant_sdk.tool_calls) == 1

	tool_sdk = tool.to_sdk()
	assert tool_sdk.role == "tool"
	assert tool_sdk.tool_call_id == "tc_1"
	assert tool_sdk.tool_output == "tool output"
	assert tool_sdk.is_error is True


def test_message_to_sdk_tool_without_content() -> None:
	tool = _make_message(msg_type=MessageType.TOOL, content=[])
	tool.tool_call_id = "tc_1"
	tool.is_error = False
	tool_sdk = tool.to_sdk()
	assert tool_sdk.role == "tool"
	assert tool_sdk.tool_output == ""
	assert tool_sdk.tool_call_id == "tc_1"
	assert tool_sdk.is_error is False


def test_message_to_sdk_tool_keeps_all_text_parts() -> None:
	tool = _make_message(
		msg_type=MessageType.TOOL,
		content=[
			{"type": "text", "text": "first"},
			{"type": "text", "text": "second"},
		],
	)
	tool.tool_call_id = "tc_1"
	tool.is_error = False

	tool_sdk = tool.to_sdk()
	assert tool_sdk.role == "tool"
	assert tool_sdk.tool_output == "firstsecond"


def test_message_to_sdk_rejects_an_unknown_finish_reason() -> None:
	"""a stored value outside the enum is a bug, not something to paper over.

	renames ship with a data migration, so nothing legitimate can produce one;
	silently nulling it would only hide whoever wrote it.
	"""
	assistant = _make_message(msg_type=MessageType.ASSISTANT)
	assistant.__dict__["finish_reason"] = "invalid"

	with pytest.raises(ValidationError):
		assistant.to_sdk()


@pytest.mark.asyncio
async def test_an_unknown_finish_reason_fails_at_the_write(
	db_session: AsyncSession,
) -> None:
	"""the column constrains the value, so no read ever has to cope with a bad one.

	failing here is the point: a row that got past the write would make every
	later load of its conversation raise, forever.
	"""
	owner = User(
		email="finish_reason_check@example.com",
		username="finish_reason_check",
		hashed_password="password",
		is_active=True,
	)
	db_session.add(owner)
	await db_session.flush()
	thread = Thread(owner_id=owner.id)
	db_session.add(thread)
	await db_session.flush()

	message_cls = Message.__mapper__.polymorphic_map[MessageType.ASSISTANT].class_
	db_session.add(
		message_cls(
			thread_id=thread.id,
			type=MessageType.ASSISTANT,
			content=[],
			tool_calls=[],
			finish_reason="stop",
		)
	)

	with pytest.raises(IntegrityError):
		await db_session.flush()


def test_malformed_tool_call_keeps_its_id_so_its_result_stays_paired() -> None:
	"""a tool result whose call vanished is rejected by every provider."""
	assistant = _make_message(msg_type=MessageType.ASSISTANT)
	assistant.tool_calls = [{"id": "tc_1", "name": 42}]

	sdk = assistant.to_sdk()
	assert isinstance(sdk, SDKAssistantMessage)
	assert [call.id for call in sdk.tool_calls] == ["tc_1"]
	assert sdk.tool_calls[0].name == ""


def test_malformed_tool_call_without_an_id_is_dropped() -> None:
	"""nothing references it, so there is no pairing left to preserve."""
	assistant = _make_message(msg_type=MessageType.ASSISTANT)
	assistant.tool_calls = [{"name": 42}]

	sdk = assistant.to_sdk()
	assert isinstance(sdk, SDKAssistantMessage)
	assert sdk.tool_calls == []


def test_tool_message_without_a_call_id_gets_a_synthetic_one() -> None:
	"""one legacy row must not break loading the conversation it sits in."""
	tool = _make_message(msg_type=MessageType.TOOL, content=[])
	tool.tool_call_id = None

	sdk = tool.to_sdk()
	assert isinstance(sdk, SDKToolMessage)
	assert sdk.tool_call_id == f"tool_call_{tool.id}"
