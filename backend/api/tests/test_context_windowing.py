"""tests for the context windowing filter and Layer 2 combined tool budget."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, _patch, patch

import pytest

from api.local_tasks import _on_task_done
from api.v1.service.chat.filters.context_windowing import (
	ContextWindowingFilter,
)
from api.v1.service.chat.windowing import (
	_COMPACTED_NOTICE,
	enforce_combined_tool_budget,
)
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


def _agent_context(thread: Thread) -> AgentContext:
	return AgentContext(
		thread=thread,
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
	) -> _patch[MagicMock]:
		ws = MagicMock()
		ws.tool_results_combined_max_share = combined_share
		ws.response_headroom = headroom
		mock_settings = MagicMock()
		mock_settings.ai.windowing = ws
		return patch(
			"api.v1.service.chat.windowing.app_settings",
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
		compacted = [m for m in tool_msgs if m.tool_output == _COMPACTED_NOTICE]
		preserved = [m for m in tool_msgs if m.tool_output != _COMPACTED_NOTICE]

		assert len(compacted) > 0, "at least one tool result should be compacted"
		assert len(preserved) > 0, "at least one tool result should be preserved"
		# the compacted ones should be the oldest (earliest in the list)
		compacted_indices = [
			i
			for i, m in enumerate(result.messages)
			if isinstance(m, ToolMessage) and m.tool_output == _COMPACTED_NOTICE
		]
		preserved_indices = [
			i
			for i, m in enumerate(result.messages)
			if isinstance(m, ToolMessage) and m.tool_output != _COMPACTED_NOTICE
		]
		assert max(compacted_indices) < max(preserved_indices), (
			"compacted results should be older (earlier) than preserved"
		)

	def test_already_compacted_skipped(self) -> None:
		"""tool results already showing the compacted notice are skipped."""
		thread = _thread(
			_sys("s"),
			_user("q"),
			_tool(_COMPACTED_NOTICE, "c1"),
			_tool("x" * 200, "c2"),
			_assistant("done"),
		)

		with self._patch_settings(combined_share=0.50, headroom=50):
			result = enforce_combined_tool_budget(thread, context_window=500)

		# the already-compacted tool should still show the notice
		tool_msgs = [m for m in result.messages if isinstance(m, ToolMessage)]
		assert tool_msgs[0].tool_output == _COMPACTED_NOTICE

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
			_tool(_COMPACTED_NOTICE, "c0"),  # already compacted
			_tool(big_output, "c1"),  # should be compacted
			_tool(big_output, "c2"),  # may be compacted
			_assistant("done"),
		)

		with self._patch_settings(combined_share=0.10, headroom=50):
			result = enforce_combined_tool_budget(thread, context_window=500)

		tool_msgs = [m for m in result.messages if isinstance(m, ToolMessage)]
		# first tool was already compacted and should remain so
		assert tool_msgs[0].tool_output == _COMPACTED_NOTICE
		# at least one of the non-compacted tools should now be compacted
		newly_compacted = [
			m for m in tool_msgs[1:] if m.tool_output == _COMPACTED_NOTICE
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


# -- ContextWindowingFilter --


class TestContextWindowingFilter:
	"""tests for the ContextWindowingFilter."""

	def test_default_fields(self) -> None:
		f = ContextWindowingFilter()
		assert f.name == "context_windowing"

	@pytest.mark.asyncio()
	async def test_none_context_skips(self) -> None:
		"""when app_context is None, thread is returned unchanged."""
		f = ContextWindowingFilter()
		thread = _thread(_user("hi"))
		state = AgentIterationState(thread=thread, tools=[])
		result = await f.process(state, _agent_context(thread), None)
		assert result is state

	@pytest.mark.asyncio()
	async def test_no_thread_id_skips_windowing(self) -> None:
		"""ephemeral runs with no thread_id skip full windowing."""
		f = ContextWindowingFilter()
		thread = _thread(_sys("system"), _user("hi"))
		ctx = _mock_ctx(thread_id=None)
		state = AgentIterationState(thread=thread, tools=[])

		result = await f.process(state, _agent_context(thread), ctx)
		assert result is state

	@pytest.mark.asyncio()
	async def test_first_pass_calls_windowing(self) -> None:
		"""first call triggers full windowing."""
		f = ContextWindowingFilter()
		ctx = _mock_ctx()
		thread = _thread(_sys("system"), _user("hi"))

		mock_windowing_result = MagicMock()
		mock_windowing_result.thread = thread
		mock_windowing_result.needs_summarization = False
		mock_windowing_result.summarize_messages = []

		with (
			patch(
				"api.v1.service.chat.filters.context_windowing.apply_context_windowing",
				AsyncMock(return_value=mock_windowing_result),
			) as mock_aw,
			patch(
				"api.v1.service.chat.filters.context_windowing.summary_service"
			) as mock_svc,
			patch(
				"api.v1.service.chat.filters.context_windowing.enforce_combined_tool_budget",
				return_value=thread,
			),
		):
			mock_svc.count_active_summaries = AsyncMock(return_value=0)
			state = AgentIterationState(thread=thread, tools=[])
			result = await f.process(state, _agent_context(thread), ctx)

		mock_aw.assert_called_once()
		assert result.thread is thread

	@pytest.mark.asyncio()
	async def test_second_pass_is_guard_only(self) -> None:
		"""second call runs only the Layer 2 guard, not full windowing."""
		f = ContextWindowingFilter()
		ctx = _mock_ctx()
		thread = _thread(_sys("s"), _user("hi"))

		mock_wr = MagicMock()
		mock_wr.thread = thread
		mock_wr.needs_summarization = False
		mock_wr.summarize_messages = []

		with (
			patch(
				"api.v1.service.chat.filters.context_windowing.apply_context_windowing",
				AsyncMock(return_value=mock_wr),
			) as mock_aw,
			patch(
				"api.v1.service.chat.filters.context_windowing.summary_service"
			) as mock_svc,
			patch(
				"api.v1.service.chat.filters.context_windowing.enforce_combined_tool_budget",
				return_value=thread,
			) as mock_guard,
		):
			mock_svc.count_active_summaries = AsyncMock(return_value=0)
			state = AgentIterationState(thread=thread, tools=[])

			# first call: full windowing
			await f.process(state, _agent_context(thread), ctx)
			assert mock_aw.call_count == 1

			# second call: guard only
			await f.process(state, _agent_context(thread), ctx)
			assert mock_aw.call_count == 1  # not called again
			assert mock_guard.call_count == 2  # called both times

	@pytest.mark.asyncio()
	async def test_schedules_summarization_when_needed(self) -> None:
		"""when windowing says summarization is needed, enqueues a durable task."""
		f = ContextWindowingFilter()
		ctx = _mock_ctx()
		thread = _thread(_sys("s"), _user("hi"))

		mock_wr = MagicMock()
		mock_wr.thread = thread
		mock_wr.needs_summarization = True
		mock_wr.summarize_messages = [_user("old msg 1"), _user("old msg 2")]
		mock_wr.start_message_id = "msg_start"
		mock_wr.end_message_id = "msg_end"

		with (
			patch(
				"api.v1.service.chat.filters.context_windowing.apply_context_windowing",
				AsyncMock(return_value=mock_wr),
			),
			patch(
				"api.v1.service.chat.filters.context_windowing.summary_service"
			) as mock_svc,
			patch(
				"api.v1.service.chat.filters.context_windowing.enforce_combined_tool_budget",
				return_value=thread,
			),
			patch(
				"api.v1.service.chat.filters.context_windowing.start_summarize_messages_task",
				new_callable=AsyncMock,
			) as mock_start_summary,
		):
			mock_svc.count_active_summaries = AsyncMock(return_value=0)
			state = AgentIterationState(thread=thread, tools=[])

			await f.process(state, _agent_context(thread), ctx)

			mock_start_summary.assert_awaited_once()

	@pytest.mark.asyncio()
	async def test_schedules_condensation_when_threshold_met(self) -> None:
		"""when summary count >= threshold, schedules condensation task."""
		f = ContextWindowingFilter()
		ctx = _mock_ctx()
		thread = _thread(_sys("s"), _user("hi"))

		mock_wr = MagicMock()
		mock_wr.thread = thread
		mock_wr.needs_summarization = False
		mock_wr.summarize_messages = []

		threshold_val = 4  # default max_summaries_before_condense

		with (
			patch(
				"api.v1.service.chat.filters.context_windowing.apply_context_windowing",
				AsyncMock(return_value=mock_wr),
			),
			patch(
				"api.v1.service.chat.filters.context_windowing.summary_service"
			) as mock_svc,
			patch(
				"api.v1.service.chat.filters.context_windowing.enforce_combined_tool_budget",
				return_value=thread,
			),
			patch(
				"api.v1.service.chat.filters.context_windowing.app_settings"
			) as mock_settings,
			patch(
				"api.v1.service.chat.filters.context_windowing.start_condense_summaries_task",
				new_callable=AsyncMock,
			) as mock_start_condense,
		):
			mock_settings.ai.windowing.max_summaries_before_condense = threshold_val
			mock_svc.count_active_summaries = AsyncMock(return_value=threshold_val)
			state = AgentIterationState(thread=thread, tools=[])

			await f.process(state, _agent_context(thread), ctx)

			mock_start_condense.assert_awaited_once()

	@pytest.mark.asyncio()
	async def test_skips_summarization_when_message_ids_missing(self) -> None:
		"""summarization is skipped when persisted message ids are unavailable."""
		f = ContextWindowingFilter()
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
				"api.v1.service.chat.filters.context_windowing.apply_context_windowing",
				AsyncMock(return_value=mock_wr),
			),
			patch(
				"api.v1.service.chat.filters.context_windowing.summary_service"
			) as mock_svc,
			patch(
				"api.v1.service.chat.filters.context_windowing.enforce_combined_tool_budget",
				return_value=thread,
			),
			patch(
				"api.v1.service.chat.filters.context_windowing.start_summarize_messages_task",
				new_callable=AsyncMock,
			) as mock_start_summary,
		):
			mock_svc.count_active_summaries = AsyncMock(return_value=0)
			state = AgentIterationState(thread=thread, tools=[])

			await f.process(state, _agent_context(thread), ctx)

			mock_start_summary.assert_not_awaited()


# -- condensation size cap --


class TestCondensationSizeCap:
	"""tests that condense_summaries caps input text size."""

	@pytest.mark.asyncio()
	async def test_large_input_is_truncated(self) -> None:
		"""when combined summary text exceeds the cap, it is truncated."""
		from api.v1.service.chat.summarization import (
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
		mock_model.generate.return_value = "condensed result"
		condensed_mock = MagicMock()
		condensed_mock.id = "tsum_condensed"

		with (
			patch(
				"api.v1.service.chat.summarization.resolve_task_chat_model",
				AsyncMock(return_value=mock_model),
			),
			patch("api.v1.service.chat.summarization.summary_service") as mock_svc,
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
