"""tests for context compaction logic."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.models.thread_summary import SummaryPurpose
from api.v1.service.chat.context_compaction import (
	ContextCompactionResult,
	apply_context_compaction,
)
from api.v1.service.chat.context_compaction.media import (
	MEDIA_PROTECTED_METADATA_KEY,
)
from api.v1.service.chat.context_compaction.summarization import (
	build_compaction_info,
	build_positional_summary_message,
	find_summarized_cutoff,
	oldest_positional_summary,
	replace_chat_window_sentinel,
)
from api.v1.service.chat.context_compaction.types import ContextCompactionError
from api.v1.service.chat.message_metadata import get_message_id
from api.v1.service.prompts import SENTINEL_CHAT_WINDOW_INFO
from nokodo_ai.messages import (
	AssistantMessage,
	Message,
	SystemMessage,
	TextContent,
	ToolCall,
	ToolMessage,
	UserMessage,
)
from nokodo_ai.threads import Thread
from nokodo_ai.tool import ToolDefinition
from nokodo_ai.types.json import JSONObject
from nokodo_ai.utils.typeid import TypeID


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


def _assistant_tool_call(name: str, msg_id: str | None = None) -> AssistantMessage:
	meta: JSONObject | None = {"_message_id": msg_id} if msg_id else None
	return AssistantMessage(
		content=[TextContent(text=f"calling {name}")],
		tool_calls=[ToolCall(id="call_1", name=name, arguments={})],
		metadata=meta,
	)


def _tool(output: str, msg_id: str | None = None) -> ToolMessage:
	meta: JSONObject | None = {"_message_id": msg_id} if msg_id else None
	return ToolMessage(
		tool_call_id="call_1",
		tool_output=output,
		metadata=meta,
	)


def _thread(*msgs: Message) -> Thread:
	return Thread(messages=list(msgs))


_TID = TypeID("th_123")
PIPELINE_SETTINGS = "api.v1.service.chat.context_compaction.pipeline.app_settings"
PIPELINE_SUMMARY_SERVICE = (
	"api.v1.service.chat.context_compaction.pipeline.summary_service"
)


def _mock_summary(
	end_message_id: str | None = None,
	content: str = "summary content",
	start_message_id: str | None = None,
) -> MagicMock:
	s = MagicMock()
	s.id = f"sum_{start_message_id or 'start'}_{end_message_id or 'end'}"
	s.start_message_id = start_message_id
	s.end_message_id = end_message_id
	s.content = content
	return s


# -- get_message_id --


class TestGetMessageId:
	def test_returns_id_from_metadata(self) -> None:
		msg = _user("hi", msg_id="msg_123")
		assert get_message_id(msg) == "msg_123"

	def test_returns_none_when_no_metadata(self) -> None:
		msg = _user("hi")
		assert get_message_id(msg) is None

	def test_returns_none_when_no_message_id_key(self) -> None:
		msg = UserMessage(
			content=[TextContent(text="hi")],
			metadata={"other": "val"},
		)
		assert get_message_id(msg) is None


# -- find_summarized_cutoff --


class TestFindSummarizedCutoff:
	def test_no_summaries_returns_zero(self) -> None:
		assert find_summarized_cutoff([], ["a", "b", "c"]) == 0

	def test_finds_cutoff_at_end_id(self) -> None:
		s = _mock_summary(end_message_id="b")
		result = find_summarized_cutoff([s], ["a", "b", "c", "d"])
		assert result == 2  # index 1 + 1

	def test_no_matching_ids(self) -> None:
		s = _mock_summary(end_message_id="z")
		result = find_summarized_cutoff([s], ["a", "b", "c"])
		assert result == 0

	def test_multiple_summaries_takes_max(self) -> None:
		s1 = _mock_summary(end_message_id="b")
		s2 = _mock_summary(end_message_id="d")
		result = find_summarized_cutoff([s1, s2], ["a", "b", "c", "d", "e"])
		assert result == 4

	def test_summary_with_no_end_id(self) -> None:
		s = _mock_summary(end_message_id=None)
		result = find_summarized_cutoff([s], ["a", "b"])
		assert result == 0

	def test_none_ids_in_branch(self) -> None:
		s = _mock_summary(end_message_id="b")
		result = find_summarized_cutoff([s], [None, "b", None])
		assert result == 2


# -- positional summary selection --


class TestPositionalSummaries:
	def test_builds_system_message_with_summary_marker(self) -> None:
		summary = _mock_summary(content="users discussed login flow")
		message = build_positional_summary_message(summary)
		assert isinstance(message, SystemMessage)
		assert "compacted conversation summary" in (message.text or "")
		assert "users discussed login flow" in (message.text or "")

	def test_selects_oldest_saving_summary(self) -> None:
		summary = _mock_summary(
			start_message_id="m1",
			end_message_id="m2",
			content="short unique summary",
		)
		messages: list[Message] = [_user("x" * 2000, "m1"), _user("y" * 2000, "m2")]
		selection = oldest_positional_summary([summary], messages, ["m1", "m2"])
		assert selection is not None
		selected, start_index, end_index, summary_message = selection
		assert selected is summary
		assert (start_index, end_index) == (0, 1)
		assert isinstance(summary_message, SystemMessage)

	def test_skips_summary_that_would_not_save_tokens(self) -> None:
		summary = _mock_summary(
			start_message_id="m1",
			end_message_id="m1",
			content="x" * 4000,
		)
		messages: list[Message] = [_user("short", "m1")]
		selection = oldest_positional_summary([summary], messages, ["m1"])
		assert selection is None


# -- build_compaction_info --


class TestBuildCompactionInfo:
	def test_basic_output(self) -> None:
		info = build_compaction_info(
			summary_count=0,
			dropped_count=0,
			total_tokens=500,
			budget_tokens=1000,
			original_message_count=10,
			visible_message_count=10,
		)
		assert "[context compaction info:" in info
		assert "10 recent messages" in info

	def test_with_summaries(self) -> None:
		info = build_compaction_info(
			summary_count=2,
			dropped_count=0,
			total_tokens=500,
			budget_tokens=1000,
			original_message_count=30,
			visible_message_count=10,
		)
		assert "2 summary/summaries" in info
		assert "20 earlier messages have been summarized" in info

	def test_with_pruning(self) -> None:
		info = build_compaction_info(
			summary_count=0,
			dropped_count=5,
			total_tokens=900,
			budget_tokens=1000,
			original_message_count=15,
			visible_message_count=10,
		)
		assert "5 messages were pruned" in info

	def test_context_usage_percentage(self) -> None:
		info = build_compaction_info(
			summary_count=0,
			dropped_count=0,
			total_tokens=750,
			budget_tokens=1000,
			original_message_count=10,
			visible_message_count=10,
		)
		assert "~75%" in info

	def test_zero_budget_no_percentage(self) -> None:
		info = build_compaction_info(
			summary_count=0,
			dropped_count=0,
			total_tokens=100,
			budget_tokens=0,
			original_message_count=5,
			visible_message_count=5,
		)
		# should not crash on zero division
		assert "recent messages" in info


# -- replace_chat_window_sentinel --


class TestReplaceChatWindowSentinel:
	def test_replaces_sentinel_in_system_message(self) -> None:
		msgs: list[Message] = [_sys(f"info: {SENTINEL_CHAT_WINDOW_INFO}")]
		result = replace_chat_window_sentinel(msgs, "[test info]")
		assert isinstance(result[0], SystemMessage)
		assert result[0].text == "info: [test info]"

	def test_no_sentinel_unchanged(self) -> None:
		msgs: list[Message] = [_sys("no sentinel here")]
		result = replace_chat_window_sentinel(msgs, "[test info]")
		assert isinstance(result[0], SystemMessage)
		assert result[0].text == "no sentinel here"

	def test_non_system_messages_unchanged(self) -> None:
		msgs: list[Message] = [_user("hello")]
		result = replace_chat_window_sentinel(msgs, "[test info]")
		assert isinstance(result[0], UserMessage)
		assert result[0].text == "hello"

	def test_does_not_mutate_original(self) -> None:
		original: list[Message] = [_sys(f"info: {SENTINEL_CHAT_WINDOW_INFO}")]
		replace_chat_window_sentinel(original, "[test info]")
		assert isinstance(original[0], SystemMessage)
		assert SENTINEL_CHAT_WINDOW_INFO in (original[0].text or "")


# -- apply_context_compaction --


def _compaction_settings(**overrides: bool | int | float) -> MagicMock:
	"""create mock context compaction settings with defaults."""
	defaults = {
		"enabled": True,
		"trigger_ratio": 0.70,
		"recovery_target_ratio": 0.55,
		"target_usage_cap_tokens": None,
		"summary_batch_min_tokens": 512,
		"summary_batch_max_tokens": 16_000,
		"prompt_overhead_tokens": 300,
		"blocking_summarization_enabled": True,
		"blocking_summarization_timeout_seconds": 20.0,
		"tool_result_max_share": 0.25,
		"tool_result_hard_cap": 100_000,
		"tool_results_combined_max_share": 0.50,
		"response_headroom": 4096,
		"summarization_max_chars_per_message": 2000,
	}
	defaults.update(overrides)
	ws = MagicMock()
	for k, v in defaults.items():
		setattr(ws, k, v)
	return ws


@pytest.fixture()
def mock_session() -> AsyncMock:
	return AsyncMock()


class TestApplyContextCompaction:
	@pytest.mark.asyncio()
	async def test_disabled_returns_original(self, mock_session: AsyncMock) -> None:
		ws = _compaction_settings(enabled=False)
		thread = _thread(_sys("hello"), _user("hi", "m1"))
		with patch(PIPELINE_SETTINGS) as mock_settings:
			mock_settings.ai.context_compaction = ws
			result = await apply_context_compaction(
				thread,
				context_window=128_000,
				thread_id=_TID,
				session=mock_session,
			)
		assert len(result.thread.messages) == 2
		assert not result.needs_summarization

	@pytest.mark.asyncio()
	async def test_disabled_clears_sentinel(self, mock_session: AsyncMock) -> None:
		ws = _compaction_settings(enabled=False)
		thread = _thread(
			_sys(f"prompt with {SENTINEL_CHAT_WINDOW_INFO}"),
			_user("hi", "m1"),
		)
		with patch(PIPELINE_SETTINGS) as mock_settings:
			mock_settings.ai.context_compaction = ws
			result = await apply_context_compaction(
				thread,
				context_window=128_000,
				thread_id=_TID,
				session=mock_session,
			)
		sys_msg = result.thread.messages[0]
		assert isinstance(sys_msg, SystemMessage)
		sys_text = sys_msg.text or ""
		assert SENTINEL_CHAT_WINDOW_INFO not in sys_text

	@pytest.mark.asyncio()
	async def test_no_truncation_when_under_budget(
		self,
		mock_session: AsyncMock,
	) -> None:
		ws = _compaction_settings()
		msgs: list[Message] = [
			_sys("system"),
			_user("hi", "m1"),
			_assistant("hello", "m2"),
		]
		thread = _thread(*msgs)

		with (
			patch(PIPELINE_SETTINGS) as mock_settings,
			patch(PIPELINE_SUMMARY_SERVICE) as mock_svc,
		):
			mock_settings.ai.context_compaction = ws
			mock_svc.list_active_summaries = AsyncMock(return_value=[])
			result = await apply_context_compaction(
				thread,
				context_window=128_000,
				thread_id=_TID,
				session=mock_session,
			)

		assert result.dropped_count == 0
		assert not result.needs_summarization
		# system + 2 conversation messages
		assert len(result.thread.messages) == 3

	@pytest.mark.asyncio()
	async def test_message_count_does_not_drop_when_tokens_fit(
		self,
		mock_session: AsyncMock,
	) -> None:
		ws = _compaction_settings()
		msgs: list[Message] = [_sys("system")]
		for i in range(5):
			msgs.append(_user(f"msg {i}", f"m{i}"))
		thread = _thread(*msgs)

		with (
			patch(PIPELINE_SETTINGS) as mock_settings,
			patch(PIPELINE_SUMMARY_SERVICE) as mock_svc,
		):
			mock_settings.ai.context_compaction = ws
			mock_svc.list_active_summaries = AsyncMock(return_value=[])
			result = await apply_context_compaction(
				thread,
				context_window=128_000,
				thread_id=_TID,
				session=mock_session,
			)

		assert result.dropped_count == 0
		conversation_msgs = [
			m for m in result.thread.messages if not isinstance(m, SystemMessage)
		]
		assert len(conversation_msgs) == 5

	@pytest.mark.asyncio()
	async def test_hard_truncation(self, mock_session: AsyncMock) -> None:
		ws = _compaction_settings()
		# create many short messages that collectively exceed budget
		msgs: list[Message] = [_sys("system")]
		for i in range(40):
			msgs.append(_user(f"message content number {i} with some text", f"m{i}"))
		thread = _thread(*msgs)

		with (
			patch(PIPELINE_SETTINGS) as mock_settings,
			patch(PIPELINE_SUMMARY_SERVICE) as mock_svc,
		):
			mock_settings.ai.context_compaction = ws
			mock_svc.list_active_summaries = AsyncMock(return_value=[])
			# small positive prompt budget to force hard truncation
			result = await apply_context_compaction(
				thread,
				context_window=4_600,
				thread_id=_TID,
				session=mock_session,
			)

		# some messages should have been dropped
		assert result.dropped_count > 0

	@pytest.mark.asyncio()
	async def test_throws_when_protected_media_busts_budget(
		self,
		mock_session: AsyncMock,
	) -> None:
		# a hard-protected (read-this-iteration) tool message alone exceeds the
		# window. prune cannot drop it, so the cascade hits the terminal throw
		# with the media-specific guidance.
		ws = _compaction_settings()
		protected_tool = ToolMessage(
			tool_call_id="call_1",
			tool_output="y" * 80_000,
			metadata={"_message_id": "m3", MEDIA_PROTECTED_METADATA_KEY: True},
		)
		thread = _thread(
			_sys("system"),
			_user("show me the file", "m1"),
			_assistant_tool_call("file_get", "m2"),
			protected_tool,
		)

		with (
			patch(PIPELINE_SETTINGS) as mock_settings,
			patch(PIPELINE_SUMMARY_SERVICE) as mock_svc,
		):
			mock_settings.ai.context_compaction = ws
			mock_svc.list_active_summaries = AsyncMock(return_value=[])
			with pytest.raises(ContextCompactionError, match="protected native media"):
				await apply_context_compaction(
					thread,
					context_window=4_600,
					thread_id=_TID,
					session=mock_session,
				)

	@pytest.mark.asyncio()
	async def test_throws_generic_when_protected_run_start_busts_budget(
		self,
		mock_session: AsyncMock,
	) -> None:
		# the active run-start user message alone exceeds the window and carries
		# no media. prune protects it, so the cascade hits the generic terminal
		# throw (not the media-specific one).
		ws = _compaction_settings()
		run_id = TypeID("run_1")
		run_start = UserMessage(
			content=[TextContent(text="y" * 80_000)],
			metadata={"_message_id": "m1", "run_id": str(run_id)},
		)
		thread = _thread(_sys("system"), run_start)

		with (
			patch(PIPELINE_SETTINGS) as mock_settings,
			patch(PIPELINE_SUMMARY_SERVICE) as mock_svc,
		):
			mock_settings.ai.context_compaction = ws
			mock_svc.list_active_summaries = AsyncMock(return_value=[])
			with pytest.raises(
				ContextCompactionError, match="protected active-run context"
			):
				await apply_context_compaction(
					thread,
					context_window=4_600,
					thread_id=_TID,
					session=mock_session,
					run_id=run_id,
				)

	@pytest.mark.asyncio()
	async def test_trigger_signals_summarization(
		self,
		mock_session: AsyncMock,
	) -> None:
		ws = _compaction_settings(trigger_ratio=0.70, recovery_target_ratio=0.55)
		msgs: list[Message] = [_sys("system")]
		# each message ~300 chars to build up enough token mass
		for i in range(10):
			msgs.append(_user(f"{'x' * 300} message {i}", f"m{i}"))
		thread = _thread(*msgs)

		with (
			patch(PIPELINE_SETTINGS) as mock_settings,
			patch(PIPELINE_SUMMARY_SERVICE) as mock_svc,
		):
			mock_settings.ai.context_compaction = ws
			mock_svc.list_active_summaries = AsyncMock(return_value=[])
			# context window large enough to fit raw messages but small
			# enough that current pressure crosses the soft threshold
			result = await apply_context_compaction(
				thread,
				context_window=5_600,
				thread_id=_TID,
				session=mock_session,
			)

		assert result.needs_summarization
		assert len(result.summarize_messages) > 0

	@pytest.mark.asyncio()
	async def test_trigger_uses_current_pressure_without_iteration_heuristics(
		self,
		mock_session: AsyncMock,
	) -> None:
		ws = _compaction_settings(trigger_ratio=0.90)
		msgs: list[Message] = [_sys("system")]
		for i in range(10):
			msgs.append(_user(f"{'x' * 300} message {i}", f"m{i}"))
		thread = _thread(
			*msgs,
			_assistant_tool_call("web_search", "m_tool_call"),
			_tool("y" * 3000, "m_tool_result"),
		)

		with (
			patch(PIPELINE_SETTINGS) as mock_settings,
			patch(PIPELINE_SUMMARY_SERVICE) as mock_svc,
		):
			mock_settings.ai.context_compaction = ws
			mock_svc.list_active_summaries = AsyncMock(return_value=[])
			first_iteration = await apply_context_compaction(
				thread,
				context_window=8_000,
				thread_id=_TID,
				session=mock_session,
				run_id=TypeID("run_1"),
				iteration=0,
			)
			second_iteration = await apply_context_compaction(
				thread,
				context_window=8_000,
				thread_id=_TID,
				session=mock_session,
				run_id=TypeID("run_1"),
				iteration=1,
			)

		assert (
			first_iteration.needs_summarization == second_iteration.needs_summarization
		)
		assert len(first_iteration.summarize_messages) == len(
			second_iteration.summarize_messages
		)

	@pytest.mark.asyncio()
	async def test_recovery_target_sizes_summary_batch(
		self,
		mock_session: AsyncMock,
	) -> None:
		ws = _compaction_settings(
			trigger_ratio=0.01,
			recovery_target_ratio=0.10,
			summary_batch_min_tokens=1,
			summary_batch_max_tokens=300,
		)
		msgs: list[Message] = [_sys("system")]
		for i in range(10):
			msgs.append(_user(f"{'x' * 300} message {i}", f"m{i}"))
		thread = _thread(*msgs)

		with (
			patch(PIPELINE_SETTINGS) as mock_settings,
			patch(PIPELINE_SUMMARY_SERVICE) as mock_svc,
		):
			mock_settings.ai.context_compaction = ws
			mock_svc.list_active_summaries = AsyncMock(return_value=[])
			result = await apply_context_compaction(
				thread,
				context_window=10_000,
				thread_id=_TID,
				session=mock_session,
			)

		assert result.needs_summarization
		assert len(result.summarize_messages) < len(msgs) - 1

	@pytest.mark.asyncio()
	async def test_summary_not_injected_when_full_thread_fits(
		self,
		mock_session: AsyncMock,
	) -> None:
		ws = _compaction_settings()
		summary = _mock_summary(
			end_message_id="m2",
			content="user discussed project setup",
		)
		msgs: list[Message] = [
			_sys("system"),
			_user("first", "m1"),
			_user("second", "m2"),
			_user("third", "m3"),
			_user("fourth", "m4"),
		]
		thread = _thread(*msgs)

		with (
			patch(PIPELINE_SETTINGS) as mock_settings,
			patch(PIPELINE_SUMMARY_SERVICE) as mock_svc,
		):
			mock_settings.ai.context_compaction = ws
			mock_svc.list_active_summaries = AsyncMock(return_value=[summary])
			result = await apply_context_compaction(
				thread,
				context_window=128_000,
				thread_id=_TID,
				session=mock_session,
			)
			mock_svc.list_active_summaries.assert_not_awaited()

		sys_msg = result.thread.messages[0]
		assert isinstance(sys_msg, SystemMessage)
		sys_text = sys_msg.text or ""
		assert "user discussed project setup" not in sys_text
		assert "conversation history summary" not in sys_text
		conversation_msgs = [
			m for m in result.thread.messages if not isinstance(m, SystemMessage)
		]
		assert len(conversation_msgs) == 4

	@pytest.mark.asyncio()
	async def test_summary_swapped_only_when_full_thread_over_budget(
		self,
		mock_session: AsyncMock,
	) -> None:
		ws = _compaction_settings()
		summary = _mock_summary(
			end_message_id="m2",
			content="user discussed project setup",
		)
		msgs: list[Message] = [
			_sys("system"),
			_user("x" * 2500, "m1"),
			_assistant("y" * 2500, "m2"),
			_user("next question", "m3"),
		]
		thread = _thread(*msgs)

		with (
			patch(PIPELINE_SETTINGS) as mock_settings,
			patch(PIPELINE_SUMMARY_SERVICE) as mock_svc,
		):
			mock_settings.ai.context_compaction = ws
			mock_svc.list_active_summaries = AsyncMock(return_value=[summary])
			result = await apply_context_compaction(
				thread,
				context_window=5_000,
				thread_id=_TID,
				session=mock_session,
			)
			mock_svc.list_active_summaries.assert_awaited_once_with(
				_TID,
				mock_session,
				purpose=SummaryPurpose.AGENT_CONTEXT,
			)

		assert isinstance(result.thread.messages[1], SystemMessage)
		assert "user discussed project setup" in (result.thread.messages[1].text or "")
		assert isinstance(result.thread.messages[2], UserMessage)
		assert result.thread.messages[2].text == "next question"

	@pytest.mark.asyncio()
	async def test_target_usage_cap_can_force_compaction_below_model_window(
		self,
		mock_session: AsyncMock,
	) -> None:
		ws = _compaction_settings(target_usage_cap_tokens=5_000)
		summary = _mock_summary(
			end_message_id="m1",
			content="summary forced by target usage cap",
		)
		thread = _thread(
			_sys("system"),
			_user("x" * 2500, "m1"),
			_user("latest", "m2"),
		)

		with (
			patch(PIPELINE_SETTINGS) as mock_settings,
			patch(PIPELINE_SUMMARY_SERVICE) as mock_svc,
		):
			mock_settings.ai.context_compaction = ws
			mock_svc.list_active_summaries = AsyncMock(return_value=[summary])
			result = await apply_context_compaction(
				thread,
				context_window=128_000,
				thread_id=_TID,
				session=mock_session,
			)

		conversation_texts = [
			message.text
			for message in result.thread.messages
			if isinstance(message, (SystemMessage, UserMessage))
		]
		assert any(
			"summary forced by target usage cap" in (text or "")
			for text in conversation_texts
		)
		assert result.budget_tokens < 128_000

	@pytest.mark.asyncio()
	async def test_ready_summaries_apply_only_until_thread_fits(
		self,
		mock_session: AsyncMock,
	) -> None:
		ws = _compaction_settings()
		first_summary = _mock_summary(
			start_message_id="m1",
			end_message_id="m1",
			content="first ready summary",
		)
		second_summary = _mock_summary(
			start_message_id="m2",
			end_message_id="m2",
			content="second ready summary",
		)
		thread = _thread(
			_sys("system"),
			_user("x" * 8000, "m1"),
			_user("middle raw message", "m2"),
			_user("latest", "m3"),
		)

		with (
			patch(PIPELINE_SETTINGS) as mock_settings,
			patch(PIPELINE_SUMMARY_SERVICE) as mock_svc,
		):
			mock_settings.ai.context_compaction = ws
			mock_svc.list_active_summaries = AsyncMock(
				return_value=[first_summary, second_summary]
			)
			result = await apply_context_compaction(
				thread,
				context_window=5_000,
				thread_id=_TID,
				session=mock_session,
			)

		summary_texts = [
			message.text
			for message in result.thread.messages
			if isinstance(message, SystemMessage)
		]
		conversation_texts = [
			message.text
			for message in result.thread.messages
			if isinstance(message, UserMessage)
		]
		assert any("first ready summary" in (text or "") for text in summary_texts)
		assert not any("second ready summary" in (text or "") for text in summary_texts)
		assert "middle raw message" in conversation_texts
		assert "latest" in conversation_texts

	@pytest.mark.asyncio()
	async def test_dropped_notice_when_no_summaries(
		self,
		mock_session: AsyncMock,
	) -> None:
		ws = _compaction_settings()
		msgs: list[Message] = [_sys("system")]
		for i in range(5):
			msgs.append(_user(f"{'x' * 2000} msg {i}", f"m{i}"))
		thread = _thread(*msgs)

		with (
			patch(PIPELINE_SETTINGS) as mock_settings,
			patch(PIPELINE_SUMMARY_SERVICE) as mock_svc,
		):
			mock_settings.ai.context_compaction = ws
			mock_svc.list_active_summaries = AsyncMock(return_value=[])
			result = await apply_context_compaction(
				thread,
				context_window=5_000,
				thread_id=_TID,
				session=mock_session,
			)

		# should have a notice about dropped messages
		all_text = " ".join(
			(
				m.text
				if isinstance(m, (SystemMessage, UserMessage, AssistantMessage))
				else ""
			)
			or ""
			for m in result.thread.messages
		)
		assert "earlier messages not shown" in all_text

	@pytest.mark.asyncio()
	async def test_old_tool_call_arguments_compacted_before_drop(
		self,
		mock_session: AsyncMock,
	) -> None:
		ws = _compaction_settings()
		assistant = AssistantMessage(
			content=[TextContent(text="using a tool")],
			tool_calls=[ToolCall(name="file_update", arguments={"patch": "x" * 4000})],
			metadata={"_message_id": "m2"},
		)
		thread = _thread(
			_sys("system"),
			_user("please edit a file", "m1"),
			assistant,
			_user("continue", "m3"),
		)

		with (
			patch(PIPELINE_SETTINGS) as mock_settings,
			patch(PIPELINE_SUMMARY_SERVICE) as mock_svc,
		):
			mock_settings.ai.context_compaction = ws
			mock_svc.list_active_summaries = AsyncMock(return_value=[])
			result = await apply_context_compaction(
				thread,
				context_window=5_000,
				thread_id=_TID,
				session=mock_session,
			)

		assert result.compacted_tool_call_count == 1
		assert result.dropped_count == 0
		compacted = next(
			message
			for message in result.thread.messages
			if isinstance(message, AssistantMessage)
		)
		assert compacted.tool_calls[0].arguments == {
			"_compacted": "tool call arguments removed to free context"
		}

	@pytest.mark.asyncio()
	async def test_tool_outputs_truncated_before_message_drop(
		self,
		mock_session: AsyncMock,
	) -> None:
		ws = _compaction_settings()
		thread = _thread(
			_sys("system"),
			_user("important original request", "m1"),
			_assistant("calling tool", "m2"),
			_tool("x" * 4000, "m3"),
			_user("follow-up that still needs context", "m4"),
		)

		with (
			patch(PIPELINE_SETTINGS) as mock_settings,
			patch(PIPELINE_SUMMARY_SERVICE) as mock_svc,
		):
			mock_settings.ai.context_compaction = ws
			mock_svc.list_active_summaries = AsyncMock(return_value=[])
			result = await apply_context_compaction(
				thread,
				context_window=5_000,
				thread_id=_TID,
				session=mock_session,
			)

		assert result.compacted_tool_result_count == 1
		assert result.dropped_count == 0
		texts = [getattr(message, "text", None) for message in result.thread.messages]
		assert "important original request" in texts
		compacted_tool = next(
			message
			for message in result.thread.messages
			if isinstance(message, ToolMessage)
		)
		assert "[... truncated:" in compacted_tool.tool_output

	@pytest.mark.asyncio()
	async def test_duplicate_tool_outputs_compacted_before_drop(
		self,
		mock_session: AsyncMock,
	) -> None:
		ws = _compaction_settings()
		duplicate_output = "search result " + "x" * 4000
		thread = _thread(
			_sys("system"),
			_user("first request", "m1"),
			_tool(duplicate_output, "m2"),
			_tool(duplicate_output, "m3"),
			_user("latest", "m4"),
		)

		with (
			patch(PIPELINE_SETTINGS) as mock_settings,
			patch(PIPELINE_SUMMARY_SERVICE) as mock_svc,
		):
			mock_settings.ai.context_compaction = ws
			mock_svc.list_active_summaries = AsyncMock(return_value=[])
			result = await apply_context_compaction(
				thread,
				context_window=5_000,
				thread_id=_TID,
				session=mock_session,
			)

		tool_outputs = [
			message.tool_output
			for message in result.thread.messages
			if isinstance(message, ToolMessage)
		]
		assert result.compacted_tool_result_count >= 1
		assert any("duplicate tool output" in output for output in tool_outputs)

	@pytest.mark.asyncio()
	async def test_tool_schema_overhead_participates_in_budget(
		self,
		mock_session: AsyncMock,
	) -> None:
		ws = _compaction_settings()
		summary = _mock_summary(
			end_message_id="m1",
			content="old request summary",
		)
		thread = _thread(
			_sys("system"),
			_user("x" * 8000, "m1"),
			_user("latest", "m2"),
		)
		tools = [
			ToolDefinition(
				name="large_schema_tool",
				description="x" * 12_000,
				parameters={"type": "object", "properties": {}},
			)
		]

		with (
			patch(PIPELINE_SETTINGS) as mock_settings,
			patch(PIPELINE_SUMMARY_SERVICE) as mock_svc,
		):
			mock_settings.ai.context_compaction = ws
			mock_svc.list_active_summaries = AsyncMock(return_value=[summary])
			result = await apply_context_compaction(
				thread,
				context_window=10_000,
				thread_id=_TID,
				session=mock_session,
				tool_definitions=tools,
			)

		conversation_texts = [
			message.text
			for message in result.thread.messages
			if isinstance(message, (SystemMessage, UserMessage))
		]
		assert any("old request summary" in (text or "") for text in conversation_texts)

	@pytest.mark.asyncio()
	async def test_run_start_user_message_is_not_summarized_or_dropped(
		self,
		mock_session: AsyncMock,
	) -> None:
		ws = _compaction_settings()
		run_id = TypeID("run_123")
		current_user = UserMessage(
			content=[TextContent(text="current request")],
			metadata={"_message_id": "m2", "run_id": str(run_id)},
		)
		summary = _mock_summary(
			end_message_id="m2",
			content="summary that would incorrectly cover the active request",
		)
		thread = _thread(
			_sys("system"),
			_user("x" * 6000, "m1"),
			current_user,
		)

		with (
			patch(PIPELINE_SETTINGS) as mock_settings,
			patch(PIPELINE_SUMMARY_SERVICE) as mock_svc,
		):
			mock_settings.ai.context_compaction = ws
			mock_svc.list_active_summaries = AsyncMock(return_value=[summary])
			result = await apply_context_compaction(
				thread,
				context_window=5_000,
				thread_id=_TID,
				session=mock_session,
				run_id=run_id,
			)

		all_text = " ".join(
			getattr(message, "text", "") or "" for message in result.thread.messages
		)
		assert "current request" in all_text
		assert "incorrectly cover the active request" not in all_text

	@pytest.mark.asyncio()
	async def test_tail_tool_output_can_be_compacted(
		self,
		mock_session: AsyncMock,
	) -> None:
		ws = _compaction_settings()
		assistant = AssistantMessage(
			content=[TextContent(text="calling tool")],
			tool_calls=[ToolCall(id="call_1", name="lookup", arguments={})],
			metadata={"_message_id": "m2"},
		)
		fresh_output = "fresh output " + "x" * 1000
		thread = _thread(
			_sys("system"),
			_user("x" * 6000, "m1"),
			assistant,
			_tool(fresh_output, "m3"),
		)

		with (
			patch(PIPELINE_SETTINGS) as mock_settings,
			patch(PIPELINE_SUMMARY_SERVICE) as mock_svc,
		):
			mock_settings.ai.context_compaction = ws
			mock_svc.list_active_summaries = AsyncMock(return_value=[])
			result = await apply_context_compaction(
				thread,
				context_window=5_000,
				thread_id=_TID,
				session=mock_session,
			)

		tool_msg = next(
			message
			for message in result.thread.messages
			if isinstance(message, ToolMessage)
		)
		assert tool_msg.tool_output != fresh_output
		assert "compacted" in tool_msg.tool_output

	@pytest.mark.asyncio()
	async def test_blocking_summary_is_last_resort_before_drop(
		self,
		mock_session: AsyncMock,
	) -> None:
		ws = _compaction_settings()
		thread = _thread(
			_sys("system"),
			_user("x" * 2500, "m1"),
			_user("y" * 2500, "m2"),
			_user("latest", "m3"),
		)

		async def blocking_summarize(
			messages: list[Message],
			start_message_id: TypeID | None,
			end_message_id: TypeID | None,
		):
			_ = (messages, start_message_id)
			summary = _mock_summary(
				end_message_id=str(end_message_id),
				content=f"inline summary through {end_message_id}",
			)
			return summary

		with (
			patch(PIPELINE_SETTINGS) as mock_settings,
			patch(PIPELINE_SUMMARY_SERVICE) as mock_svc,
		):
			mock_settings.ai.context_compaction = ws
			mock_svc.list_active_summaries = AsyncMock(return_value=[])
			result = await apply_context_compaction(
				thread,
				context_window=5_000,
				thread_id=_TID,
				session=mock_session,
				blocking_summarize=blocking_summarize,
			)

		conversation_texts = [
			message.text
			for message in result.thread.messages
			if isinstance(message, (SystemMessage, UserMessage))
		]
		assert any(
			"inline summary through" in (text or "") for text in conversation_texts
		)
		assert result.blocking_summary_count > 0

	@pytest.mark.asyncio()
	async def test_blocking_summary_skips_ready_summary_placeholders(
		self,
		mock_session: AsyncMock,
	) -> None:
		ws = _compaction_settings()
		ready_summary = _mock_summary(
			start_message_id="m1",
			end_message_id="m1",
			content="ready summary for first message",
		)
		thread = _thread(
			_sys("system"),
			_user("x" * 2500, "m1"),
			_user("y" * 2500, "m2"),
			_user("latest", "m3"),
		)
		captured_batches: list[list[Message]] = []

		async def blocking_summarize(
			messages: list[Message],
			start_message_id: TypeID | None,
			end_message_id: TypeID | None,
		):
			_ = start_message_id
			captured_batches.append(messages)
			return _mock_summary(
				end_message_id=str(end_message_id),
				content=f"inline summary through {end_message_id}",
			)

		with (
			patch(PIPELINE_SETTINGS) as mock_settings,
			patch(PIPELINE_SUMMARY_SERVICE) as mock_svc,
		):
			mock_settings.ai.context_compaction = ws
			mock_svc.list_active_summaries = AsyncMock(return_value=[ready_summary])
			result = await apply_context_compaction(
				thread,
				context_window=5_000,
				thread_id=_TID,
				session=mock_session,
				blocking_summarize=blocking_summarize,
			)

		assert captured_batches
		assert all(
			"ready summary for first message" not in (message.text or "")
			for message in captured_batches[0]
			if isinstance(message, UserMessage)
		)
		conversation_texts = [
			message.text
			for message in result.thread.messages
			if isinstance(message, (SystemMessage, UserMessage))
		]
		assert any(
			"ready summary for first message" in (text or "")
			for text in conversation_texts
		)
		assert any(
			"inline summary through" in (text or "") for text in conversation_texts
		)

	@pytest.mark.asyncio()
	async def test_blocking_summary_retries_after_t4_when_range_remains(
		self,
		mock_session: AsyncMock,
	) -> None:
		ws = _compaction_settings(
			summary_batch_min_tokens=1,
			summary_batch_max_tokens=8000,
		)
		thread = _thread(_sys("system"), _user("x" * 2500, "m1"))
		calls = 0

		async def blocking_summarize(
			messages: list[Message],
			start_message_id: TypeID | None,
			end_message_id: TypeID | None,
		):
			nonlocal calls
			_ = (messages, start_message_id)
			calls += 1
			if calls == 1:
				return None
			return _mock_summary(
				end_message_id=str(end_message_id),
				content="post-prune inline summary",
			)

		with (
			patch(PIPELINE_SETTINGS) as mock_settings,
			patch(PIPELINE_SUMMARY_SERVICE) as mock_svc,
		):
			mock_settings.ai.context_compaction = ws
			mock_svc.list_active_summaries = AsyncMock(return_value=[])
			result = await apply_context_compaction(
				thread,
				context_window=5_000,
				thread_id=_TID,
				session=mock_session,
				blocking_summarize=blocking_summarize,
			)

		assert calls == 2
		assert result.dropped_count == 0
		assert result.blocking_summary_count == 1
		assert any(
			"post-prune inline summary" in (message.text or "")
			for message in result.thread.messages
			if isinstance(message, (SystemMessage, UserMessage))
		)

	@pytest.mark.asyncio()
	async def test_blocking_summary_can_be_disabled(
		self,
		mock_session: AsyncMock,
	) -> None:
		ws = _compaction_settings(blocking_summarization_enabled=False)
		thread = _thread(
			_sys("system"),
			_user("x" * 2500, "m1"),
			_user("y" * 2500, "m2"),
			_user("latest", "m3"),
		)
		blocking_summarize = AsyncMock()

		with (
			patch(PIPELINE_SETTINGS) as mock_settings,
			patch(PIPELINE_SUMMARY_SERVICE) as mock_svc,
		):
			mock_settings.ai.context_compaction = ws
			mock_svc.list_active_summaries = AsyncMock(return_value=[])
			result = await apply_context_compaction(
				thread,
				context_window=5_000,
				thread_id=_TID,
				session=mock_session,
				blocking_summarize=blocking_summarize,
			)

		blocking_summarize.assert_not_awaited()
		assert result.blocking_summary_count == 0
		assert result.dropped_count > 0

	@pytest.mark.asyncio()
	async def test_sentinel_replaced_in_output(
		self,
		mock_session: AsyncMock,
	) -> None:
		ws = _compaction_settings()
		thread = _thread(
			_sys(f"prompt {SENTINEL_CHAT_WINDOW_INFO}"),
			_user("hi", "m1"),
		)

		with (
			patch(PIPELINE_SETTINGS) as mock_settings,
			patch(PIPELINE_SUMMARY_SERVICE) as mock_svc,
		):
			mock_settings.ai.context_compaction = ws
			mock_svc.list_active_summaries = AsyncMock(return_value=[])
			result = await apply_context_compaction(
				thread,
				context_window=128_000,
				thread_id=_TID,
				session=mock_session,
			)

		sys_msg = result.thread.messages[0]
		assert isinstance(sys_msg, SystemMessage)
		sys_text = sys_msg.text or ""
		assert SENTINEL_CHAT_WINDOW_INFO not in sys_text
		assert "context compaction info:" in sys_text

	@pytest.mark.asyncio()
	async def test_result_dataclass_fields(self, mock_session: AsyncMock) -> None:
		ws = _compaction_settings()
		thread = _thread(_sys("system"), _user("hi", "m1"))

		with (
			patch(PIPELINE_SETTINGS) as mock_settings,
			patch(PIPELINE_SUMMARY_SERVICE) as mock_svc,
		):
			mock_settings.ai.context_compaction = ws
			mock_svc.list_active_summaries = AsyncMock(return_value=[])
			result = await apply_context_compaction(
				thread,
				context_window=128_000,
				thread_id=_TID,
				session=mock_session,
			)

		assert isinstance(result, ContextCompactionResult)
		assert isinstance(result.total_tokens, int)
		assert isinstance(result.budget_tokens, int)
		assert result.total_tokens >= 0
		assert result.budget_tokens >= 0
