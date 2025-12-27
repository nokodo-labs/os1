from collections.abc import AsyncIterator
from typing import TypedDict

import pytest

from nokodo_ai import (
	Agent,
	AssistantMessage,
	ChatModel,
	SystemMessage,
	Thread,
	ToolCall,
	ToolMessage,
	UserMessage,
	tool,
)
from nokodo_ai.adapters.chat import BaseChatAdapter, ChatGenerationParams
from nokodo_ai.tool import ToolExecutionContext


class _Call(TypedDict):
	messages: list[object]
	tools: object
	params: ChatGenerationParams
	stream: bool


class _StubChatAdapter(BaseChatAdapter):
	def __init__(self, responses: list[AssistantMessage]) -> None:
		self.responses = list(responses)
		self.calls: list[_Call] = []

	async def generate(
		self,
		messages,
		*,
		stream: bool = False,
		tools=None,
		params: ChatGenerationParams | None = None,
	) -> AssistantMessage | AsyncIterator[AssistantMessage]:
		params = params or ChatGenerationParams()
		self.calls.append(
			{
				"messages": list(messages),
				"tools": tools,
				"params": params,
				"stream": stream,
			}
		)
		if not self.responses:
			raise AssertionError("no more stub responses")
		return self.responses.pop(0)


@pytest.mark.asyncio
async def test_agent_runs_without_tools_returns_messages() -> None:
	"""agent.run() returns list of messages produced."""
	adapter = _StubChatAdapter([AssistantMessage.from_text("done")])
	llm = ChatModel(model="stub", adapter=adapter)
	agent = Agent(llm=llm)

	thread = Thread()
	thread.add(SystemMessage.from_text("be-kind"))
	thread.add(UserMessage.from_text("hello"))
	result = await agent.run(thread)

	assert isinstance(result, list)
	assert len(result) == 1
	assert result[0].text == "done"
	first_call = adapter.calls[0]
	messages = first_call["messages"]
	assert isinstance(messages, list)
	assert isinstance(messages[0], SystemMessage)
	assert messages[0].text == "be-kind"
	assert first_call["params"].tool_choice is None


@pytest.mark.asyncio
async def test_agent_executes_tool_and_returns_all_messages() -> None:
	"""agent returns assistant + tool messages when tools are called."""
	tool_call = ToolCall(id="tc1", name="echo", arguments={"text": "hi"})
	responses = [
		AssistantMessage(tool_calls=[tool_call]),
		AssistantMessage.from_text("all done"),
	]
	adapter = _StubChatAdapter(responses)
	llm = ChatModel(model="stub", adapter=adapter)

	@tool(description="echo input")
	def echo(text: str, *, __context: ToolExecutionContext) -> str:
		return f"{text}:{__context.call_id}"

	agent = Agent(llm=llm, tools=[echo])
	thread = Thread()
	thread.add(UserMessage.from_text("start"))
	result = await agent.run(thread)

	# should have: assistant with tool call, tool result, final assistant
	assert len(result) == 3
	assert isinstance(result[0], AssistantMessage)
	assert isinstance(result[1], ToolMessage)
	assert isinstance(result[2], AssistantMessage)
	assert result[1].tool_result.output == "hi:tc1"
	assert result[1].tool_result.is_error is False
	assert result[2].text == "all done"


@pytest.mark.asyncio
async def test_agent_respects_existing_thread_messages() -> None:
	"""agent works with pre-populated threads."""
	adapter = _StubChatAdapter([AssistantMessage.from_text("ok")])
	llm = ChatModel(model="stub", adapter=adapter)
	thread = Thread()
	thread.add(UserMessage.from_text("prior"))

	agent = Agent(llm=llm)
	result = await agent.run(thread)

	assert len(result) == 1
	assert result[0].text == "ok"
	# original message should still be in thread
	assert thread.messages[0].text == "prior"


@pytest.mark.asyncio
async def test_agent_handles_unknown_tool_gracefully() -> None:
	"""unknown tool names produce error tool messages."""
	responses = [
		AssistantMessage(tool_calls=[ToolCall(id="tc1", name="missing", arguments={})]),
		AssistantMessage.from_text("done"),
	]
	adapter = _StubChatAdapter(responses)
	llm = ChatModel(model="stub", adapter=adapter)
	calls: list[tuple[str, str, dict]] = []
	results: list[tuple[str, str, bool]] = []

	agent = Agent(
		llm=llm,
		tools=[],
		on_tool_call=lambda name, call_id, args: calls.append((name, call_id, args)),
		on_tool_result=lambda call_id, output, is_error: results.append(
			(call_id, output, is_error)
		),
	)

	thread = Thread()
	thread.add(UserMessage.from_text("hi"))
	result = await agent.run(thread)

	# should have: assistant with tool call, error tool message, final assistant
	assert len(result) == 3
	assert isinstance(result[1], ToolMessage)
	assert result[1].tool_result.is_error is True
	assert "unknown tool" in result[1].tool_result.output
	assert result[2].text == "done"
	assert calls == [("missing", "tc1", {})]
	assert results == [("tc1", result[1].tool_result.output, True)]


