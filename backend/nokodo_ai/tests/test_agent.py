"""tests for SDK Agent class."""

from collections.abc import AsyncIterator, Awaitable

import pytest
from pydantic import PrivateAttr

from nokodo_ai import (
	Agent,
	AgentContext,
	AgentIterationSnapshot,
	AgentIterationState,
	AssistantMessage,
	ChatModel,
	SystemMessage,
	Thread,
	Tool,
	ToolCall,
	ToolCallContext,
	ToolMessage,
	UserMessage,
)
from nokodo_ai.adapters.base.chat import BaseChatAdapter, ChatGenerationParams
from nokodo_ai.agents import _should_continue_agent_run
from nokodo_ai.filters import Filter
from nokodo_ai.hooks import Hook
from nokodo_ai.messages import Message
from nokodo_ai.tool import ToolDefinition
from nokodo_ai.types.json import JSONObject


class _QueuedChatAdapter(BaseChatAdapter):
	_sync_responses: list[AssistantMessage] = PrivateAttr()
	_stream_responses: list[list[AssistantMessage]] = PrivateAttr()
	_calls: list[dict[str, object]] = PrivateAttr(default_factory=list)

	def __init__(
		self,
		sync_responses: list[AssistantMessage] | None = None,
		stream_responses: list[list[AssistantMessage]] | None = None,
	) -> None:
		super().__init__()
		self._sync_responses = list(sync_responses or [])
		self._stream_responses = list(stream_responses or [])

	@property
	def calls(self) -> list[dict[str, object]]:
		return self._calls

	def generate(  # type: ignore[override]
		self,
		messages: list[Message],
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
		api=None,
		model_name="stub",
		adapter=adapter,
	)


class _EchoTool(Tool[None]):
	async def call(
		self,
		__state__: AgentIterationSnapshot[None],
		__agent_context__: AgentContext,
		__tool_call_context__: ToolCallContext,
		__app_context__: None,
		**kwargs: object,
	) -> ToolMessage:
		_ = (__state__, __agent_context__, __app_context__)
		text = kwargs.get("text")
		assert isinstance(text, str)
		return self.success(
			f"{text}:{__tool_call_context__.tool_call_id}",
			__tool_call_context__,
		)


class _TimingCaptureTool(Tool[None]):
	"""captures tool_call_start_time from the tool context for assertions."""

	captured_start_times: list[float] = []

	async def call(
		self,
		__state__: AgentIterationSnapshot[None],
		__agent_context__: AgentContext,
		__tool_call_context__: ToolCallContext,
		__app_context__: None,
		**kwargs: object,
	) -> ToolMessage:
		_ = (__state__, __agent_context__, __app_context__, kwargs)
		assert __tool_call_context__.tool_call_start_time is not None
		self.captured_start_times.append(__tool_call_context__.tool_call_start_time)
		return self.success("ok", __tool_call_context__)


class _ExplodingTool(Tool[None]):
	async def call(
		self,
		__state__: AgentIterationSnapshot[None],
		__agent_context__: AgentContext,
		__tool_call_context__: ToolCallContext,
		__app_context__: None,
		**kwargs: object,
	) -> ToolMessage:
		_ = (
			__state__,
			__agent_context__,
			__tool_call_context__,
			__app_context__,
			kwargs,
		)
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


def _state_from(thread: Thread) -> AgentIterationState[None]:
	return AgentIterationState(thread=thread, tools=[])


def test_iteration_snapshot_copies_thread_and_shares_tools() -> None:
	thread = Thread()
	thread.add(UserMessage.from_text("hello"))
	tool: Tool[None] = _EchoTool(name="echo", description="echo")
	state = AgentIterationState[None](thread=thread, tools=[tool])

	snapshot = state.snapshot()
	snapshot_tool = snapshot.tools[0]
	snapshot.thread.add(UserMessage.from_text("snapshot only"))
	snapshot.tools.clear()

	assert isinstance(snapshot.tools, list)
	assert snapshot.thread is not state.thread
	assert snapshot.thread.messages[0] is not state.thread.messages[0]
	assert snapshot.tools is not state.tools
	assert snapshot_tool is state.tools[0]
	assert len(state.thread.messages) == 1
	assert state.tools == [tool]


