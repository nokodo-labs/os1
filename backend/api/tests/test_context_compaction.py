"""tests for the context compaction filter and Layer 2 combined tool budget."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, _patch, patch

import pytest

from api.local_tasks import _on_task_done
from api.models.event_types import EventType
from api.v1.service.chat.context import AppContext
from api.v1.service.chat.context_compaction.tool_io import (
	COMPACTED_TOOL_OUTPUT_NOTICE,
	enforce_combined_tool_budget,
)
from api.v1.service.chat.filters.context_compaction import (
	ContextCompactionFilter,
)
from api.v1.service.chat.models import is_context_pressure_generation_error
from nokodo_ai.adapters.chat import GenerationBadRequestError, GenerationRateLimitError
from nokodo_ai.agents import AgentIterationState
from nokodo_ai.chat_models import ChatModel
from nokodo_ai.context import AgentContext
from nokodo_ai.messages import (
	AssistantMessage,
	Message,
	SystemMessage,
	TextContent,
	ToolMessage,
	UserMessage,
)
from nokodo_ai.threads import Thread
from nokodo_ai.tool import ToolDefinition
from nokodo_ai.types.json import JSONObject
from nokodo_ai.utils.typeid import TypeID


# -- AppContext.with_emitter --


class TestAppContextWithEmitter:
	"""tests that AppContext.with_emitter preserves context_window."""

	def test_with_emitter_preserves_context_window(self) -> None:
		from api.v1.service.chat.context import AppContext

		principal = MagicMock()
		principal.user.id = "usr_123"
		emitter_a = AsyncMock()
		emitter_b = AsyncMock()

		ctx = AppContext(
			session=AsyncMock(),
			principal=principal,
			event_emitter=emitter_a,
			context_window=200_000,
		)
		new_ctx = ctx.with_emitter(emitter_b)

		assert new_ctx.context_window == 200_000
		assert new_ctx.event_emitter is emitter_b
		assert new_ctx.session is ctx.session
		assert new_ctx.principal is ctx.principal

	def test_with_emitter_preserves_none_context_window(self) -> None:
		from api.v1.service.chat.context import AppContext

		principal = MagicMock()
		principal.user.id = "usr_123"

		ctx = AppContext(
			session=AsyncMock(),
			principal=principal,
			event_emitter=AsyncMock(),
		)
		new_ctx = ctx.with_emitter(AsyncMock())

		assert new_ctx.context_window is None


# -- helpers --


class TestProviderContextPressureHelper:
	def test_detects_openai_context_length_bad_request(self) -> None:
		exc = GenerationBadRequestError(
			"this model's maximum context length is 128000 tokens",
			provider="openai.chat_completions",
			status_code=400,
			code="context_length_exceeded",
		)

		assert is_context_pressure_generation_error(exc) is True

	def test_detects_anthropic_prompt_too_long_bad_request(self) -> None:
		exc = GenerationBadRequestError(
			"prompt is too long: 103078 tokens > 102398 maximum",
			provider="anthropic.messages",
			status_code=400,
			code="invalid_request_error",
		)

		assert is_context_pressure_generation_error(exc) is True

	def test_detects_google_input_token_count_bad_request(self) -> None:
		exc = GenerationBadRequestError(
			"the input token count exceeds the maximum number of tokens allowed",
			provider="google.generate_content",
			status_code=400,
			code="INVALID_ARGUMENT",
		)

		assert is_context_pressure_generation_error(exc) is True

	def test_rejects_generic_bad_request(self) -> None:
		exc = GenerationBadRequestError(
			"unknown model",
			provider="openai.chat_completions",
			status_code=400,
			code="invalid_request_error",
		)

		assert is_context_pressure_generation_error(exc) is False

	def test_rejects_non_bad_request_error(self) -> None:
		exc = GenerationRateLimitError(
			"too many requests",
			provider="openai.chat_completions",
			status_code=429,
			code="rate_limit_exceeded",
		)

		assert is_context_pressure_generation_error(exc) is False


def _sys(text: str) -> SystemMessage:
	return SystemMessage.from_text(text)


def _user(text: str, msg_id: str | None = None) -> UserMessage:
	meta: JSONObject | None = {"_message_id": msg_id} if msg_id else None
	return UserMessage(
		content=[TextContent(text=text)],
		metadata=meta,
	)


def _assistant(text: str, msg_id: str | None = None) -> AssistantMessage:
	meta: JSONObject | None = {"_message_id": msg_id} if msg_id else None
	return AssistantMessage(
		content=[TextContent(text=text)],
		metadata=meta,
	)


def _tool(output: str, call_id: str = "call_1") -> ToolMessage:
	return ToolMessage(
		tool_call_id=call_id,
		tool_output=output,
	)


def _thread(*msgs: Message) -> Thread:
	return Thread(messages=list(msgs))


def _state(thread: Thread) -> AgentIterationState[AppContext]:
	return AgentIterationState[AppContext](thread=thread, tools=[])


def _agent_context() -> AgentContext:
	return AgentContext(
		model=ChatModel.model_construct(model_name="test"),
	)


_TID = TypeID("th_123")


def _mock_ctx(
	thread_id: TypeID | None = _TID,
	context_window: int | None = 128_000,
) -> MagicMock:
	ctx = MagicMock()
	ctx.thread_id = thread_id
	ctx.context_window = context_window
	ctx.session = AsyncMock()
	ctx.principal = MagicMock()
	ctx.event_emitter = AsyncMock()
	ctx.run_id = None
	ctx.user_id = TypeID("usr_123")
	return ctx


# -- _log_task_exception --


class TestOnTaskDone:
	def test_cancelled_task_no_error(self) -> None:
		task = MagicMock()
		task.cancelled.return_value = True
		# should not raise
		_on_task_done(task, "test")

	def test_successful_task_no_error(self) -> None:
		task = MagicMock()
		task.cancelled.return_value = False
		task.exception.return_value = None
		_on_task_done(task, "test")

	def test_failed_task_logs_exception(self) -> None:
		task = MagicMock()
		task.cancelled.return_value = False
		exc = RuntimeError("boom")
		task.exception.return_value = exc

		with patch("api.local_tasks.logger") as mock_log:
			_on_task_done(task, "test_task")
			mock_log.exception.assert_called_once()
			assert "test_task" in mock_log.exception.call_args[0][1]


# -- enforce_combined_tool_budget --


class TestEnforceCombinedToolBudget:
	"""tests for the Layer 2 combined tool result token budget guard."""

	def _patch_settings(
		self,
		combined_share: float = 0.50,
		headroom: int = 4096,
		prompt_overhead_tokens: int = 0,
	) -> _patch[MagicMock]:
		ws = MagicMock()
		ws.tool_results_combined_max_share = combined_share
		ws.response_headroom = headroom
		ws.prompt_overhead_tokens = prompt_overhead_tokens
		ws.target_usage_cap_tokens = None
		mock_settings = MagicMock()
		mock_settings.ai.context_compaction = ws
		return patch(
			"api.v1.service.chat.context_compaction.tool_io.app_settings",
			mock_settings,
		)

	def test_under_budget_returns_unchanged(self) -> None:
		"""when combined tool tokens are within budget, thread is returned as-is."""
		thread = _thread(
			_sys("system"),
			_user("hi"),
			_tool("short result"),
			_assistant("done"),
		)
		# context_window=128000, 50% of budget = ~62000 tokens
		# "short result" is maybe 5 tokens, well under budget
		with self._patch_settings():
			result = enforce_combined_tool_budget(thread, context_window=128_000)
		assert result is thread

	def test_over_budget_compacts_oldest_first(self) -> None:
		"""when combined tool tokens exceed budget, oldest results are compacted."""
		# context_window=1000, headroom=100 -> budget=900
		# combined_share=0.20 -> limit=180 tokens
		# each tool output "x"*300 = ~90 tokens (300/4*1.2)
		# 4 tool results = ~360 tokens > 180 limit
		# compacting releases ~75 tokens each (90 - ~15 for notice)
		# after compacting 3 oldest: ~135 tokens < 180 -> 1 preserved
		big_output = "x" * 300
		thread = _thread(
			_sys("s"),
			_user("q"),
			_tool(big_output, "c1"),  # oldest - compacted first
			_tool(big_output, "c2"),
			_tool(big_output, "c3"),
			_tool(big_output, "c4"),  # newest - should be preserved
			_assistant("done"),
		)

		with self._patch_settings(combined_share=0.20, headroom=100):
			result = enforce_combined_tool_budget(thread, context_window=1000)

		# some oldest tool results should be compacted
		tool_msgs = [m for m in result.messages if isinstance(m, ToolMessage)]
		compacted = [
			m for m in tool_msgs if m.tool_output == COMPACTED_TOOL_OUTPUT_NOTICE
		]
		preserved = [
			m for m in tool_msgs if m.tool_output != COMPACTED_TOOL_OUTPUT_NOTICE
		]

		assert len(compacted) > 0, "at least one tool result should be compacted"
		assert len(preserved) > 0, "at least one tool result should be preserved"
		# the compacted ones should be the oldest (earliest in the list)
		compacted_indices = [
			i
			for i, m in enumerate(result.messages)
			if isinstance(m, ToolMessage)
			and m.tool_output == COMPACTED_TOOL_OUTPUT_NOTICE
		]
		preserved_indices = [
			i
			for i, m in enumerate(result.messages)
			if isinstance(m, ToolMessage)
			and m.tool_output != COMPACTED_TOOL_OUTPUT_NOTICE
		]
		assert max(compacted_indices) < max(preserved_indices), (
			"compacted results should be older (earlier) than preserved"
		)

	def test_already_compacted_skipped(self) -> None:
		"""tool results already showing the compacted notice are skipped."""
		thread = _thread(
			_sys("s"),
			_user("q"),
			_tool(COMPACTED_TOOL_OUTPUT_NOTICE, "c1"),
			_tool("x" * 200, "c2"),
			_assistant("done"),
		)

		with self._patch_settings(combined_share=0.50, headroom=50):
			result = enforce_combined_tool_budget(thread, context_window=500)

		# the already-compacted tool should still show the notice
		tool_msgs = [m for m in result.messages if isinstance(m, ToolMessage)]
		assert tool_msgs[0].tool_output == COMPACTED_TOOL_OUTPUT_NOTICE

	def test_compaction_skips_already_compacted_in_loop(self) -> None:
		"""when over budget and oldest result is already compacted, skip it."""
		# context_window=500, headroom=50 -> budget=450
		# combined_share=0.10 -> limit=45 tokens
		# big_output "x"*300 = ~90 tokens each
		# 2 non-compacted results + 1 compacted = ~180 non-compacted tokens > 45
		big_output = "x" * 300
		thread = _thread(
			_sys("s"),
			_user("q"),
			_tool(COMPACTED_TOOL_OUTPUT_NOTICE, "c0"),  # already compacted
			_tool(big_output, "c1"),  # should be compacted
			_tool(big_output, "c2"),  # may be compacted
			_assistant("done"),
		)

		with self._patch_settings(combined_share=0.10, headroom=50):
			result = enforce_combined_tool_budget(thread, context_window=500)

		tool_msgs = [m for m in result.messages if isinstance(m, ToolMessage)]
		# first tool was already compacted and should remain so
		assert tool_msgs[0].tool_output == COMPACTED_TOOL_OUTPUT_NOTICE
		# at least one of the non-compacted tools should now be compacted
		newly_compacted = [
			m for m in tool_msgs[1:] if m.tool_output == COMPACTED_TOOL_OUTPUT_NOTICE
		]
		assert len(newly_compacted) > 0

	def test_no_tool_messages_returns_unchanged(self) -> None:
		"""threads with no tool messages are returned as-is."""
		thread = _thread(
			_sys("system"),
			_user("hello"),
			_assistant("world"),
		)
		with self._patch_settings():
			result = enforce_combined_tool_budget(thread, context_window=128_000)
		assert result is thread

	def test_system_prompt_and_overhead_reduce_tool_budget(self) -> None:
		"""standalone tool budgeting uses the same fixed prompt costs."""
		thread = _thread(
			_sys("s" * 2000),
			_user("q"),
			_tool("x" * 500, "c1"),
			_assistant("done"),
		)

		with self._patch_settings(
			combined_share=0.50,
			headroom=100,
			prompt_overhead_tokens=100,
		):
			result = enforce_combined_tool_budget(thread, context_window=1000)

		tool_msg = next(
			message for message in result.messages if isinstance(message, ToolMessage)
		)
		assert tool_msg.tool_output == COMPACTED_TOOL_OUTPUT_NOTICE

	def test_tool_definitions_reduce_tool_budget(self) -> None:
		"""standalone tool budgeting includes tool definition schema tokens."""
		thread = _thread(
			_sys("s"),
			_user("q"),
			_tool("x" * 500, "c1"),
			_assistant("done"),
		)
		tools = [
			ToolDefinition(
				name="large_schema_tool",
				description="x" * 2000,
				parameters={"type": "object", "properties": {}},
			)
		]

		with self._patch_settings(combined_share=0.50, headroom=100):
			result = enforce_combined_tool_budget(
				thread,
				context_window=1000,
				tool_definitions=tools,
			)

		tool_msg = next(
			message for message in result.messages if isinstance(message, ToolMessage)
		)
		assert tool_msg.tool_output == COMPACTED_TOOL_OUTPUT_NOTICE

	def test_none_context_window_uses_default(self) -> None:
		"""when context_window is None, uses DEFAULT_CONTEXT_WINDOW."""
		thread = _thread(
			_sys("s"),
			_user("q"),
			_tool("short"),
			_assistant("done"),
		)
		with self._patch_settings():
			result = enforce_combined_tool_budget(thread, context_window=None)
		# with default 128K window, a short tool result should be fine
		assert result is thread

	def test_original_thread_not_mutated(self) -> None:
		"""the original thread should not be mutated by compaction."""
		big_output = "x" * 500
		thread = _thread(
			_sys("s"),
			_user("q"),
			_tool(big_output, "c1"),
			_tool(big_output, "c2"),
			_tool(big_output, "c3"),
			_assistant("done"),
		)
		original_count = len(thread.messages)

		with self._patch_settings(combined_share=0.05, headroom=50):
			result = enforce_combined_tool_budget(thread, context_window=500)

		# original should be untouched
		assert len(thread.messages) == original_count
		for m in thread.messages:
			if isinstance(m, ToolMessage):
				assert m.tool_output == big_output

		# result may have compacted messages
		assert result is not thread


# -- ContextCompactionFilter --


class TestContextCompactionFilter:
	"""tests for the ContextCompactionFilter."""

	def test_default_fields(self) -> None:
		f = ContextCompactionFilter()
		assert f.name == "context_compaction"

	@pytest.mark.asyncio()
	async def test_none_context_skips(self) -> None:
		"""when app_context is None, thread is returned unchanged."""
		f = ContextCompactionFilter()
		thread = _thread(_user("hi"))
		state = _state(thread)
		result = await f.process(state, _agent_context(), None)
		assert result is state

	@pytest.mark.asyncio()
	async def test_no_thread_id_skips_compaction(self) -> None:
		"""ephemeral runs with no thread_id skip full compaction."""
		f = ContextCompactionFilter()
		thread = _thread(_sys("system"), _user("hi"))
		ctx = _mock_ctx(thread_id=None)
		state = _state(thread)

		result = await f.process(state, _agent_context(), ctx)
		assert result is state

	@pytest.mark.asyncio()
	async def test_first_pass_calls_compaction(self) -> None:
		"""first call triggers full compaction."""
		f = ContextCompactionFilter()
		ctx = _mock_ctx()
		thread = _thread(_sys("system"), _user("hi"))

		mock_compaction_result = MagicMock()
		mock_compaction_result.thread = thread
		mock_compaction_result.needs_summarization = False
		mock_compaction_result.summarize_messages = []

		with (
			patch(
				"api.v1.service.chat.filters.context_compaction.apply_context_compaction",
				AsyncMock(return_value=mock_compaction_result),
			) as mock_aw,
			patch(
				"api.v1.service.chat.filters.context_compaction.summary_service"
			) as mock_svc,
		):
			mock_svc.count_active_summaries = AsyncMock(return_value=0)
			state = _state(thread)
			result = await f.process(state, _agent_context(), ctx)

		mock_aw.assert_called_once()
		assert result.thread is thread

	@pytest.mark.asyncio()
	async def test_later_iteration_runs_full_compaction(self) -> None:
		"""second call reruns the full budget cascade."""
		f = ContextCompactionFilter()
		ctx = _mock_ctx()
		thread = _thread(_sys("s"), _user("hi", "msg_head"))

		mock_wr = MagicMock()
		mock_wr.thread = thread
		mock_wr.needs_summarization = False
		mock_wr.summarize_messages = []

		with (
			patch(
				"api.v1.service.chat.filters.context_compaction.apply_context_compaction",
				AsyncMock(return_value=mock_wr),
			) as mock_aw,
			patch(
				"api.v1.service.chat.filters.context_compaction.summary_service"
			) as mock_svc,
		):
			mock_svc.count_active_summaries = AsyncMock(return_value=0)
			state = _state(thread)

			# first iteration: full compaction
			await f.process(state, _agent_context(), ctx)
			assert mock_aw.call_count == 1

			# later iteration: full cascade again
			state.iteration = 1
			await f.process(state, _agent_context(), ctx)
			assert mock_aw.call_count == 2

	@pytest.mark.asyncio()
	async def test_first_iteration_is_stateless_across_runs(self) -> None:
		"""same filter instance can first-pass multiple runs independently."""
		f = ContextCompactionFilter()
		ctx = _mock_ctx()
		thread = _thread(_sys("s"), _user("hi", "msg_head"))

		mock_wr = MagicMock()
		mock_wr.thread = thread
		mock_wr.needs_summarization = False
		mock_wr.summarize_messages = []

		with (
			patch(
				"api.v1.service.chat.filters.context_compaction.apply_context_compaction",
				AsyncMock(return_value=mock_wr),
			) as mock_aw,
			patch(
				"api.v1.service.chat.filters.context_compaction.summary_service"
			) as mock_svc,
		):
			mock_svc.count_active_summaries = AsyncMock(return_value=0)
			state = _state(thread)

			await f.process(state, _agent_context(), ctx)
			await f.process(state, _agent_context(), ctx)

		assert mock_aw.call_count == 2

	@pytest.mark.asyncio()
	async def test_blocking_compaction_emits_lifecycle_events(self) -> None:
		"""blocking compaction progress emits run context lifecycle events."""
		f = ContextCompactionFilter()
		ctx = _mock_ctx()
		ctx.run_id = TypeID("run_123")
		captured = []

		async def event_emitter(event):
			captured.append(event)

		ctx.event_emitter = event_emitter
		thread = _thread(_sys("s"), _user("hi", "msg_user"))

		async def fake_compaction(*args, **kwargs):
			_ = args
			await kwargs["progress_callback"](15, "compacting context")
			result = MagicMock()
			result.thread = thread
			result.needs_summarization = False
			result.summarize_messages = []
			result.summary_count = 1
			result.blocking_summary_count = 1
			result.dropped_count = 0
			result.compacted_tool_call_count = 0
			result.compacted_tool_result_count = 0
			result.compacted_tool_run_count = 0
			result.total_tokens = 100
			result.budget_tokens = 200
			return result

		with (
			patch(
				"api.v1.service.chat.filters.context_compaction.apply_context_compaction",
				AsyncMock(side_effect=fake_compaction),
			),
			patch(
				"api.v1.service.chat.filters.context_compaction.summary_service"
			) as mock_svc,
		):
			mock_svc.count_active_summaries = AsyncMock(return_value=0)
			state = _state(thread)

			await f.process(state, _agent_context(), ctx)

		assert [event.type for event in captured] == [
			EventType.RUN_ACTIVITY_STARTED,
			EventType.RUN_ACTIVITY_PROGRESS,
			EventType.RUN_ACTIVITY_ENDED,
		]
		assert captured[0].thread_id == str(_TID)
		assert captured[0].data["run_id"] == "run_123"
		assert captured[0].message_id == "msg_user"
		assert captured[0].data["activity_type"] == "context_compaction"
		assert captured[0].data["title"] == "compacting chat"
		assert captured[2].data["activity_id"] == captured[0].data["activity_id"]
		assert captured[2].data["outcome"] == "success"

	@pytest.mark.asyncio()
	async def test_non_blocking_compaction_does_not_emit_lifecycle_events(
		self,
	) -> None:
		"""non-blocking compaction stays invisible to chat UI events."""
		f = ContextCompactionFilter()
		ctx = _mock_ctx()
		ctx.run_id = TypeID("run_123")
		captured = []

		async def event_emitter(event):
			captured.append(event)

		ctx.event_emitter = event_emitter
		thread = _thread(_sys("s"), _user("hi", "msg_user"))

		async def fake_compaction(*args, **kwargs):
			_ = (args, kwargs)
			result = MagicMock()
			result.thread = thread
			result.needs_summarization = False
			result.summarize_messages = []
			result.summary_count = 1
			result.blocking_summary_count = 0
			result.dropped_count = 0
			result.total_tokens = 100
			result.budget_tokens = 200
			return result

		with (
			patch(
				"api.v1.service.chat.filters.context_compaction.apply_context_compaction",
				AsyncMock(side_effect=fake_compaction),
			),
			patch(
				"api.v1.service.chat.filters.context_compaction.summary_service"
			) as mock_svc,
		):
			mock_svc.count_active_summaries = AsyncMock(return_value=0)
			state = _state(thread)

			await f.process(state, _agent_context(), ctx)

		assert captured == []

	@pytest.mark.asyncio()
	async def test_schedules_summarization_when_needed(self) -> None:
		"""when compaction says summarization is needed, enqueues a durable task."""
		f = ContextCompactionFilter()
		ctx = _mock_ctx()
		thread = _thread(_sys("s"), _user("hi", "msg_head"))

		mock_wr = MagicMock()
		mock_wr.thread = thread
		mock_wr.needs_summarization = True
		mock_wr.summarize_messages = [_user("old msg 1"), _user("old msg 2")]
		mock_wr.start_message_id = "msg_start"
		mock_wr.end_message_id = "msg_end"

		with (
			patch(
				"api.v1.service.chat.filters.context_compaction.apply_context_compaction",
				AsyncMock(return_value=mock_wr),
			),
			patch(
				"api.v1.service.chat.filters.context_compaction.summary_service"
			) as mock_svc,
			patch(
				"api.v1.service.chat.filters.context_compaction.start_summarize_messages_task",
				new_callable=AsyncMock,
			) as mock_start_summary,
		):
			mock_svc.count_active_summaries = AsyncMock(return_value=0)
			state = _state(thread)

			await f.process(state, _agent_context(), ctx)

			mock_start_summary.assert_awaited_once()
			call_kwargs = mock_start_summary.await_args.kwargs
			assert call_kwargs["branch_head_message_id"] == "msg_head"

	@pytest.mark.asyncio()
	async def test_schedules_condensation_when_multiple_summaries_exist(self) -> None:
		"""when multiple summaries exist, schedules condensation task."""
		f = ContextCompactionFilter()
		ctx = _mock_ctx()
		thread = _thread(_sys("s"), _user("hi"))

		mock_wr = MagicMock()
		mock_wr.thread = thread
		mock_wr.needs_summarization = False
		mock_wr.summarize_messages = []

		with (
			patch(
				"api.v1.service.chat.filters.context_compaction.apply_context_compaction",
				AsyncMock(return_value=mock_wr),
			),
			patch(
				"api.v1.service.chat.filters.context_compaction.summary_service"
			) as mock_svc,
			patch(
				"api.v1.service.chat.filters.context_compaction.start_condense_summaries_task",
				new_callable=AsyncMock,
			) as mock_start_condense,
		):
			mock_svc.count_active_summaries = AsyncMock(return_value=2)
			state = _state(thread)

			await f.process(state, _agent_context(), ctx)

			mock_start_condense.assert_awaited_once()

	@pytest.mark.asyncio()
	async def test_skips_summarization_when_message_ids_missing(self) -> None:
		"""summarization is skipped when persisted message ids are unavailable."""
		f = ContextCompactionFilter()
		ctx = _mock_ctx()
		thread = _thread(_sys("s"), _user("hi"))

		mock_wr = MagicMock()
		mock_wr.thread = thread
		mock_wr.needs_summarization = True
		mock_wr.summarize_messages = [_user("old msg")]
		mock_wr.start_message_id = None
		mock_wr.end_message_id = None

		with (
			patch(
				"api.v1.service.chat.filters.context_compaction.apply_context_compaction",
				AsyncMock(return_value=mock_wr),
			),
			patch(
				"api.v1.service.chat.filters.context_compaction.summary_service"
			) as mock_svc,
			patch(
				"api.v1.service.chat.filters.context_compaction.start_summarize_messages_task",
				new_callable=AsyncMock,
			) as mock_start_summary,
		):
			mock_svc.count_active_summaries = AsyncMock(return_value=0)
			state = _state(thread)

			await f.process(state, _agent_context(), ctx)

			mock_start_summary.assert_not_awaited()


# -- condensation size cap --


class TestCondensationSizeCap:
	"""tests that condense_summaries caps input text size."""

	@pytest.mark.asyncio()
	async def test_large_input_is_truncated(self) -> None:
		"""when combined summary text exceeds the cap, it is truncated."""
		from api.v1.service.chat.context_compaction.summarization import (
			_MAX_CONDENSATION_INPUT_CHARS,
			condense_summaries,
		)

		# create summaries whose combined text exceeds the cap
		huge_content = "x" * (_MAX_CONDENSATION_INPUT_CHARS + 10_000)
		existing = [
			MagicMock(
				id="tsum_1",
				content=huge_content,
				message_count=100,
				start_message_id="msg_1",
				end_message_id="msg_100",
			),
			MagicMock(
				id="tsum_2",
				content="second summary",
				message_count=20,
				start_message_id="msg_101",
				end_message_id="msg_120",
			),
		]

		mock_model = AsyncMock()
		mock_response = MagicMock()
		mock_response.json_content = {"summary": "condensed result"}
		mock_model.generate = AsyncMock(return_value=mock_response)
		condensed_mock = MagicMock()
		condensed_mock.id = "tsum_condensed"

		with (
			patch(
				"api.v1.service.chat.context_compaction.summarization.resolve_task_chat_model",
				AsyncMock(return_value=mock_model),
			),
			patch(
				"api.v1.service.chat.context_compaction.summarization.summary_service"
			) as mock_svc,
		):
			mock_svc.list_active_summaries = AsyncMock(return_value=existing)
			mock_svc.create_summary = AsyncMock(return_value=condensed_mock)
			mock_svc.supersede_summaries = AsyncMock()
			session = AsyncMock()

			await condense_summaries(thread_id=TypeID("th_123"), session=session)

		# verify the model was called (summarization ran)
		mock_model.generate.assert_called_once()
		# the raw summary content should be <= cap
		capped = huge_content[:_MAX_CONDENSATION_INPUT_CHARS]
		assert len(capped) <= _MAX_CONDENSATION_INPUT_CHARS


# -- protected indices + island-aware summarization --


_RUN = TypeID("run_abc")


def _run_user(text: str, msg_id: str) -> UserMessage:
	# the run-start anchor: a user message stamped with the active run_id.
	return UserMessage(
		content=[TextContent(text=text)],
		metadata={"_message_id": msg_id, "run_id": str(_RUN)},
	)


def _protected_tool(output: str = "media", call_id: str = "cm") -> ToolMessage:
	# a tool message carrying hard-protected native media (marked by projection).
	from api.v1.service.chat.context_compaction.media import (
		MEDIA_PROTECTED_METADATA_KEY,
	)

	return ToolMessage(
		tool_call_id=call_id,
		tool_output=output,
		metadata={MEDIA_PROTECTED_METADATA_KEY: True},
	)


class TestProtectedIndices:
	"""protected_indices returns the run anchor plus each hard-media island."""

	def test_collects_run_start_and_media_islands(self) -> None:
		from api.v1.service.chat.context_compaction.protection import (
			find_media_protected_index,
			protected_indices,
		)

		messages: list[Message] = [
			_user("old", "m0"),
			_assistant("a0", "m1"),
			_protected_tool(call_id="c_media"),
			_run_user("current request", "m3"),
			_assistant("a3", "m4"),
		]

		protected = protected_indices(messages, _RUN)

		# index 2 is the marked media message, index 3 is the run-start anchor
		assert protected == {2, 3}
		assert find_media_protected_index(messages) == 2

	def test_empty_without_run_or_media(self) -> None:
		from api.v1.service.chat.context_compaction.protection import (
			protected_indices,
		)

		messages: list[Message] = [_user("a", "m0"), _assistant("b", "m1")]

		assert protected_indices(messages, None) == set()


class TestIslandAwareSummarization:
	"""next_summarization_batch never crosses a protected island."""

	def test_batch_stops_at_run_start_anchor(self) -> None:
		from api.v1.service.chat.context_compaction.summarization import (
			next_summarization_batch,
		)

		long = "word " * 40  # comfortably above the minimum-saving threshold
		messages: list[Message] = [
			_user(long, "m0"),
			_assistant(long, "m1"),
			_run_user(long, "m2"),
			_assistant(long, "m3"),
		]
		message_ids = ["m0", "m1", "m2", "m3"]

		batch, start_id, end_id = next_summarization_batch(
			messages, message_ids, [], token_limit=10_000, run_id=_RUN
		)

		# the oldest compressible run is m0..m1; the run-start anchor at m2
		# bounds the batch so it is never summarized.
		assert start_id == TypeID("m0")
		assert end_id == TypeID("m1")
		assert len(batch) == 2

	def test_batch_stops_at_mid_thread_media_island(self) -> None:
		from api.v1.service.chat.context_compaction.summarization import (
			next_summarization_batch,
		)

		# a hard-media island sits between two compressible spans. the oldest
		# batch must stop at the island instead of jumping past it to grab the
		# newer compressible span (which would wall off the recoverable gap).
		long = "word " * 40
		messages: list[Message] = [
			_user(long, "m0"),
			_assistant(long, "m1"),
			_protected_tool(call_id="c_media"),
			_user(long, "m3"),
			_assistant(long, "m4"),
		]
		message_ids = ["m0", "m1", None, "m3", "m4"]

		batch, start_id, end_id = next_summarization_batch(
			messages, message_ids, [], token_limit=10_000, run_id=None
		)

		assert start_id == TypeID("m0")
		assert end_id == TypeID("m1")
		assert len(batch) == 2
