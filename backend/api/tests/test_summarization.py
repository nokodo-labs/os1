"""tests for context summarization module."""

from __future__ import annotations

import contextlib
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from api.v1.service.chat.summarization import (
	_format_transcript,
	_placeholder_summary,
	condense_summaries,
	summarize_messages,
)
from nokodo_ai.messages import (
	AssistantMessage,
	Message,
	SystemMessage,
	TextContent,
	ToolMessage,
	UserMessage,
)
from nokodo_ai.utils.typeid import TypeID


_TID = TypeID("th_123")
_M1 = TypeID("m1")
_M2 = TypeID("m2")


# -- helpers --


def _user(text: str) -> UserMessage:
	return UserMessage.from_text(text)


def _assistant(text: str) -> AssistantMessage:
	return AssistantMessage(content=[TextContent(text=text)])


def _sys(text: str) -> SystemMessage:
	return SystemMessage.from_text(text)


def _tool(output: str, call_id: str = "call_1") -> ToolMessage:
	return ToolMessage(tool_call_id=call_id, tool_output=output)


def _mock_summary(
	id_: str = "tsum_1",
	content: str = "summary content",
	message_count: int = 5,
	start_message_id: str | None = None,
	end_message_id: str | None = None,
) -> MagicMock:
	s = MagicMock()
	s.id = id_
	s.content = content
	s.message_count = message_count
	s.start_message_id = start_message_id
	s.end_message_id = end_message_id
	return s


# -- _format_transcript --


class TestFormatTranscript:
	def test_formats_messages(self) -> None:
		msgs: list[Message] = [_user("hello"), _assistant("hi there")]
		result = _format_transcript(msgs)
		assert "[user]: hello" in result
		assert "[assistant]: hi there" in result

	def test_truncates_long_messages(self) -> None:
		long_text = "x" * 5000
		msgs = [_user(long_text)]
		result = _format_transcript(msgs)
		# each message is capped at 2000 chars
		assert len(result) < 5000

	def test_empty_messages(self) -> None:
		result = _format_transcript([])
		assert result == ""

	def test_system_messages_included(self) -> None:
		msgs: list[Message] = [_sys("instructions"), _user("hello")]
		result = _format_transcript(msgs)
		assert "[system]: instructions" in result

	def test_tool_messages_included(self) -> None:
		msgs = [_tool("search result data", "tc_1")]
		result = _format_transcript(msgs)
		assert "[tool]: search result data" in result

	def test_tool_message_truncates_output(self) -> None:
		msgs = [_tool("x" * 5000, "tc_1")]
		result = _format_transcript(msgs)
		assert len(result) < 5000

	def test_tool_message_empty_output(self) -> None:
		msgs = [_tool("", "tc_1")]
		result = _format_transcript(msgs)
		# empty output means no line added
		assert result == ""

	def test_unknown_message_type_skipped(self) -> None:
		"""messages of unrecognized type produce empty text and are skipped."""
		fake = MagicMock()
		fake.role = "custom"
		# force isinstance checks to fail by using a raw MagicMock
		msgs = [fake]
		result = _format_transcript(msgs)  # type: ignore[arg-type]
		assert result == ""


# -- _placeholder_summary --


class TestPlaceholderSummary:
	def test_basic_placeholder(self) -> None:
		msgs = [_user("a"), _user("b"), _user("c")]
		result = _placeholder_summary(msgs)
		assert "3 messages" in result
		assert "summary unavailable" in result

	def test_with_timestamps(self) -> None:
		from datetime import datetime

		msgs = [_user("a")]
		start = datetime(2025, 1, 1, 12, 0)
		end = datetime(2025, 1, 1, 13, 0)
		result = _placeholder_summary(msgs, start_time=start, end_time=end)
		assert "1 messages" in result
		assert "2025-01-01" in result


# -- summarize_messages --