@pytest.mark.asyncio
async def test_streaming_reports_no_finish_reason_when_the_provider_gave_none() -> None:
	"""the SDK reports what the provider said, and invents nothing.

	this adapter never sets one, so both the terminal delta and the persisted
	message must say None rather than a plausible-looking "completed".
	"""
	adapter = _QueuedChatAdapter(
		stream_responses=[[AssistantMessage.from_text("done")]]
	)
	agent = Agent(chat_model=_make_chat_model(adapter))
	thread = Thread(messages=[UserMessage.from_text("hello")])

	stream = await agent.run(thread, stream=True)
	deltas = [delta async for delta in stream]
	terminal = [delta for delta in deltas if delta.chat is not None and delta.chat.done]

	assert len(terminal) == 1
	assert terminal[0].chat is not None
	assert terminal[0].chat.message.finish_reason is None
	assert isinstance(thread.messages[-1], AssistantMessage)
	assert thread.messages[-1].finish_reason is None


@pytest.mark.asyncio
async def test_streaming_carries_a_reported_finish_reason_onto_the_terminal_delta() -> (
	None
):
	"""a reason the provider DID report survives to both consumers.

	the accumulated reason is copied onto the terminal delta, which is what the
	client reads and what the persistence layer writes down - dropping either
	assignment turns every persisted finish_reason into NULL silently.
	"""
	adapter = _QueuedChatAdapter(
		stream_responses=[
			[
				AssistantMessage.from_text("trunc"),
				AssistantMessage(finish_reason="length"),
			]
		]
	)
	agent = Agent(chat_model=_make_chat_model(adapter))
	thread = Thread(messages=[UserMessage.from_text("hello")])

	stream = await agent.run(thread, stream=True)
	deltas = [delta async for delta in stream]
	terminal = [delta for delta in deltas if delta.chat is not None and delta.chat.done]

	assert len(terminal) == 1
	assert terminal[0].chat is not None
	assert terminal[0].chat.message.finish_reason == "length"
	assert isinstance(thread.messages[-1], AssistantMessage)
	assert thread.messages[-1].finish_reason == "length"


@pytest.mark.asyncio
async def test_max_iterations_final_call_reports_its_finish_reason() -> None:
	"""the tool-less final call carries its reason the same way the loop does."""
	adapter = _QueuedChatAdapter(
		stream_responses=[
			[
				AssistantMessage.from_text("final"),
				AssistantMessage(finish_reason="length"),
			]
		]
	)
	agent = Agent(chat_model=_make_chat_model(adapter), max_iterations=0)
	thread = Thread(messages=[UserMessage.from_text("hello")])

	stream = await agent.run(thread, stream=True)
	deltas = [delta async for delta in stream]
	terminal = [delta for delta in deltas if delta.chat is not None and delta.chat.done]

	assert len(terminal) == 1
	assert terminal[0].chat is not None
	assert terminal[0].chat.message.finish_reason == "length"
	assert isinstance(thread.messages[-1], AssistantMessage)
	assert thread.messages[-1].finish_reason == "length"


@pytest.mark.asyncio
async def test_observer_hook_failure_does_not_fail_agent_run() -> None:
	class _FailingHook(Hook[None]):
		name: str = "failing"

		async def execute(
			self,
			state: AgentIterationSnapshot[None],
			agent_context: AgentContext,
			app_context: None,
		) -> None:
			_ = (state, agent_context, app_context)
			raise RuntimeError("observer failed")

	adapter = _QueuedChatAdapter(
		stream_responses=[[AssistantMessage.from_text("done")]]
	)
	agent = Agent(chat_model=_make_chat_model(adapter), hooks=[_FailingHook()])
	thread = Thread(messages=[UserMessage.from_text("hello")])

	stream = await agent.run(thread, stream=True)
	deltas = [delta async for delta in stream]

	assert deltas[-1].done
	assert isinstance(thread.messages[-1], AssistantMessage)
	assert thread.messages[-1].text == "done"


