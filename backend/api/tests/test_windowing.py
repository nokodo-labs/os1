"""tests for context windowing logic."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.v1.service.chat.windowing import (
	WindowingResult,
	_build_summary_injection,
	_build_window_info,
	_find_summarized_cutoff,
	_get_message_id,
	_inject_summary_into_system,
	_replace_chat_window_sentinel,
	apply_context_windowing,
)
from api.v1.service.prompt_runtime import SENTINEL_CHAT_WINDOW_INFO
from nokodo_ai.messages import (
	AssistantMessage,
	Message,
	SystemMessage,
	TextContent,
	UserMessage,
)
from nokodo_ai.threads import Thread
from nokodo_ai.types.json import JSONObject
from nokodo_ai.utils.typeid import TypeID


# -- helpers --


def _sys(text: str) -> SystemMessage:
	return SystemMessage.from_text(text)


def _user(text: str, msg_id: str | None = None) -> UserMessage:
	meta: JSONObject | None = {"message_id": msg_id} if msg_id else None
	return UserMessage(
		content=[TextContent(text=text)],
		metadata=meta,
	)


def _assistant(text: str, msg_id: str | None = None) -> AssistantMessage:
	meta: JSONObject | None = {"message_id": msg_id} if msg_id else None
	return AssistantMessage(
		content=[TextContent(text=text)],
		metadata=meta,
	)


def _thread(*msgs: Message) -> Thread:
	return Thread(messages=list(msgs))


_TID = TypeID("th_123")


def _mock_summary(
	end_message_id: str | None = None,
	content: str = "summary content",
) -> MagicMock:
	s = MagicMock()
	s.end_message_id = end_message_id
	s.content = content
	return s


# -- _get_message_id --


class TestGetMessageId:
	def test_returns_id_from_metadata(self) -> None:
		msg = _user("hi", msg_id="msg_123")
		assert _get_message_id(msg) == "msg_123"

	def test_returns_none_when_no_metadata(self) -> None:
		msg = _user("hi")
		assert _get_message_id(msg) is None

	def test_returns_none_when_no_message_id_key(self) -> None:
		msg = UserMessage(
			content=[TextContent(text="hi")],
			metadata={"other": "val"},
		)
		assert _get_message_id(msg) is None


# -- _find_summarized_cutoff --


class TestFindSummarizedCutoff:
	def test_no_summaries_returns_zero(self) -> None:
		assert _find_summarized_cutoff([], ["a", "b", "c"]) == 0

	def test_finds_cutoff_at_end_id(self) -> None:
		s = _mock_summary(end_message_id="b")
		result = _find_summarized_cutoff([s], ["a", "b", "c", "d"])
		assert result == 2  # index 1 + 1

	def test_no_matching_ids(self) -> None:
		s = _mock_summary(end_message_id="z")
		result = _find_summarized_cutoff([s], ["a", "b", "c"])
		assert result == 0

	def test_multiple_summaries_takes_max(self) -> None:
		s1 = _mock_summary(end_message_id="b")
		s2 = _mock_summary(end_message_id="d")
		result = _find_summarized_cutoff([s1, s2], ["a", "b", "c", "d", "e"])
		assert result == 4

	def test_summary_with_no_end_id(self) -> None:
		s = _mock_summary(end_message_id=None)
		result = _find_summarized_cutoff([s], ["a", "b"])
		assert result == 0

	def test_none_ids_in_branch(self) -> None:
		s = _mock_summary(end_message_id="b")
		result = _find_summarized_cutoff([s], [None, "b", None])
		assert result == 2


# -- _build_summary_injection --


class TestBuildSummaryInjection:
	def test_empty_summaries(self) -> None:
		assert _build_summary_injection([]) == ""

	def test_single_summary(self) -> None:
		s = _mock_summary(content="users discussed login flow")
		result = _build_summary_injection([s])
		assert "conversation history summary" in result
		assert "users discussed login flow" in result

	def test_multiple_summaries_joined(self) -> None:
		s1 = _mock_summary(content="part one")
		s2 = _mock_summary(content="part two")
		result = _build_summary_injection([s1, s2])
		assert "part one" in result
		assert "part two" in result
		assert "---" in result

	def test_empty_content_filtered(self) -> None:
		s1 = _mock_summary(content="")
		s2 = _mock_summary(content="real content")
		result = _build_summary_injection([s1, s2])
		assert "real content" in result

	def test_all_empty_returns_empty(self) -> None:
		s1 = _mock_summary(content="")
		s2 = _mock_summary(content="")
		assert _build_summary_injection([s1, s2]) == ""


# -- _inject_summary_into_system --


class TestInjectSummaryIntoSystem:
	def test_no_text_returns_original(self) -> None:
		msgs: list[Message] = [_sys("you are helpful")]
		result = _inject_summary_into_system(msgs, "")
		assert isinstance(result[0], SystemMessage)
		assert result[0].text == "you are helpful"

	def test_appends_to_system_message(self) -> None:
		msgs: list[Message] = [_sys("you are helpful")]
		result = _inject_summary_into_system(msgs, "\n\nsummary here")
		assert isinstance(result[0], SystemMessage)
		assert result[0].text == "you are helpful\n\nsummary here"

	def test_creates_system_if_none(self) -> None:
		msgs: list[Message] = [_user("hi")]
		result = _inject_summary_into_system(msgs, "\n\nsummary here")
		assert isinstance(result[0], SystemMessage)
		assert "summary here" in (result[0].text or "")

	def test_does_not_mutate_original(self) -> None:
		original: list[Message] = [_sys("original")]
		_inject_summary_into_system(original, "\n\naddition")
		assert isinstance(original[0], SystemMessage)
		assert original[0].text == "original"


# -- _build_window_info --


class TestBuildWindowInfo:
	def test_basic_output(self) -> None:
		info = _build_window_info(
			summary_count=0,
			dropped_count=0,
			total_tokens=500,
			budget_tokens=1000,
			original_message_count=10,
			visible_message_count=10,
		)
		assert "[context window info:" in info
		assert "10 recent messages" in info

	def test_with_summaries(self) -> None:
		info = _build_window_info(
			summary_count=2,
			dropped_count=0,
			total_tokens=500,
			budget_tokens=1000,
			original_message_count=30,
			visible_message_count=10,
		)
		assert "2 summary/summaries" in info
		assert "20 earlier messages have been summarized" in info

	def test_with_drops(self) -> None:
		info = _build_window_info(
			summary_count=0,
			dropped_count=5,
			total_tokens=900,
			budget_tokens=1000,
			original_message_count=15,
			visible_message_count=10,
		)
		assert "5 messages were hard-truncated" in info

	def test_context_usage_percentage(self) -> None:
		info = _build_window_info(
			summary_count=0,
			dropped_count=0,
			total_tokens=750,
			budget_tokens=1000,
			original_message_count=10,
			visible_message_count=10,
		)
		assert "~75%" in info

	def test_zero_budget_no_percentage(self) -> None:
		info = _build_window_info(
			summary_count=0,
			dropped_count=0,
			total_tokens=100,
			budget_tokens=0,
			original_message_count=5,
			visible_message_count=5,
		)
		# should not crash on zero division
		assert "recent messages" in info


# -- _replace_chat_window_sentinel --


class TestReplaceChatWindowSentinel:
	def test_replaces_sentinel_in_system_message(self) -> None:
		msgs: list[Message] = [_sys(f"info: {SENTINEL_CHAT_WINDOW_INFO}")]
		result = _replace_chat_window_sentinel(msgs, "[test info]")
		assert isinstance(result[0], SystemMessage)
		assert result[0].text == "info: [test info]"

	def test_no_sentinel_unchanged(self) -> None:
		msgs: list[Message] = [_sys("no sentinel here")]
		result = _replace_chat_window_sentinel(msgs, "[test info]")
		assert isinstance(result[0], SystemMessage)
		assert result[0].text == "no sentinel here"

	def test_non_system_messages_unchanged(self) -> None:
		msgs: list[Message] = [_user("hello")]
		result = _replace_chat_window_sentinel(msgs, "[test info]")
		assert isinstance(result[0], UserMessage)
		assert result[0].text == "hello"

	def test_does_not_mutate_original(self) -> None:
		original: list[Message] = [_sys(f"info: {SENTINEL_CHAT_WINDOW_INFO}")]
		_replace_chat_window_sentinel(original, "[test info]")
		assert isinstance(original[0], SystemMessage)
		assert SENTINEL_CHAT_WINDOW_INFO in (original[0].text or "")


# -- apply_context_windowing --


def _windowing_settings(**overrides: bool | int | float) -> MagicMock:
	"""create a mock windowing settings with defaults."""
	defaults = {
		"enabled": True,
		"max_messages": 50,
		"trigger_ratio": 0.70,
		"hard_ratio": 0.90,
		"summary_batch_size": 20,
		"max_summaries_before_condense": 4,
		"tool_result_max_share": 0.25,
		"tool_result_hard_cap": 100_000,
		"response_headroom": 4096,
	}
	defaults.update(overrides)
	ws = MagicMock()
	for k, v in defaults.items():
		setattr(ws, k, v)
	return ws


@pytest.fixture()
def mock_session() -> AsyncMock:
	return AsyncMock()


class TestApplyContextWindowing:
	@pytest.mark.asyncio()
	async def test_disabled_returns_original(self, mock_session: AsyncMock) -> None:
		ws = _windowing_settings(enabled=False)
		thread = _thread(_sys("hello"), _user("hi", "m1"))
		with patch("api.v1.service.chat.windowing.app_settings") as mock_settings:
			mock_settings.ai.windowing = ws
			result = await apply_context_windowing(
				thread,
				context_window=128_000,
				thread_id=_TID,
				session=mock_session,
			)
		assert len(result.thread.messages) == 2
		assert not result.needs_summarization

	@pytest.mark.asyncio()
	async def test_disabled_clears_sentinel(self, mock_session: AsyncMock) -> None:
		ws = _windowing_settings(enabled=False)
		thread = _thread(
			_sys(f"prompt with {SENTINEL_CHAT_WINDOW_INFO}"),
			_user("hi", "m1"),
		)
		with patch("api.v1.service.chat.windowing.app_settings") as mock_settings:
			mock_settings.ai.windowing = ws
			result = await apply_context_windowing(
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
		ws = _windowing_settings()
		msgs: list[Message] = [
			_sys("system"),
			_user("hi", "m1"),
			_assistant("hello", "m2"),
		]
		thread = _thread(*msgs)

		with (
			patch("api.v1.service.chat.windowing.app_settings") as mock_settings,
			patch("api.v1.service.chat.windowing.summary_service") as mock_svc,
		):
			mock_settings.ai.windowing = ws
			mock_svc.list_active_summaries = AsyncMock(return_value=[])
			result = await apply_context_windowing(
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
	async def test_max_messages_cap(self, mock_session: AsyncMock) -> None:
		ws = _windowing_settings(max_messages=3)
		# 1 system + 5 user messages = 5 over max of 3
		msgs: list[Message] = [_sys("system")]
		for i in range(5):
			msgs.append(_user(f"msg {i}", f"m{i}"))
		thread = _thread(*msgs)

		with (
			patch("api.v1.service.chat.windowing.app_settings") as mock_settings,
			patch("api.v1.service.chat.windowing.summary_service") as mock_svc,
		):
			mock_settings.ai.windowing = ws
			mock_svc.list_active_summaries = AsyncMock(return_value=[])
			result = await apply_context_windowing(
				thread,
				context_window=128_000,
				thread_id=_TID,
				session=mock_session,
			)

		# system + 3 most recent conversation messages
		assert result.dropped_count == 2
		conversation_msgs = [
			m for m in result.thread.messages if not isinstance(m, SystemMessage)
		]
		assert len(conversation_msgs) == 3

	@pytest.mark.asyncio()
	async def test_hard_truncation(self, mock_session: AsyncMock) -> None:
		ws = _windowing_settings(hard_ratio=0.90, max_messages=100)
		# create many short messages that collectively exceed budget
		msgs: list[Message] = [_sys("system")]
		for i in range(40):
			msgs.append(_user(f"message content number {i} with some text", f"m{i}"))
		thread = _thread(*msgs)

		with (
			patch("api.v1.service.chat.windowing.app_settings") as mock_settings,
			patch("api.v1.service.chat.windowing.summary_service") as mock_svc,
		):
			mock_settings.ai.windowing = ws
			mock_svc.list_active_summaries = AsyncMock(return_value=[])
			# small context window to force hard truncation
			result = await apply_context_windowing(
				thread,
				context_window=200,
				thread_id=_TID,
				session=mock_session,
			)

		# some messages should have been dropped
		assert result.dropped_count > 0

	@pytest.mark.asyncio()
	async def test_trigger_signals_summarization(
		self,
		mock_session: AsyncMock,
	) -> None:
		# use a tiny context window so even modest content exceeds trigger
		ws = _windowing_settings(
			trigger_ratio=0.01,
			hard_ratio=0.99,
			max_messages=100,
		)
		msgs: list[Message] = [_sys("system")]
		# each message ~300 chars to build up enough token mass
		for i in range(10):
			msgs.append(_user(f"{'x' * 300} message {i}", f"m{i}"))
		thread = _thread(*msgs)

		with (
			patch("api.v1.service.chat.windowing.app_settings") as mock_settings,
			patch("api.v1.service.chat.windowing.summary_service") as mock_svc,
		):
			mock_settings.ai.windowing = ws
			mock_svc.list_active_summaries = AsyncMock(return_value=[])
			# context window large enough for positive budget but small
			# enough that trigger_ratio (0.01) is exceeded
			result = await apply_context_windowing(
				thread,
				context_window=10_000,
				thread_id=_TID,
				session=mock_session,
			)

		assert result.needs_summarization
		assert len(result.summarize_messages) > 0

	@pytest.mark.asyncio()
	async def test_summary_injection(self, mock_session: AsyncMock) -> None:
		ws = _windowing_settings()
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
			patch("api.v1.service.chat.windowing.app_settings") as mock_settings,
			patch("api.v1.service.chat.windowing.summary_service") as mock_svc,
		):
			mock_settings.ai.windowing = ws
			mock_svc.list_active_summaries = AsyncMock(return_value=[summary])
			result = await apply_context_windowing(
				thread,
				context_window=128_000,
				thread_id=_TID,
				session=mock_session,
			)

		sys_msg = result.thread.messages[0]
		assert isinstance(sys_msg, SystemMessage)
		sys_text = sys_msg.text or ""
		assert "user discussed project setup" in sys_text
		assert "conversation history summary" in sys_text
		# m1 and m2 should be excluded, m3 and m4 remain
		conversation_msgs = [
			m for m in result.thread.messages if not isinstance(m, SystemMessage)
		]
		assert len(conversation_msgs) == 2

	@pytest.mark.asyncio()
	async def test_dropped_notice_when_no_summaries(
		self,
		mock_session: AsyncMock,
	) -> None:
		ws = _windowing_settings(max_messages=2)
		msgs: list[Message] = [_sys("system")]
		for i in range(5):
			msgs.append(_user(f"msg {i}", f"m{i}"))
		thread = _thread(*msgs)

		with (
			patch("api.v1.service.chat.windowing.app_settings") as mock_settings,
			patch("api.v1.service.chat.windowing.summary_service") as mock_svc,
		):
			mock_settings.ai.windowing = ws
			mock_svc.list_active_summaries = AsyncMock(return_value=[])
			result = await apply_context_windowing(
				thread,
				context_window=128_000,
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
	async def test_sentinel_replaced_in_output(
		self,
		mock_session: AsyncMock,
	) -> None:
		ws = _windowing_settings()
		thread = _thread(
			_sys(f"prompt {SENTINEL_CHAT_WINDOW_INFO}"),
			_user("hi", "m1"),
		)

		with (
			patch("api.v1.service.chat.windowing.app_settings") as mock_settings,
			patch("api.v1.service.chat.windowing.summary_service") as mock_svc,
		):
			mock_settings.ai.windowing = ws
			mock_svc.list_active_summaries = AsyncMock(return_value=[])
			result = await apply_context_windowing(
				thread,
				context_window=128_000,
				thread_id=_TID,
				session=mock_session,
			)

		sys_msg = result.thread.messages[0]
		assert isinstance(sys_msg, SystemMessage)
		sys_text = sys_msg.text or ""
		assert SENTINEL_CHAT_WINDOW_INFO not in sys_text
		assert "context window info:" in sys_text

	@pytest.mark.asyncio()
	async def test_result_dataclass_fields(self, mock_session: AsyncMock) -> None:
		ws = _windowing_settings()
		thread = _thread(_sys("system"), _user("hi", "m1"))

		with (
			patch("api.v1.service.chat.windowing.app_settings") as mock_settings,
			patch("api.v1.service.chat.windowing.summary_service") as mock_svc,
		):
			mock_settings.ai.windowing = ws
			mock_svc.list_active_summaries = AsyncMock(return_value=[])
			result = await apply_context_windowing(
				thread,
				context_window=128_000,
				thread_id=_TID,
				session=mock_session,
			)

		assert isinstance(result, WindowingResult)
		assert isinstance(result.total_tokens, int)
		assert isinstance(result.budget_tokens, int)
		assert result.total_tokens >= 0
		assert result.budget_tokens >= 0
