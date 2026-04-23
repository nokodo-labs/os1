"""Extra coverage for SDK models and errors."""

from __future__ import annotations

from typing import cast
from uuid import uuid4

from nokodo_ai.models import (
	AssistantMessage,
	BaseMessage,
	ConflictError,
	Message,
	MessageStore,
	MessageType,
	NotFoundError,
	StoreError,
	Thread,
	ThreadStore,
	ToolMessage,
	UserMessage,
)
from nokodo_ai.utils.typeid import new_typeid


def test_module_exports() -> None:
	thread = Thread(id=new_typeid("thread"), owner_id=new_typeid("user"))
	assert thread.id
	assert issubclass(StoreError, Exception)
	assert MessageType.USER.value == "user"
	assert MessageStore is not None and ThreadStore is not None


def test_chat_validators_coerce_identifiers() -> None:
	msg: Message = UserMessage(
		id=new_typeid("msg"),
		thread_id=cast(str, uuid4()),
		parent_id=None,
		content="c",
		type=MessageType.USER,
	)
	assert isinstance(msg.thread_id, str)
	assistant = AssistantMessage(
		id=new_typeid("msg"),
		thread_id=msg.thread_id,
		parent_id=msg.id,
		content="a",
		type=MessageType.ASSISTANT,
		read_by=cast(list[str], {new_typeid("user")}),
	)
	assert assistant.read_by and isinstance(assistant.read_by[0], str)
	tool = ToolMessage(
		id=new_typeid("msg"),
		thread_id=msg.thread_id,
		parent_id=msg.id,
		content="t",
		type=MessageType.TOOL,
	)
	assert tool.parent_id == msg.id
	base = BaseMessage(
		id=new_typeid("msg"),
		thread_id=msg.thread_id,
		content="b",
		type=MessageType.SYSTEM,
	)
	assert base.read_by == []

	none_read = UserMessage(
		id=new_typeid("msg"),
		thread_id=msg.thread_id,
		content="n",
		type=MessageType.USER,
		read_by=cast(list[str], None),
	)
	assert none_read.read_by == []

	string_read = UserMessage(
		id=new_typeid("msg"),
		thread_id=msg.thread_id,
		content="s",
		type=MessageType.USER,
		read_by=cast(list[str], "user-single"),
	)
	assert string_read.read_by == ["user-single"]

	int_read = UserMessage(
		id=new_typeid("msg"),
		thread_id=msg.thread_id,
		content="i",
		type=MessageType.USER,
		read_by=cast(list[str], 123),
	)
	assert int_read.read_by == ["123"]

	assert BaseMessage._coerce_read_by({456}) == ["456"]
	assert BaseMessage._coerce_read_by("raw") == ["raw"]


def test_store_errors_capture_details() -> None:
	nf = NotFoundError("thread", "missing")
	assert "thread" in str(nf)
	assert nf.entity == "thread"
	conflict = ConflictError("bad state")
	assert str(conflict) == "bad state"