@pytest.mark.asyncio
async def test_a_failing_filter_surfaces_its_own_exception() -> None:
	"""nothing the SDK does around a filter may replace what it raised.

	the loop used to run caller cleanup in a `finally` around each callback,
	which could raise on the way out and mask the real failure.
	"""

	class _FailingFilter(Filter[None]):
		name: str = "failing"

		async def process(
			self,
			state: AgentIterationState[None],
			agent_context: AgentContext,
			app_context: None,
		) -> AgentIterationState[None]:
			_ = (state, agent_context, app_context)
			raise RuntimeError("filter exploded")

	adapter = _QueuedChatAdapter(
		stream_responses=[[AssistantMessage.from_text("done")]]
	)
	agent = Agent(chat_model=_make_chat_model(adapter), filters=[_FailingFilter()])
	thread = Thread(messages=[UserMessage.from_text("hello")])

	stream = await agent.run(thread, stream=True)
	with pytest.raises(RuntimeError, match="filter exploded"):
		_ = [delta async for delta in stream]


@pytest.mark.asyncio
async def test_a_failing_tool_reports_the_failure_as_its_result() -> None:
	"""a tool that raises ends that tool call, not the run.

	the message it produces is what the model reads next, so the failure has to
	arrive as a tool result rather than as an exception through the loop.
	"""

	class _FailingTool(Tool[None]):
		name: str = "boom"
		description: str = "always raises"
		parameters: JSONObject = {}

		async def call(
			self,
			__state__: AgentIterationSnapshot[None],
			__agent_context__: AgentContext,
			__tool_call_context__: ToolCallContext,
			__app_context__: None,
			**kwargs: object,
		) -> ToolMessage:
			_ = (__state__, __agent_context__, __tool_call_context__, kwargs)
			raise RuntimeError("tool exploded")

	adapter = _QueuedChatAdapter(
		stream_responses=[
			[
				AssistantMessage(
					tool_calls=[ToolCall(id="tc1", name="boom", arguments="{}")]
				)
			],
			[AssistantMessage.from_text("recovered")],
		]
	)
	agent = Agent(
		chat_model=_make_chat_model(adapter),
		tools=[_FailingTool()],
		max_iterations=2,
	)
	thread = Thread(messages=[UserMessage.from_text("hello")])

	stream = await agent.run(thread, stream=True)
	deltas = [delta async for delta in stream]

	tool_messages = [d.tool for d in deltas if d.tool is not None]
	assert len(tool_messages) == 1
	assert tool_messages[0].is_error is True


def test_should_continue_agent_run_from_thread_state() -> None:
	empty = Thread()
	assert _should_continue_agent_run(_state_from(empty)) is True

	complete = Thread()
	complete.add(SystemMessage.from_text("system"))
	complete.add(AssistantMessage.from_text("done"))
	assert _should_continue_agent_run(_state_from(complete)) is False

	awaiting_user_response = Thread()
	awaiting_user_response.add(AssistantMessage.from_text("done"))
	awaiting_user_response.add(UserMessage.from_text("next"))
	assert _should_continue_agent_run(_state_from(awaiting_user_response)) is True

	awaiting_tool_response = Thread()
	awaiting_tool_response.add(ToolMessage(tool_call_id="tc1", tool_output="ok"))
	assert _should_continue_agent_run(_state_from(awaiting_tool_response)) is True

	tool_request = Thread()
	tool_request.add(
		AssistantMessage(tool_calls=[ToolCall(id="tc1", name="echo", arguments={})])
	)
	assert _should_continue_agent_run(_state_from(tool_request)) is True


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
	assert "an internal error occurred" in tool_msg.tool_output