class TestSummarizeMessages:
	@pytest.mark.asyncio()
	async def test_successful_summarization(self) -> None:
		mock_model = AsyncMock()
		mock_response = MagicMock()
		mock_response.text = "the user asked about login flow and setup"
		mock_model.generate = AsyncMock(return_value=mock_response)

		mock_summary = MagicMock()
		mock_summary.id = "tsum_new"

		with (
			patch(
				"api.v1.service.chat.summarization.resolve_task_chat_model",
				AsyncMock(return_value=mock_model),
			),
			patch("api.v1.service.chat.summarization.summary_service") as mock_svc,
		):
			mock_svc.create_summary = AsyncMock(return_value=mock_summary)
			session = AsyncMock()

			result = await summarize_messages(
				thread_id=_TID,
				messages=[_user("hello"), _assistant("hi")],
				start_message_id=_M1,
				end_message_id=_M2,
				session=session,
			)

		assert str(result) == "tsum_new"
		mock_svc.create_summary.assert_called_once()
		call_kwargs = mock_svc.create_summary.call_args.kwargs
		assert call_kwargs["content"] == "the user asked about login flow and setup"

	@pytest.mark.asyncio()
	async def test_fallback_on_llm_failure(self) -> None:
		mock_summary = MagicMock()
		mock_summary.id = "tsum_fallback"

		with (
			patch(
				"api.v1.service.chat.summarization.resolve_task_chat_model",
				AsyncMock(side_effect=RuntimeError("model unavailable")),
			),
			patch("api.v1.service.chat.summarization.summary_service") as mock_svc,
		):
			mock_svc.create_summary = AsyncMock(return_value=mock_summary)
			session = AsyncMock()

			result = await summarize_messages(
				thread_id=_TID,
				messages=[_user("hello"), _assistant("hi")],
				session=session,
			)

		assert str(result) == "tsum_fallback"
		call_kwargs = mock_svc.create_summary.call_args.kwargs
		assert "summary unavailable" in call_kwargs["content"]

	@pytest.mark.asyncio()
	async def test_empty_llm_response_uses_placeholder(self) -> None:
		mock_model = AsyncMock()
		mock_response = MagicMock()
		mock_response.text = ""
		mock_model.generate = AsyncMock(return_value=mock_response)

		mock_summary = MagicMock()
		mock_summary.id = "tsum_empty"

		with (
			patch(
				"api.v1.service.chat.summarization.resolve_task_chat_model",
				AsyncMock(return_value=mock_model),
			),
			patch("api.v1.service.chat.summarization.summary_service") as mock_svc,
		):
			mock_svc.create_summary = AsyncMock(return_value=mock_summary)
			session = AsyncMock()

			await summarize_messages(
				thread_id=_TID,
				messages=[_user("hello")],
				session=session,
			)

		call_kwargs = mock_svc.create_summary.call_args.kwargs
		assert "summary unavailable" in call_kwargs["content"]

	@pytest.mark.asyncio()
	async def test_creates_session_when_none(self) -> None:
		"""when session is None, creates one via async_session_local."""
		mock_model = AsyncMock()
		mock_response = MagicMock()
		mock_response.text = "summary text"
		mock_model.generate = AsyncMock(return_value=mock_response)

		mock_summary = MagicMock()
		mock_summary.id = "tsum_auto"

		mock_session = AsyncMock()

		@contextlib.asynccontextmanager
		async def _fake_scope(
			session: AsyncSession | None = None,
		) -> AsyncGenerator[AsyncSession]:
			yield mock_session

		with (
			patch(
				"api.v1.service.chat.summarization.resolve_task_chat_model",
				AsyncMock(return_value=mock_model),
			),
			patch("api.v1.service.chat.summarization.summary_service") as mock_svc,
			patch("api.v1.service.chat.summarization.session_scope", _fake_scope),
		):
			mock_svc.create_summary = AsyncMock(return_value=mock_summary)

			result = await summarize_messages(
				thread_id=_TID,
				messages=[_user("hello")],
			)

		assert str(result) == "tsum_auto"


