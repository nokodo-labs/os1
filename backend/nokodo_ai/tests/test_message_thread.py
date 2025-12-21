"""tests for SDK message and thread models."""

from nokodo_ai import (
	AssistantMessage,
	SystemMessage,
	Thread,
	ToolCall,
	ToolMessage,
	ToolResult,
	UserMessage,
)


def test_user_message_creation() -> None:
	msg = UserMessage(content="hello")
	assert msg.content == "hello"


def test_assistant_message_creation() -> None:
	msg = AssistantMessage(content="hi there")
	assert msg.content == "hi there"
	assert msg.tool_calls is None


def test_assistant_message_with_tool_calls() -> None:
	tool_call = ToolCall(id="call_1", name="get_weather", arguments='{"city": "paris"}')
	msg = AssistantMessage(content="", tool_calls=[tool_call])
	assert msg.tool_calls is not None
	assert len(msg.tool_calls) == 1
	assert msg.tool_calls[0].name == "get_weather"


def test_tool_message_creation() -> None:
	result = ToolResult(tool_call_id="call_1", content="sunny")
	msg = ToolMessage(tool_results=[result])
	assert len(msg.tool_results) == 1
	assert msg.tool_results[0].content == "sunny"
	assert msg.tool_results[0].is_error is False


def test_tool_result_error() -> None:
	result = ToolResult(tool_call_id="call_1", content="not found", is_error=True)
	assert result.is_error is True


def test_system_message_creation() -> None:
	msg = SystemMessage(content="you are a helpful assistant")
	assert msg.content == "you are a helpful assistant"


def test_thread_creation_empty() -> None:
	thread = Thread()
	assert len(thread.messages) == 0


def test_thread_add_messages() -> None:
	thread = Thread()
	thread.add(UserMessage(content="hello"))
	thread.add(AssistantMessage(content="hi"))
	assert len(thread.messages) == 2