@pytest.mark.asyncio
async def test_agent_sync_applies_filters_and_hooks() -> None:
	seen: list[str] = []

	class _TestFilter(Filter[None]):
		name: str = "test_filter"
		description: str = "test filter"

		async def process(
			self,
			state: AgentIterationState[None],
			agent_context: AgentContext,
			app_context: None,
		) -> AgentIterationState[None]:
			_ = agent_context
			seen.append(f"filter:{state.iteration}")
			if state.iteration == 0:
				state.thread.add(SystemMessage.from_text("injected"))
			return state

	class _TestHook(Hook[None]):
		name: str = "test_hook"
		description: str = "test hook"

		async def execute(
			self,
			state: AgentIterationSnapshot[None],
			agent_context: AgentContext,
			app_context: None,
		) -> None:
			_ = (agent_context, app_context)
			phase = "final" if state.final else "hook"
			seen.append(f"{phase}:{state.iteration}")

	adapter = _QueuedChatAdapter(sync_responses=[AssistantMessage.from_text("ok")])
	chat_model = _make_chat_model(adapter)
	filters: list[Filter[None]] = [_TestFilter()]
	hooks: list[Hook[None]] = [_TestHook()]
	agent = Agent(chat_model=chat_model, filters=filters, hooks=hooks)
	thread = Thread()
	thread.add(UserMessage.from_text("hi"))

	result = await agent.run(thread)

	assert len(result) == 1
	assert isinstance(result[0], AssistantMessage)
	assert result[0].text == "ok"
	assert seen == ["filter:0", "hook:0", "filter:1", "final:1"]
	call_messages = adapter.calls[-1]["messages"]
	assert isinstance(call_messages, list)
	assert any(
		isinstance(m, SystemMessage) and m.text == "injected" for m in call_messages
	)


@pytest.mark.asyncio
async def test_agent_sync_filter_can_inject_after_terminal_response() -> None:
	class _LateUserFilter(Filter[None]):
		name: str = "late_user"
		description: str = "late user"

		calls: int = 0

		async def process(
			self,
			state: AgentIterationState[None],
			agent_context: AgentContext,
			app_context: None,
		) -> AgentIterationState[None]:
			_ = (agent_context, app_context)
			self.calls += 1
			if self.calls == 2:
				state.thread.add(UserMessage.from_text("late"))
			return state

	adapter = _QueuedChatAdapter(
		sync_responses=[
			AssistantMessage.from_text("first"),
			AssistantMessage.from_text("second"),
		]
	)
	chat_model = _make_chat_model(adapter)
	filters: list[Filter[None]] = [_LateUserFilter()]
	agent = Agent(chat_model=chat_model, filters=filters)
	thread = Thread()
	thread.add(UserMessage.from_text("start"))

	result = await agent.run(thread)

	assert [m.text for m in result if isinstance(m, AssistantMessage)] == [
		"first",
		"second",
	]
	assert len(adapter.calls) == 2
	assert [m.role for m in thread.messages] == [
		"user",
		"assistant",
		"user",
		"assistant",
	]


@pytest.mark.asyncio
async def test_agent_sync_filter_can_change_iteration_tools_and_choice() -> None:
	class _DisableToolsFilter(Filter[None]):
		name: str = "disable_tools"
		description: str = "disable tools"

		async def process(
			self,
			state: AgentIterationState[None],
			agent_context: AgentContext,
			app_context: None,
		) -> AgentIterationState[None]:
			_ = (agent_context, app_context)
			state.tools = []
			state.tool_choice = "required"
			return state

	adapter = _QueuedChatAdapter(sync_responses=[AssistantMessage.from_text("done")])
	chat_model = _make_chat_model(adapter)
	tools: list[Tool[None]] = [_EchoTool(name="echo", description="echo")]
	filters: list[Filter[None]] = [_DisableToolsFilter()]
	agent = Agent(
		chat_model=chat_model,
		tools=tools,
		filters=filters,
	)
	thread = Thread()
	thread.add(UserMessage.from_text("start"))

	await agent.run(thread)

	call = adapter.calls[-1]
	assert call["tools"] == []
	params = call["params"]
	assert isinstance(params, ChatGenerationParams)
	assert params.tool_choice is None