class TestCondenseSummaries:
	@pytest.mark.asyncio()
	async def test_skips_when_fewer_than_two(self) -> None:
		with patch("api.v1.service.chat.summarization.summary_service") as mock_svc:
			mock_svc.list_active_summaries = AsyncMock(
				return_value=[_mock_summary()],
			)
			session = AsyncMock()

			result = await condense_summaries(
				thread_id=_TID,
				session=session,
			)

		assert result is None

	@pytest.mark.asyncio()
	async def test_successful_condensation(self) -> None:
		existing = [
			_mock_summary(id_="tsum_1", content="first part"),
			_mock_summary(id_="tsum_2", content="second part"),
		]
		condensed_mock = MagicMock()
		condensed_mock.id = "tsum_condensed"

		mock_model = AsyncMock()
		mock_response = MagicMock()
		mock_response.text = "merged summary of both parts"
		mock_model.generate = AsyncMock(return_value=mock_response)

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

			result = await condense_summaries(
				thread_id=_TID,
				session=session,
			)

		assert str(result) == "tsum_condensed"
		mock_svc.supersede_summaries.assert_called_once()

	@pytest.mark.asyncio()
	async def test_fallback_on_llm_failure(self) -> None:
		existing = [
			_mock_summary(id_="tsum_1", content="part one"),
			_mock_summary(id_="tsum_2", content="part two"),
		]
		condensed_mock = MagicMock()
		condensed_mock.id = "tsum_fallback"

		with (
			patch(
				"api.v1.service.chat.summarization.resolve_task_chat_model",
				AsyncMock(side_effect=RuntimeError("no model")),
			),
			patch("api.v1.service.chat.summarization.summary_service") as mock_svc,
		):
			mock_svc.list_active_summaries = AsyncMock(return_value=existing)
			mock_svc.create_summary = AsyncMock(return_value=condensed_mock)
			mock_svc.supersede_summaries = AsyncMock()
			session = AsyncMock()

			await condense_summaries(
				thread_id=_TID,
				session=session,
			)

		# on failure, uses concatenated raw summaries
		call_kwargs = mock_svc.create_summary.call_args.kwargs
		assert "part one" in call_kwargs["content"]
		assert "part two" in call_kwargs["content"]

	@pytest.mark.asyncio()
	async def test_empty_llm_response_uses_concatenation(self) -> None:
		"""when LLM returns empty text during condensation, fall back to raw concat."""
		existing = [
			_mock_summary(id_="tsum_1", content="alpha summary"),
			_mock_summary(id_="tsum_2", content="beta summary"),
		]
		condensed_mock = MagicMock()
		condensed_mock.id = "tsum_empty"

		mock_model = AsyncMock()
		mock_response = MagicMock()
		mock_response.text = ""
		mock_model.generate = AsyncMock(return_value=mock_response)

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

			result = await condense_summaries(
				thread_id=_TID,
				session=session,
			)

		assert str(result) == "tsum_empty"
		call_kwargs = mock_svc.create_summary.call_args.kwargs
		# fallback content should have the raw concatenation
		assert "alpha summary" in call_kwargs["content"]
		assert "beta summary" in call_kwargs["content"]

	@pytest.mark.asyncio()
	async def test_creates_session_when_none(self) -> None:
		"""when session is None, creates one via async_session_local."""
		existing = [
			_mock_summary(id_="tsum_1", content="part a"),
			_mock_summary(id_="tsum_2", content="part b"),
		]
		condensed_mock = MagicMock()
		condensed_mock.id = "tsum_auto_session"

		mock_model = AsyncMock()
		mock_response = MagicMock()
		mock_response.text = "condensed from auto session"
		mock_model.generate = AsyncMock(return_value=mock_response)

		mock_session = AsyncMock()

		@contextlib.asynccontextmanager
		async def _fake_scope(
			session: AsyncSession | None = None,
		) -> AsyncGenerator[AsyncSession]:
			yield mock_session

		with (
			patch(
				"api.v1.service.chat.summarization.resolve_task_chat_model",
				AsyncMock(return_value=mock_model),
			),
			patch("api.v1.service.chat.summarization.summary_service") as mock_svc,
			patch("api.v1.service.chat.summarization.session_scope", _fake_scope),
		):
			mock_svc.list_active_summaries = AsyncMock(return_value=existing)
			mock_svc.create_summary = AsyncMock(return_value=condensed_mock)
			mock_svc.supersede_summaries = AsyncMock()

			result = await condense_summaries(thread_id=_TID)

		assert str(result) == "tsum_auto_session"
