"""tests for SDK Agent class."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable

import pytest
from pydantic import PrivateAttr

from nokodo_ai import (
	Agent,
	AgentContext,
	AssistantMessage,
	ChatModel,
	SystemMessage,
	Thread,
	Tool,
	ToolCall,
	ToolMessage,
	UserMessage,
)
from nokodo_ai.adapters.base.chat import BaseChatAdapter, ChatGenerationParams
from nokodo_ai.filters import Filter
from nokodo_ai.hooks import Hook
from nokodo_ai.tool import ToolDefinition


class _QueuedChatAdapter(BaseChatAdapter):
	_sync_responses: list[AssistantMessage] = PrivateAttr()
	_stream_responses: list[list[AssistantMessage]] = PrivateAttr()
	_calls: list[dict[str, object]] = PrivateAttr(default_factory=list)

	def __init__(
		self,
		*,
		sync_responses: list[AssistantMessage] | None = None,
		stream_responses: list[list[AssistantMessage]] | None = None,
	) -> None:
		super().__init__()
		self._sync_responses = list(sync_responses or [])
		self._stream_responses = list(stream_responses or [])

	@property
	def calls(self) -> list[dict[str, object]]:
		return self._calls

	def generate(
		self,
		messages,
		model: str,
		stream: bool = False,
		tools: list[ToolDefinition] = [],
		params: ChatGenerationParams | None = None,
	) -> Awaitable[AssistantMessage] | AsyncIterator[AssistantMessage]:
		self._calls.append(
			{
				"messages": list(messages),
				"model": model,
				"stream": stream,
				"tools": tools,
				"params": params or ChatGenerationParams(),
			}
		)
		if stream:
			chunks = self._stream_responses.pop(0) if self._stream_responses else []

			async def _gen() -> AsyncIterator[AssistantMessage]:
				for chunk in chunks:
					yield chunk

			return _gen()

		if not self._sync_responses:
			raise AssertionError("no more sync responses")
		response = self._sync_responses.pop(0)

		async def _resp() -> AssistantMessage:
			return response

		return _resp()


def _make_chat_model(adapter: BaseChatAdapter) -> ChatModel:
	return ChatModel.model_construct(
		provider="openai",
		api=None,
		model_name="stub",
		adapter=adapter,
	)


class _EchoTool(Tool[None]):
	async def call(
		self,
		__agent_context__: AgentContext,
		__app_context__: None,
		*,
		text: str,
	) -> ToolMessage:
		return self.success(
			f"{text}:{__agent_context__.tool_call_id}",
			__agent_context__,
		)


class _ExplodingTool(Tool[None]):
	async def call(
		self,
		__agent_context__: AgentContext,
		__app_context__: None,
		**kwargs: object,
	) -> ToolMessage:
		raise RuntimeError("boom")


@pytest.mark.asyncio
async def test_agent_sync_without_tools_tool_choice_none() -> None:
	adapter = _QueuedChatAdapter(sync_responses=[AssistantMessage.from_text("done")])
	chat_model = _make_chat_model(adapter)
	agent = Agent(chat_model=chat_model)
	thread = Thread()
	thread.add(SystemMessage.from_text("be-kind"))
	thread.add(UserMessage.from_text("hello"))

	result = await agent.run(thread)

	assert len(result) == 1
	assert isinstance(result[0], AssistantMessage)
	assert result[0].text == "done"
	call = adapter.calls[-1]
	params = call["params"]
	assert isinstance(params, ChatGenerationParams)
	assert params.tool_choice is None
	assert call["tools"] == []


@pytest.mark.asyncio
async def test_agent_sync_executes_tool_with_dict_args_and_metadata() -> None:
	adapter = _QueuedChatAdapter(
		sync_responses=[
			AssistantMessage(
				tool_calls=[
					ToolCall(
						id="tc1",
						name="echo",
						arguments={"text": "hi"},
						metadata={"x": "y"},
					)
				]
			),
			AssistantMessage.from_text("done"),
		]
	)
	chat_model = _make_chat_model(adapter)
	agent = Agent(
		chat_model=chat_model,
		tools=[_EchoTool(name="echo", description="echo")],
	)
	thread = Thread()
	thread.add(UserMessage.from_text("start"))

	result = await agent.run(thread)

	assert len(result) == 3
	assert isinstance(result[1], ToolMessage)
	assert result[1].tool_output == "hi:tc1"
	assert result[1].metadata == {"x": "y"}
	last = result[-1]
	assert isinstance(last, AssistantMessage)
	assert last.text == "done"


@pytest.mark.asyncio
async def test_agent_sync_executes_tool_with_json_string_args() -> None:
	adapter = _QueuedChatAdapter(
		sync_responses=[
			AssistantMessage(
				tool_calls=[
					ToolCall(
						id="tc1",
						name="echo",
						arguments='{"text": "hi"}',
					)
				]
			),
			AssistantMessage.from_text("done"),
		]
	)
	chat_model = _make_chat_model(adapter)
	agent = Agent(
		chat_model=chat_model,
		tools=[_EchoTool(name="echo", description="echo")],
	)
	thread = Thread()
	thread.add(UserMessage.from_text("start"))

	result = await agent.run(thread)

	tool_msg = next(m for m in result if isinstance(m, ToolMessage))
	assert tool_msg.tool_output == "hi:tc1"


@pytest.mark.asyncio
async def test_agent_sync_invalid_json_args_returns_error() -> None:
	adapter = _QueuedChatAdapter(
		sync_responses=[
			AssistantMessage(
				tool_calls=[ToolCall(id="tc1", name="echo", arguments="{bad")]
			),
			AssistantMessage.from_text("done"),
		]
	)
	chat_model = _make_chat_model(adapter)
	agent = Agent(
		chat_model=chat_model,
		tools=[_EchoTool(name="echo", description="echo")],
	)
	thread = Thread()
	thread.add(UserMessage.from_text("start"))

	result = await agent.run(thread)

	tool_msg = next(m for m in result if isinstance(m, ToolMessage))
	assert tool_msg.is_error is True
	assert "invalid json" in tool_msg.tool_output


@pytest.mark.asyncio
async def test_agent_sync_json_not_object_returns_error() -> None:
	adapter = _QueuedChatAdapter(
		sync_responses=[
			AssistantMessage(
				tool_calls=[ToolCall(id="tc1", name="echo", arguments="[1, 2]")]
			),
			AssistantMessage.from_text("done"),
		]
	)
	chat_model = _make_chat_model(adapter)
	agent = Agent(
		chat_model=chat_model,
		tools=[_EchoTool(name="echo", description="echo")],
	)
	thread = Thread()
	thread.add(UserMessage.from_text("start"))

	result = await agent.run(thread)

	tool_msg = next(m for m in result if isinstance(m, ToolMessage))
	assert tool_msg.is_error is True
	assert "expected a json object" in tool_msg.tool_output


@pytest.mark.asyncio
async def test_agent_sync_unsupported_args_type_returns_error() -> None:
	adapter = _QueuedChatAdapter(
		sync_responses=[
			AssistantMessage(
				tool_calls=[ToolCall(id="tc1", name="echo", arguments=123)]
			),
			AssistantMessage.from_text("done"),
		]
	)
	chat_model = _make_chat_model(adapter)
	agent = Agent(
		chat_model=chat_model,
		tools=[_EchoTool(name="echo", description="echo")],
	)
	thread = Thread()
	thread.add(UserMessage.from_text("start"))

	result = await agent.run(thread)

	tool_msg = next(m for m in result if isinstance(m, ToolMessage))
	assert tool_msg.is_error is True
	assert "expected json object" in tool_msg.tool_output


@pytest.mark.asyncio
async def test_agent_sync_unknown_tool_returns_error() -> None:
	adapter = _QueuedChatAdapter(
		sync_responses=[
			AssistantMessage(
				tool_calls=[ToolCall(id="tc1", name="missing", arguments={})]
			),
			AssistantMessage.from_text("done"),
		]
	)
	chat_model = _make_chat_model(adapter)
	agent = Agent(chat_model=chat_model, tools=[])
	thread = Thread()
	thread.add(UserMessage.from_text("start"))

	result = await agent.run(thread)

	tool_msg = next(m for m in result if isinstance(m, ToolMessage))
	assert tool_msg.is_error is True
	assert "unknown tool" in tool_msg.tool_output


@pytest.mark.asyncio
async def test_agent_sync_tool_exception_returns_error() -> None:
	adapter = _QueuedChatAdapter(
		sync_responses=[
			AssistantMessage(
				tool_calls=[ToolCall(id="tc1", name="explode", arguments={})]
			),
			AssistantMessage.from_text("done"),
		]
	)
	chat_model = _make_chat_model(adapter)
	agent = Agent(
		chat_model=chat_model,
		tools=[_ExplodingTool(name="explode", description="explode")],
	)
	thread = Thread()
	thread.add(UserMessage.from_text("start"))

	result = await agent.run(thread)

	tool_msg = next(m for m in result if isinstance(m, ToolMessage))
	assert tool_msg.is_error is True
	assert "error executing tool" in tool_msg.tool_output


@pytest.mark.asyncio
async def test_agent_sync_applies_filters_and_hooks() -> None:
	seen: list[str] = []

	class _TestFilter(Filter[None]):
		name: str = "test_filter"
		description: str = "test filter"

		async def process(self, thread: Thread, app_context: None) -> Thread:
			seen.append("filter")
			thread.add(SystemMessage.from_text("injected"))
			return thread

	class _TestHook(Hook[None]):
		name: str = "test_hook"
		description: str = "test hook"

		async def execute(self, thread: Thread, app_context: None) -> None:
			seen.append("hook")

	adapter = _QueuedChatAdapter(sync_responses=[AssistantMessage.from_text("ok")])
	chat_model = _make_chat_model(adapter)
	agent = Agent(chat_model=chat_model, filters=[_TestFilter()], hooks=[_TestHook()])
	thread = Thread()
	thread.add(UserMessage.from_text("hi"))

	result = await agent.run(thread)

	assert len(result) == 1
	assert isinstance(result[0], AssistantMessage)
	assert result[0].text == "ok"
	assert seen == ["filter", "hook"]
	call_messages = adapter.calls[-1]["messages"]
	assert isinstance(call_messages, list)
	assert any(
		isinstance(m, SystemMessage) and m.text == "injected" for m in call_messages
	)


@pytest.mark.asyncio
async def test_agent_sync_max_iterations_final_call_disables_tools() -> None:
	adapter = _QueuedChatAdapter(
		sync_responses=[
			AssistantMessage(
				tool_calls=[ToolCall(id="tc1", name="missing", arguments={})]
			),
			AssistantMessage.from_text("final"),
		]
	)
	chat_model = _make_chat_model(adapter)
	agent = Agent(chat_model=chat_model, tools=[], max_iterations=1)
	thread = Thread()
	thread.add(UserMessage.from_text("loop"))

	result = await agent.run(thread)

	last = result[-1]
	assert isinstance(last, AssistantMessage)
	assert last.text == "final"
	assert len(adapter.calls) == 2
	params = adapter.calls[-1]["params"]
	assert isinstance(params, ChatGenerationParams)
	assert params.tool_choice == "none"


@pytest.mark.asyncio
async def test_agent_streaming_yields_chat_deltas_tool_deltas_and_done() -> None:
	adapter = _QueuedChatAdapter(
		stream_responses=[
			[
				AssistantMessage(
					tool_calls=[
						ToolCall(
							id="tc1",
							name="echo",
							arguments={"text": "hi"},
						)
					]
				)
			],
			[AssistantMessage.from_text("done")],
		]
	)
	chat_model = _make_chat_model(adapter)
	agent = Agent(
		chat_model=chat_model,
		tools=[_EchoTool(name="echo", description="echo")],
	)
	thread = Thread()
	thread.add(UserMessage.from_text("start"))

	stream = await agent.run(thread, stream=True)
	deltas = [d async for d in stream]

	assert any(d.chat is not None for d in deltas)
	assert any(d.tool is not None for d in deltas)
	assert deltas[-1].done is True
	assert [m.role for m in thread.messages] == [
		"user",
		"assistant",
		"tool",
		"assistant",
	]


@pytest.mark.asyncio
async def test_agent_streaming_final_fallback_text_when_empty() -> None:
	adapter = _QueuedChatAdapter(stream_responses=[[]])
	chat_model = _make_chat_model(adapter)
	agent = Agent(chat_model=chat_model, max_iterations=0)
	thread = Thread()
	thread.add(UserMessage.from_text("hi"))

	stream = await agent.run(thread, stream=True)
	_ = [d async for d in stream]

	last = thread.messages[-1]
	assert isinstance(last, AssistantMessage)
	assert "unable to complete" in last.text


@pytest.mark.asyncio
async def test_agent_streaming_final_call_no_fallback_when_text() -> None:
	adapter = _QueuedChatAdapter(
		stream_responses=[[AssistantMessage.from_text("final")]]
	)
	chat_model = _make_chat_model(adapter)
	agent = Agent(chat_model=chat_model, max_iterations=0)
	thread = Thread()
	thread.add(UserMessage.from_text("hi"))

	stream = await agent.run(thread, stream=True)
	_ = [d async for d in stream]

	last = thread.messages[-1]
	assert isinstance(last, AssistantMessage)
	assert last.text == "final"
	assert "unable to complete" not in last.text


@pytest.mark.asyncio
async def test_agent_streaming_applies_filters_and_hooks() -> None:
	seen: list[str] = []

	class _TestFilter(Filter[None]):
		name: str = "test_filter"
		description: str = "test filter"

		async def process(self, thread: Thread, app_context: None) -> Thread:
			seen.append("filter")
			thread.add(SystemMessage.from_text("injected"))
			return thread

	class _TestHook(Hook[None]):
		name: str = "test_hook"
		description: str = "test hook"

		async def execute(self, thread: Thread, app_context: None) -> None:
			seen.append("hook")

	adapter = _QueuedChatAdapter(stream_responses=[[AssistantMessage.from_text("ok")]])
	chat_model = _make_chat_model(adapter)
	agent = Agent(chat_model=chat_model, filters=[_TestFilter()], hooks=[_TestHook()])
	thread = Thread()
	thread.add(UserMessage.from_text("hi"))

	stream = await agent.run(thread, stream=True)
	deltas = [d async for d in stream]

	assert deltas[-1].done is True
	assert seen == ["filter", "hook"]
	call_messages = adapter.calls[-1]["messages"]
	assert isinstance(call_messages, list)
	assert any(
		isinstance(m, SystemMessage) and m.text == "injected" for m in call_messages
	)


@pytest.mark.asyncio
async def test_agent_stream_stops_when_no_tool_calls() -> None:
	adapter = _QueuedChatAdapter(
		stream_responses=[[AssistantMessage.from_text("hello")]]
	)
	chat_model = _make_chat_model(adapter)
	agent = Agent(chat_model=chat_model, max_iterations=3)
	thread = Thread()
	thread.add(UserMessage.from_text("yo"))

	stream = await agent.run(thread, stream=True)
	deltas = [d async for d in stream]

	assert any(d.chat is not None for d in deltas)
	assert deltas[-1].done is True
	assert [m.role for m in thread.messages] == ["user", "assistant"]
	assert isinstance(thread.messages[-1], AssistantMessage)
	assert thread.messages[-1].text == "hello"


@pytest.mark.asyncio
async def test_agent_tool_call_with_no_metadata_sets_empty_context_metadata() -> None:
	adapter = _QueuedChatAdapter(
		sync_responses=[
			AssistantMessage(
				tool_calls=[
					ToolCall(
						id="tc1",
						name="echo",
						arguments={"text": "hey"},
						metadata=None,
					)
				]
			),
			AssistantMessage.from_text("done"),
		]
	)
	chat_model = _make_chat_model(adapter)
	agent = Agent(
		chat_model=chat_model,
		tools=[_EchoTool(name="echo", description="echo")],
	)
	thread = Thread()
	thread.add(UserMessage.from_text("yo"))

	result = await agent.run(thread)
	tool_msg = next(m for m in result if isinstance(m, ToolMessage))
	assert tool_msg.metadata == {}