@pytest.mark.asyncio
async def test_agent_sync_forced_tool_choice_only_applies_to_first_iteration() -> None:
	"""a run-level forced tool_choice forces only the first model call."""
	adapter = _QueuedChatAdapter(
		sync_responses=[
			AssistantMessage(
				tool_calls=[ToolCall(id="tc1", name="echo", arguments={"text": "hi"})]
			),
			AssistantMessage.from_text("final"),
		]
	)
	chat_model = _make_chat_model(adapter)
	tools: list[Tool[None]] = [_EchoTool(name="echo", description="echo")]
	agent = Agent(chat_model=chat_model, tools=tools)
	thread = Thread()
	thread.add(UserMessage.from_text("start"))

	await agent.run(thread, tool_choice="echo")

	assert len(adapter.calls) == 2
	first_params = adapter.calls[0]["params"]
	second_params = adapter.calls[1]["params"]
	assert isinstance(first_params, ChatGenerationParams)
	assert isinstance(second_params, ChatGenerationParams)
	assert first_params.tool_choice == "echo"
	assert second_params.tool_choice == "auto"


@pytest.mark.asyncio
async def test_agent_stream_forced_tool_choice_only_applies_to_first_iteration() -> (
	None
):
	"""streaming: a run-level forced tool_choice forces only the first call."""
	adapter = _QueuedChatAdapter(
		stream_responses=[
			[
				AssistantMessage(
					tool_calls=[
						ToolCall(id="tc1", name="echo", arguments={"text": "hi"})
					]
				)
			],
			[AssistantMessage.from_text("final")],
		]
	)
	chat_model = _make_chat_model(adapter)
	tools: list[Tool[None]] = [_EchoTool(name="echo", description="echo")]
	agent = Agent(chat_model=chat_model, tools=tools)
	thread = Thread()
	thread.add(UserMessage.from_text("start"))

	stream = await agent.run(thread, stream=True, tool_choice="echo")
	_ = [delta async for delta in stream]

	assert len(adapter.calls) == 2
	first_params = adapter.calls[0]["params"]
	second_params = adapter.calls[1]["params"]
	assert isinstance(first_params, ChatGenerationParams)
	assert isinstance(second_params, ChatGenerationParams)
	assert first_params.tool_choice == "echo"
	assert second_params.tool_choice == "auto"


@pytest.mark.asyncio
async def test_agent_sync_filter_can_reforce_tool_choice_each_iteration() -> None:
	"""a filter re-setting tool_choice every iteration keeps forcing it."""

	class _ForceEchoFilter(Filter[None]):
		name: str = "force_echo"
		description: str = "force echo"

		async def process(
			self,
			state: AgentIterationState[None],
			agent_context: AgentContext,
			app_context: None,
		) -> AgentIterationState[None]:
			_ = (agent_context, app_context)
			state.tool_choice = "echo"
			return state

	adapter = _QueuedChatAdapter(
		sync_responses=[
			AssistantMessage(
				tool_calls=[ToolCall(id="tc1", name="echo", arguments={"text": "a"})]
			),
			AssistantMessage(
				tool_calls=[ToolCall(id="tc2", name="echo", arguments={"text": "b"})]
			),
			AssistantMessage.from_text("final"),
		]
	)
	chat_model = _make_chat_model(adapter)
	tools: list[Tool[None]] = [_EchoTool(name="echo", description="echo")]
	filters: list[Filter[None]] = [_ForceEchoFilter()]
	agent = Agent(
		chat_model=chat_model,
		tools=tools,
		filters=filters,
		max_iterations=2,
	)
	thread = Thread()
	thread.add(UserMessage.from_text("start"))

	await agent.run(thread)

	# two forced iterations, then the tools-disabled final call
	choices: list[object] = []
	for call in adapter.calls:
		params = call["params"]
		assert isinstance(params, ChatGenerationParams)
		choices.append(params.tool_choice)
	assert choices == ["echo", "echo", "none"]


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
async def test_agent_sync_keeps_an_empty_final_response() -> None:
	"""a turn the model answered with nothing is still a message it sent.

	the final call is made with ``tool_choice="none"``, so an empty result is
	the model's answer rather than an artifact of the iteration limit.
	"""
	adapter = _QueuedChatAdapter(sync_responses=[AssistantMessage()])
	chat_model = _make_chat_model(adapter)
	agent = Agent(chat_model=chat_model, max_iterations=0)
	thread = Thread()
	thread.add(UserMessage.from_text("loop"))

	result = await agent.run(thread)

	assert len(result) == 1
	assert isinstance(result[0], AssistantMessage)
	assert result[0].content == []
	assert [message.role for message in thread.messages] == ["user", "assistant"]