@pytest.mark.asyncio
async def test_agent_fallback_when_iteration_limit_hit() -> None:
	"""agent appends fallback message when max iterations reached."""
	responses = [
		AssistantMessage(tool_calls=[ToolCall(id="tc1", name="loop", arguments={})]),
		AssistantMessage(content=[]),
	]
	adapter = _StubChatAdapter(responses)
	llm = ChatModel(model="stub", adapter=adapter)
	agent = Agent(llm=llm, tools=[], max_iterations=1)

	thread = Thread()
	thread.add(UserMessage.from_text("repeat"))
	result = await agent.run(thread)

	assert isinstance(result, list)
	assert len(adapter.calls) == 2
	# last message should have fallback text
	last_msg = result[-1]
	assert isinstance(last_msg, AssistantMessage)
	assert "unable to complete" in last_msg.text


@pytest.mark.asyncio
async def test_agent_final_response_without_fallback() -> None:
	"""no fallback when llm responds with text before limit."""
	adapter = _StubChatAdapter([AssistantMessage.from_text("done")])
	llm = ChatModel(model="stub", adapter=adapter)
	agent = Agent(llm=llm, tools=[], max_iterations=0)

	thread = Thread()
	thread.add(UserMessage.from_text("hi"))
	result = await agent.run(thread)

	assert isinstance(result, list)
	last_msg = result[-1]
	assert isinstance(last_msg, AssistantMessage)
	assert last_msg.text == "done"
	assert "unable to complete" not in last_msg.text


@pytest.mark.asyncio
async def test_agent_executes_tool_callbacks_and_error_handling() -> None:
	"""on_tool_call and on_tool_result callbacks are invoked."""
	calls: list[tuple[str, str, dict]] = []
	results: list[tuple[str, str, bool]] = []

	@tool(description="good tool")
	def good_tool(value: int, *, __context: ToolExecutionContext) -> str:
		return f"ok:{value}:{__context.call_id}"

	@tool(description="bad tool")
	def bad_tool(_: int, *, __context: ToolExecutionContext) -> str:
		raise RuntimeError("boom")

	responses = [
		AssistantMessage(
			tool_calls=[
				ToolCall(id="good1", name="good_tool", arguments={"value": 1}),
				ToolCall(id="bad1", name="bad_tool", arguments={"value": 2}),
			]
		),
		AssistantMessage.from_text("done"),
	]

	adapter = _StubChatAdapter(responses)
	llm = ChatModel(model="stub", adapter=adapter)
	agent = Agent(
		llm=llm,
		tools=[good_tool, bad_tool],
		on_tool_call=lambda name, call_id, args: calls.append((name, call_id, args)),
		on_tool_result=lambda call_id, output, is_error: results.append(
			(call_id, output, is_error)
		),
	)

	thread = Thread()
	thread.add(UserMessage.from_text("start"))
	result = await agent.run(thread)

	assert isinstance(result, list)
	last_msg = result[-1]
	assert isinstance(last_msg, AssistantMessage)
	assert last_msg.text == "done"
	assert calls == [
		("good_tool", "good1", {"value": 1}),
		("bad_tool", "bad1", {"value": 2}),
	]
	assert ("good1", "ok:1:good1", False) in results
	# error output should be captured and flagged
	assert any(call_id == "bad1" and is_error for call_id, _, is_error in results)


@pytest.mark.asyncio
async def test_agent_tool_error_without_result_callback() -> None:
	"""tool errors are captured even without on_tool_result callback."""

	@tool(description="explodes")
	def explode(*, __context: ToolExecutionContext) -> str:
		raise RuntimeError("kaboom")

	responses = [
		AssistantMessage(
			tool_calls=[ToolCall(id="err1", name="explode", arguments={})]
		),
		AssistantMessage.from_text("ok"),
	]

	adapter = _StubChatAdapter(responses)
	llm = ChatModel(model="stub", adapter=adapter)
	agent = Agent(llm=llm, tools=[explode])

	thread = Thread()
	thread.add(UserMessage.from_text("start"))
	result = await agent.run(thread)

	assert isinstance(result, list)
	# result[1] should be the tool error message
	assert isinstance(result[1], ToolMessage)
	assert result[1].tool_result.is_error is True
	assert "error executing tool" in result[1].tool_result.output
	last_msg = result[-1]
	assert isinstance(last_msg, AssistantMessage)
	assert last_msg.text == "ok"
