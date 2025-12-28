"""tests for SDK message and thread models."""

import pytest

from nokodo_ai import (
	AssistantMessage,
	JsonContent,
	RefusalContent,
	SystemMessage,
	TextContent,
	Thread,
	ToolCall,
	ToolMessage,
	UserMessage,
)
from nokodo_ai.message import _HasTextContentHelpers


def test_user_message_creation() -> None:
	msg = UserMessage.from_text("hello")
	assert len(msg.content) == 1
	assert isinstance(msg.content[0], TextContent)
	assert msg.text == "hello"


def test_assistant_message_creation() -> None:
	msg = AssistantMessage.from_text("hi there")
	assert msg.text == "hi there"
	assert msg.tool_calls == []


def test_assistant_message_with_tool_calls() -> None:
	tool_call = ToolCall(id="call_1", name="get_weather", arguments={"city": "paris"})
	msg = AssistantMessage(content=[], tool_calls=[tool_call])
	assert len(msg.tool_calls) == 1
	assert msg.tool_calls[0].name == "get_weather"
	assert msg.tool_calls[0].arguments["city"] == "paris"


def test_tool_call_default_id_is_set() -> None:
	tool_call = ToolCall(name="get_weather")
	assert tool_call.id != ""


def test_tool_message_creation() -> None:
	msg = ToolMessage(tool_call_id="call_1", tool_output="sunny")
	assert msg.tool_output == "sunny"
	assert msg.is_error is False


def test_tool_result_error() -> None:
	msg = ToolMessage(tool_call_id="call_1", tool_output="not found", is_error=True)
	assert msg.is_error is True


def test_system_message_creation() -> None:
	msg = SystemMessage.from_text("you are a helpful assistant")
	assert msg.text == "you are a helpful assistant"


def test_thread_creation_empty() -> None:
	thread = Thread()
	assert len(thread.messages) == 0


def test_thread_add_messages() -> None:
	thread = Thread()
	thread.add(UserMessage.from_text("hello"))
	thread.add(AssistantMessage.from_text("hi"))
	assert len(thread.messages) == 2


def test_assistant_json_and_refusal_helpers() -> None:
	msg = AssistantMessage(
		content=[
			JsonContent(data={"foo": "bar"}),
			RefusalContent(reason="nope"),
		],
	)
	assert msg.json == {"foo": "bar"}
	assert msg.refusal == "nope"

	plain = AssistantMessage.from_text("hi")
	assert plain.json is None
	assert plain.refusal is None


def test_text_content_helpers_raise() -> None:
	class Dummy(_HasTextContentHelpers):
		"""dummy helper implementation"""

		pass

	dummy = Dummy()
	with pytest.raises(NotImplementedError):
		Dummy.from_text("x")

	with pytest.raises(NotImplementedError):
		_ = dummy.text