@pytest.mark.asyncio
async def test_agent_sync_runs_hooks_after_each_assistant_response() -> None:
	"""sync hooks observe each assistant response appended by the loop."""
	seen: list[list[str]] = []

	class _TestHook(Hook[None]):
		name: str = "test_hook"
		description: str = "test hook"

		async def execute(
			self,
			state: AgentIterationSnapshot[None],
			agent_context: AgentContext,
			app_context: None,
		) -> None:
			_ = (agent_context, app_context)
			seen.append(
				[str(state.final), *[message.role for message in state.thread.messages]]
			)

	adapter = _QueuedChatAdapter(
		sync_responses=[
			AssistantMessage(
				tool_calls=[ToolCall(id="tc1", name="echo", arguments={"text": "hi"})]
			),
			AssistantMessage.from_text("done"),
		]
	)
	chat_model = _make_chat_model(adapter)
	tools: list[Tool[None]] = [_EchoTool(name="echo", description="echo")]
	hooks: list[Hook[None]] = [_TestHook()]
	agent = Agent(
		chat_model=chat_model,
		tools=tools,
		hooks=hooks,
	)
	thread = Thread()
	thread.add(UserMessage.from_text("start"))

	await agent.run(thread)

	assert seen == [
		["False", "user", "assistant"],
		["False", "user", "assistant", "tool", "assistant"],
		["True", "user", "assistant", "tool", "assistant"],
	]


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
async def test_agent_streaming_keeps_an_empty_final_response() -> None:
	"""an empty final answer is added to the thread, and still ENDS.

	the final call is made with ``tool_choice="none"``, so an empty result is
	a turn the model answered with nothing rather than an artifact of the
	iteration limit - and the terminal delta must arrive either way, or every
	consumer waits for a `done` that never comes.
	"""
	adapter = _QueuedChatAdapter(stream_responses=[[]])
	chat_model = _make_chat_model(adapter)
	agent = Agent(chat_model=chat_model, max_iterations=0)
	thread = Thread()
	thread.add(UserMessage.from_text("hi"))

	stream = await agent.run(thread, stream=True)
	deltas = [d async for d in stream]

	assert [message.role for message in thread.messages] == ["user", "assistant"]
	# the only chat delta is the terminal one: no content was produced.
	chat_deltas = [delta for delta in deltas if delta.chat is not None]
	assert len(chat_deltas) == 1
	assert chat_deltas[0].chat is not None
	assert chat_deltas[0].chat.done is True
	assert deltas[-1].done is True


@pytest.mark.asyncio
async def test_agent_streaming_final_call_preserves_model_text() -> None:
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


