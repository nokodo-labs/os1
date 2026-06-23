"""Targeted coverage for ORM → SDK mapping helpers."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from api.models.message import Message, MessageType
from api.models.thread import Thread
from nokodo_ai.utils.typeid import TypeID, new_typeid


def _make_message(
	msg_type: object,
	content: list[dict[str, object]] | None = None,
) -> Message:
	content_value = content if content is not None else [{"type": "text", "text": "hi"}]
	return Message(
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
		read_by=[],
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

	unknown = _make_message(
		msg_type="other",
		content=[{"type": "text", "text": "x"}],
	)

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

	with pytest.raises(ValueError, match="unsupported message type"):
		unknown.to_sdk()


def test_message_to_sdk_tool_without_content() -> None:
	tool = _make_message(msg_type=MessageType.TOOL, content=[])
	tool.tool_call_id = "tc_1"
	tool.is_error = False
	tool_sdk = tool.to_sdk()
	assert tool_sdk.role == "tool"
	assert tool_sdk.tool_output == ""
	assert tool_sdk.tool_call_id == "tc_1"
	assert tool_sdk.is_error is False


def test_thread_to_sdk_no_current_message() -> None:
	thread = Thread(
		owner_id=TypeID(new_typeid("user")),
		title=None,
		tags=[],
		is_archived=False,
		is_temporary=False,
		spawned_from_message_id=None,
		current_message_id=None,
		metadata_={"a": 1},
	)
	thread.created_at = datetime.now(UTC)
	thread.messages = []

	sdk = thread.to_sdk()
	assert sdk.messages == []
	assert sdk.metadata == {"a": 1}


def test_thread_to_sdk_branch_and_missing_link() -> None:
	root = _make_message(msg_type=MessageType.USER)
	child = _make_message(msg_type=MessageType.ASSISTANT)
	child.parent_id = TypeID(root.id)

	thread = Thread(
		owner_id=TypeID(new_typeid("user")),
		title=None,
		tags=[],
		is_archived=False,
		is_temporary=False,
		spawned_from_message_id=None,
		current_message_id=TypeID(child.id),
		metadata_={},
	)
	thread.created_at = datetime.now(UTC)
	thread.messages = [root, child]

	sdk = thread.to_sdk()
	assert [m.role for m in sdk.messages] == ["user", "assistant"]

	thread.current_message_id = TypeID(new_typeid("msg"))
	sdk2 = thread.to_sdk()
	assert sdk2.messages == []


def test_thread_to_sdk_handles_parent_cycle() -> None:
	root = _make_message(msg_type=MessageType.USER)
	child = _make_message(msg_type=MessageType.ASSISTANT)

	# create a parent cycle: root -> child -> root
	root.parent_id = TypeID(child.id)
	child.parent_id = TypeID(root.id)

	thread = Thread(
		owner_id=TypeID(new_typeid("user")),
		title=None,
		tags=[],
		is_archived=False,
		is_temporary=False,
		spawned_from_message_id=None,
		current_message_id=TypeID(child.id),
		metadata_={},
	)
	thread.created_at = datetime.now(UTC)
	thread.messages = [root, child]

	sdk = thread.to_sdk()
	assert [m.role for m in sdk.messages] == ["user", "assistant"]