@pytest.mark.asyncio
async def test_agent_streaming_applies_filters_and_hooks() -> None:
	seen: list[str] = []

	class _TestFilter(Filter[None]):
		name: str = "test_filter"
		description: str = "test filter"

		async def process(
			self,
			state: AgentIterationState[None],
			agent_context: AgentContext,
			app_context: None,
		) -> AgentIterationState[None]:
			_ = agent_context
			seen.append(f"filter:{state.iteration}")
			if state.iteration == 0:
				state.thread.add(SystemMessage.from_text("injected"))
			return state

	class _TestHook(Hook[None]):
		name: str = "test_hook"
		description: str = "test hook"

		async def execute(
			self,
			state: AgentIterationSnapshot[None],
			agent_context: AgentContext,
			app_context: None,
		) -> None:
			_ = (agent_context, app_context)
			phase = "final" if state.final else "hook"
			seen.append(f"{phase}:{state.iteration}")

	adapter = _QueuedChatAdapter(stream_responses=[[AssistantMessage.from_text("ok")]])
	chat_model = _make_chat_model(adapter)
	filters: list[Filter[None]] = [_TestFilter()]
	hooks: list[Hook[None]] = [_TestHook()]
	agent = Agent(chat_model=chat_model, filters=filters, hooks=hooks)
	thread = Thread()
	thread.add(UserMessage.from_text("hi"))

	stream = await agent.run(thread, stream=True)
	deltas = [d async for d in stream]

	assert deltas[-1].done is True
	assert seen == ["filter:0", "hook:0", "filter:1", "final:1"]
	call_messages = adapter.calls[-1]["messages"]
	assert isinstance(call_messages, list)
	assert any(
		isinstance(m, SystemMessage) and m.text == "injected" for m in call_messages
	)


@pytest.mark.asyncio
async def test_agent_stream_filter_can_inject_after_terminal_response() -> None:
	class _LateUserFilter(Filter[None]):
		name: str = "late_user"
		description: str = "late user"

		calls: int = 0

		async def process(
			self,
			state: AgentIterationState[None],
			agent_context: AgentContext,
			app_context: None,
		) -> AgentIterationState[None]:
			_ = (agent_context, app_context)
			self.calls += 1
			if self.calls == 2:
				state.thread.add(UserMessage.from_text("late"))
			return state

	adapter = _QueuedChatAdapter(
		stream_responses=[
			[AssistantMessage.from_text("first")],
			[AssistantMessage.from_text("second")],
		]
	)
	chat_model = _make_chat_model(adapter)
	filters: list[Filter[None]] = [_LateUserFilter()]
	agent = Agent(chat_model=chat_model, filters=filters)
	thread = Thread()
	thread.add(UserMessage.from_text("start"))

	stream = await agent.run(thread, stream=True)
	deltas = [delta async for delta in stream]

	texts = [
		delta.chat.message.text
		for delta in deltas
		if delta.chat is not None and delta.chat.message.text
	]
	assert texts == ["first", "second"]
	assert deltas[-1].done is True
	assert len(adapter.calls) == 2
	assert [m.role for m in thread.messages] == [
		"user",
		"assistant",
		"user",
		"assistant",
	]


@pytest.mark.asyncio
async def test_agent_streaming_runs_hooks_after_each_assistant_response() -> None:
	"""streaming hooks observe each assistant response appended by the loop."""
	seen: list[list[str]] = []

	class _TestHook(Hook[None]):
		name: str = "test_hook"
		description: str = "test hook"

		async def execute(
			self,
			state: AgentIterationSnapshot[None],
			agent_context: AgentContext,
			app_context: None,
		) -> None:
			_ = (agent_context, app_context)
			seen.append(
				[str(state.final), *[message.role for message in state.thread.messages]]
			)

	adapter = _QueuedChatAdapter(
		stream_responses=[
			[
				AssistantMessage(
					tool_calls=[
						ToolCall(id="tc1", name="echo", arguments={"text": "hi"})
					]
				)
			],
			[AssistantMessage.from_text("done")],
		]
	)
	chat_model = _make_chat_model(adapter)
	tools: list[Tool[None]] = [_EchoTool(name="echo", description="echo")]
	hooks: list[Hook[None]] = [_TestHook()]
	agent = Agent(
		chat_model=chat_model,
		tools=tools,
		hooks=hooks,
	)
	thread = Thread()
	thread.add(UserMessage.from_text("start"))

	stream = await agent.run(thread, stream=True)
	_ = [delta async for delta in stream]

	assert seen == [
		["False", "user", "assistant"],
		["False", "user", "assistant", "tool", "assistant"],
		["True", "user", "assistant", "tool", "assistant"],
	]


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


@pytest.mark.asyncio
async def test_agent_tool_custom_metadata_preserves_provider_data() -> None:
	"""custom tool metadata must not prevent provider metadata propagation.

	regression test for the bug where deep_merge(overwrite=False) treated
	None base values for provider_data as existing, silently dropping
	the overlay.
	"""
	from nokodo_ai.messages import PROVIDER_DATA_KEY

	provider_meta: JSONObject = {
		PROVIDER_DATA_KEY: {
			"anthropic.messages": {"tool_call_id": "toolu_01ABC"},
		}
	}

	class _MetadataTool(Tool[None]):
		async def call(
			self,
			__state__: AgentIterationSnapshot[None],
			__agent_context__: AgentContext,
			__tool_call_context__: ToolCallContext,
			__app_context__: None,
			**kwargs: object,
		) -> ToolMessage:
			_ = (__state__, __agent_context__, __app_context__, kwargs)
			tool_call_id = __tool_call_context__.tool_call_id
			return ToolMessage(
				tool_call_id=tool_call_id,
				tool_output="note content here",
				metadata={"_application_data": {"resource_id": "n1"}},
			)

	adapter = _QueuedChatAdapter(
		sync_responses=[
			AssistantMessage(
				tool_calls=[
					ToolCall(
						id="tc1",
						name="metadata_tool",
						arguments={},
						metadata=provider_meta,
					),
				]
			),
			AssistantMessage.from_text("done"),
		]
	)
	chat_model = _make_chat_model(adapter)
	agent = Agent(
		chat_model=chat_model,
		tools=[
			_MetadataTool(name="metadata_tool", description="return metadata"),
		],
	)
	thread = Thread()
	thread.add(UserMessage.from_text("get my note"))

	result = await agent.run(thread)
	tool_msg = next(m for m in result if isinstance(m, ToolMessage))

	# provider_data must be propagated despite tool returning custom metadata
	assert tool_msg.metadata is not None
	pd = tool_msg.metadata.get(PROVIDER_DATA_KEY)
	assert pd is not None, "provider_data was not propagated to ToolMessage"
	assert pd == {"anthropic.messages": {"tool_call_id": "toolu_01ABC"}}

	# tool's own metadata must also be preserved
	assert tool_msg.metadata.get("_application_data") == {"resource_id": "n1"}


# tool_call_start_time monotonic propagation


@pytest.mark.asyncio
async def test_agent_sync_passes_monotonic_start_time_to_tool() -> None:
	"""tool_call_start_time in AgentContext must come
	from ToolCall.created_at_monotonic."""

	tc = ToolCall(id="tc1", name="capture", arguments={})
	expected_mono = tc.created_at_monotonic
	assert expected_mono > 0

	timing_tool = _TimingCaptureTool(name="capture", description="capture timing")

	adapter = _QueuedChatAdapter(
		sync_responses=[
			AssistantMessage(tool_calls=[tc]),
			AssistantMessage.from_text("done"),
		]
	)
	chat_model = _make_chat_model(adapter)
	agent = Agent(chat_model=chat_model, tools=[timing_tool])
	thread = Thread()
	thread.add(UserMessage.from_text("go"))

	await agent.run(thread)

	assert len(timing_tool.captured_start_times) == 1
	assert timing_tool.captured_start_times[0] == expected_mono


@pytest.mark.asyncio
async def test_agent_streaming_passes_monotonic_start_time_to_tool() -> None:
	"""streaming path must also propagate created_at_monotonic."""
	tc = ToolCall(id="tc1", name="capture", arguments={})
	expected_mono = tc.created_at_monotonic

	timing_tool = _TimingCaptureTool(name="capture", description="capture timing")

	adapter = _QueuedChatAdapter(
		stream_responses=[
			[AssistantMessage(tool_calls=[tc])],
			[AssistantMessage.from_text("done")],
		]
	)
	chat_model = _make_chat_model(adapter)
	agent = Agent(chat_model=chat_model, tools=[timing_tool])
	thread = Thread()
	thread.add(UserMessage.from_text("go"))

	stream = await agent.run(thread, stream=True)
	_ = [d async for d in stream]

	assert len(timing_tool.captured_start_times) == 1
	assert timing_tool.captured_start_times[0] == expected_mono
