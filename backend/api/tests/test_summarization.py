"""tests for context summarization module."""

from __future__ import annotations

import contextlib
from collections.abc import AsyncGenerator
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.thread_summary import SummaryPurpose
from api.v1.service.chat.context_compaction.summarization import (
	SUMMARY_COVERED_RAW_IDS_METADATA_KEY,
	SUMMARY_MESSAGE_METADATA_KEY,
	SUMMARY_PREDECESSOR_IDS_METADATA_KEY,
	SummaryRangeStaleError,
	_format_transcript,
	_placeholder_summary,
	condense_summaries,
	summarize_messages,
	summarize_thread_message_range,
)
from nokodo_ai.messages import (
	AssistantMessage,
	Message,
	SystemMessage,
	TextContent,
	ToolCall,
	ToolMessage,
	UserMessage,
)
from nokodo_ai.utils.typeid import TypeID


_TID = TypeID("th_123")
_M1 = TypeID("m1")
_M2 = TypeID("m2")
_TSUM_1 = TypeID("tsum_01h5fskfsk4fpeqwnsyz5hj55t")
_TSUM_2 = TypeID("tsum_01h5fskfsk4fpeqwnsyz5hj55v")
_TSUM_OLD = TypeID("tsum_01h5fskfsk4fpeqwnsyz5hj55w")
_TSUM_NEW = TypeID("tsum_01h5fskfsk4fpeqwnsyz5hj55x")
_TSUM_FALLBACK = TypeID("tsum_01h5fskfsk4fpeqwnsyz5hj55y")
_TSUM_EMPTY = TypeID("tsum_01h5fskfsk4fpeqwnsyz5hj55z")
_TSUM_AUTO = TypeID("tsum_01h5fskfsk4fpeqwnsyz5hj560")
_TSUM_CONDENSED = TypeID("tsum_01h5fskfsk4fpeqwnsyz5hj561")


# -- helpers --


def _user(text: str, metadata: dict[str, object] | None = None) -> UserMessage:
	return UserMessage.from_text(text).model_copy(update={"metadata": metadata})


def _assistant(text: str) -> AssistantMessage:
	return AssistantMessage(content=[TextContent(text=text)])


def _sys(text: str) -> SystemMessage:
	return SystemMessage.from_text(text)


def _tool(output: str, call_id: str = "call_1") -> ToolMessage:
	return ToolMessage(tool_call_id=call_id, tool_output=output)


def _long_text(label: str) -> str:
	return f"{label}: " + ("specific chat detail " * 140)


def _compactable_messages() -> list[Message]:
	return [_user(_long_text("user")), _assistant(_long_text("assistant"))]


def _mock_summary(
	id_: TypeID = _TSUM_1,
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

	def test_unlimited_message_length_when_limit_is_none(self) -> None:
		long_text = "x" * 5000
		mock_settings = SimpleNamespace(
			ai=SimpleNamespace(
				context_compaction=SimpleNamespace(
					summarization_max_chars_per_message=None,
				),
			),
		)
		with patch(
			"api.v1.service.chat.context_compaction.summarization.settings",
			mock_settings,
		):
			result = _format_transcript([_user(long_text)])

		assert long_text in result

	def test_empty_messages(self) -> None:
		result = _format_transcript([])
		assert result == ""

	def test_system_messages_included(self) -> None:
		msgs: list[Message] = [_sys("instructions"), _user("hello")]
		result = _format_transcript(msgs)
		assert "[system]: instructions" in result

	def test_assistant_tool_calls_include_name_and_arguments(self) -> None:
		message = AssistantMessage(
			content=[],
			tool_calls=[
				ToolCall(
					id="call_1",
					name="web_search",
					arguments={"query": "release plan"},
				)
			],
		)
		result = _format_transcript([message])
		assert "tool_call id=call_1 name=web_search" in result
		assert '"query":"release plan"' in result

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
		messages = _compactable_messages()
		mock_model = AsyncMock()
		mock_response = MagicMock()
		mock_response.json_content = {
			"summary": "the user asked about login flow and setup"
		}
		mock_model.generate = AsyncMock(return_value=mock_response)

		mock_summary = MagicMock()
		mock_summary.id = _TSUM_NEW

		with (
			patch(
				"api.v1.service.chat.context_compaction.summarization.resolve_task_chat_model",
				AsyncMock(return_value=mock_model),
			),
			patch(
				"api.v1.service.chat.context_compaction.summarization.summary_service"
			) as mock_svc,
		):
			mock_svc.create_summary = AsyncMock(return_value=mock_summary)
			session = AsyncMock()

			result = await summarize_messages(
				thread_id=_TID,
				messages=messages,
				start_message_id=_M1,
				end_message_id=_M2,
				session=session,
			)

		assert result == _TSUM_NEW
		mock_svc.create_summary.assert_called_once()
		call_kwargs = mock_svc.create_summary.call_args.kwargs
		assert call_kwargs["purpose"] == SummaryPurpose.AGENT_CONTEXT
		assert call_kwargs["content"] == "the user asked about login flow and setup"
		schema = mock_model.generate.call_args.kwargs["params"]["response_model"]
		assert schema["properties"]["summary"]["maxLength"] < len(
			_format_transcript(messages)
		)

	@pytest.mark.asyncio()
	async def test_fallback_on_llm_failure(self) -> None:
		mock_summary = MagicMock()
		mock_summary.id = _TSUM_FALLBACK

		with (
			patch(
				"api.v1.service.chat.context_compaction.summarization.resolve_task_chat_model",
				AsyncMock(side_effect=RuntimeError("model unavailable")),
			),
			patch(
				"api.v1.service.chat.context_compaction.summarization.summary_service"
			) as mock_svc,
		):
			mock_svc.create_summary = AsyncMock(return_value=mock_summary)
			session = AsyncMock()

			result = await summarize_messages(
				thread_id=_TID,
				messages=_compactable_messages(),
				session=session,
			)

		assert result == _TSUM_FALLBACK
		call_kwargs = mock_svc.create_summary.call_args.kwargs
		assert "summary unavailable" in call_kwargs["content"]

	@pytest.mark.asyncio()
	async def test_rejects_batch_too_small_to_save_tokens(self) -> None:
		with pytest.raises(ValueError, match="too small"):
			await summarize_messages(
				thread_id=_TID,
				messages=[_user("tiny")],
				session=AsyncMock(),
			)

	@pytest.mark.asyncio()
	async def test_overlong_structured_output_uses_bounded_placeholder(self) -> None:
		mock_model = AsyncMock()
		mock_response = MagicMock()
		mock_response.json_content = {"summary": "x" * 20_000}
		mock_model.generate = AsyncMock(return_value=mock_response)

		mock_summary = MagicMock()
		mock_summary.id = _TSUM_FALLBACK

		with (
			patch(
				"api.v1.service.chat.context_compaction.summarization.resolve_task_chat_model",
				AsyncMock(return_value=mock_model),
			),
			patch(
				"api.v1.service.chat.context_compaction.summarization.summary_service"
			) as mock_svc,
		):
			mock_svc.create_summary = AsyncMock(return_value=mock_summary)
			await summarize_messages(
				thread_id=_TID,
				messages=_compactable_messages(),
				session=AsyncMock(),
			)

		call_kwargs = mock_svc.create_summary.call_args.kwargs
		assert call_kwargs["content"].startswith("[2 messages")
		assert len(call_kwargs["content"]) < 20_000

	@pytest.mark.asyncio()
	async def test_stores_coverage_and_lineage_metadata(self) -> None:
		mock_model = AsyncMock()
		mock_response = MagicMock()
		mock_response.json_content = {"summary": "summary over mixed bundle"}
		mock_model.generate = AsyncMock(return_value=mock_response)

		mock_summary = MagicMock()
		mock_summary.id = _TSUM_NEW
		mock_summary.metadata_ = {
			SUMMARY_PREDECESSOR_IDS_METADATA_KEY: [str(_TSUM_OLD)],
		}

		with (
			patch(
				"api.v1.service.chat.context_compaction.summarization.resolve_task_chat_model",
				AsyncMock(return_value=mock_model),
			),
			patch(
				"api.v1.service.chat.context_compaction.summarization.summary_service"
			) as mock_svc,
		):
			mock_svc.create_summary = AsyncMock(return_value=mock_summary)
			mock_svc.supersede_summaries = AsyncMock()
			session = AsyncMock()

			result = await summarize_messages(
				thread_id=_TID,
				messages=[
					_user(
						_long_text("prior summary"),
						{SUMMARY_MESSAGE_METADATA_KEY: str(_TSUM_OLD)},
					),
					_user(_long_text("new raw"), {"_message_id": "m2"}),
				],
				start_message_id=_M1,
				end_message_id=_M2,
				session=session,
			)

		assert result == _TSUM_NEW
		call_kwargs = mock_svc.create_summary.call_args.kwargs
		metadata = call_kwargs["metadata"]
		assert metadata[SUMMARY_COVERED_RAW_IDS_METADATA_KEY] == ["m2"]
		assert metadata[SUMMARY_PREDECESSOR_IDS_METADATA_KEY] == [str(_TSUM_OLD)]
		mock_svc.supersede_summaries.assert_awaited_once_with(
			[_TSUM_OLD],
			_TSUM_NEW,
			session,
		)

	@pytest.mark.asyncio()
	async def test_thread_range_rejects_stale_branch_head(self) -> None:
		session = AsyncMock()
		session.get = AsyncMock(
			return_value=SimpleNamespace(current_message_id="m_other")
		)

		with pytest.raises(SummaryRangeStaleError):
			await summarize_thread_message_range(
				thread_id=_TID,
				start_message_id=_M1,
				end_message_id=_M2,
				branch_head_message_id=_M2,
				session=session,
			)

	@pytest.mark.asyncio()
	async def test_empty_llm_response_uses_placeholder(self) -> None:
		mock_model = AsyncMock()
		mock_response = MagicMock()
		mock_response.json_content = {"summary": ""}
		mock_model.generate = AsyncMock(return_value=mock_response)

		mock_summary = MagicMock()
		mock_summary.id = _TSUM_EMPTY

		with (
			patch(
				"api.v1.service.chat.context_compaction.summarization.resolve_task_chat_model",
				AsyncMock(return_value=mock_model),
			),
			patch(
				"api.v1.service.chat.context_compaction.summarization.summary_service"
			) as mock_svc,
		):
			mock_svc.create_summary = AsyncMock(return_value=mock_summary)
			session = AsyncMock()

			await summarize_messages(
				thread_id=_TID,
				messages=_compactable_messages(),
				session=session,
			)

		call_kwargs = mock_svc.create_summary.call_args.kwargs
		assert "summary unavailable" in call_kwargs["content"]

	@pytest.mark.asyncio()
	async def test_creates_session_when_none(self) -> None:
		"""when session is None, creates one via async_session_local."""
		mock_model = AsyncMock()
		mock_response = MagicMock()
		mock_response.json_content = {"summary": "summary text"}
		mock_model.generate = AsyncMock(return_value=mock_response)

		mock_summary = MagicMock()
		mock_summary.id = _TSUM_AUTO

		mock_session = AsyncMock()

		@contextlib.asynccontextmanager
		async def _fake_scope(
			session: AsyncSession | None = None,
		) -> AsyncGenerator[AsyncSession]:
			yield mock_session

		with (
			patch(
				"api.v1.service.chat.context_compaction.summarization.resolve_task_chat_model",
				AsyncMock(return_value=mock_model),
			),
			patch(
				"api.v1.service.chat.context_compaction.summarization.summary_service"
			) as mock_svc,
			patch(
				"api.v1.service.chat.context_compaction.summarization.session_scope",
				_fake_scope,
			),
		):
			mock_svc.create_summary = AsyncMock(return_value=mock_summary)

			result = await summarize_messages(
				thread_id=_TID,
				messages=_compactable_messages(),
			)

		assert result == _TSUM_AUTO


class TestCondenseSummaries:
	@pytest.mark.asyncio()
	async def test_skips_when_fewer_than_two(self) -> None:
		with patch(
			"api.v1.service.chat.context_compaction.summarization.summary_service"
		) as mock_svc:
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
			_mock_summary(id_=_TSUM_1, content="first part"),
			_mock_summary(id_=_TSUM_2, content="second part"),
		]
		condensed_mock = MagicMock()
		condensed_mock.id = _TSUM_CONDENSED

		mock_model = AsyncMock()
		mock_response = MagicMock()
		mock_response.json_content = {"summary": "merged summary of both parts"}
		mock_model.generate = AsyncMock(return_value=mock_response)

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

			result = await condense_summaries(
				thread_id=_TID,
				session=session,
			)

		assert result == _TSUM_CONDENSED
		mock_svc.list_active_summaries.assert_called_once_with(
			_TID,
			session,
			purpose=SummaryPurpose.AGENT_CONTEXT,
		)
		call_kwargs = mock_svc.create_summary.call_args.kwargs
		assert call_kwargs["purpose"] == SummaryPurpose.AGENT_CONTEXT
		mock_svc.supersede_summaries.assert_called_once()

	@pytest.mark.asyncio()
	async def test_fallback_on_llm_failure(self) -> None:
		existing = [
			_mock_summary(id_=_TSUM_1, content="part one"),
			_mock_summary(id_=_TSUM_2, content="part two extra"),
		]
		condensed_mock = MagicMock()
		condensed_mock.id = _TSUM_FALLBACK

		with (
			patch(
				"api.v1.service.chat.context_compaction.summarization.resolve_task_chat_model",
				AsyncMock(side_effect=RuntimeError("no model")),
			),
			patch(
				"api.v1.service.chat.context_compaction.summarization.summary_service"
			) as mock_svc,
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
			_mock_summary(id_=_TSUM_1, content="alpha summary"),
			_mock_summary(id_=_TSUM_2, content="beta summary extra"),
		]
		condensed_mock = MagicMock()
		condensed_mock.id = _TSUM_EMPTY

		mock_model = AsyncMock()
		mock_response = MagicMock()
		mock_response.json_content = {"summary": ""}
		mock_model.generate = AsyncMock(return_value=mock_response)

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

			result = await condense_summaries(
				thread_id=_TID,
				session=session,
			)

		assert result == _TSUM_EMPTY
		call_kwargs = mock_svc.create_summary.call_args.kwargs
		# fallback content should have the raw concatenation
		assert "alpha summary" in call_kwargs["content"]
		assert "beta summary" in call_kwargs["content"]

	@pytest.mark.asyncio()
	async def test_creates_session_when_none(self) -> None:
		"""when session is None, creates one via async_session_local."""
		existing = [
			_mock_summary(id_=_TSUM_1, content="part a"),
			_mock_summary(id_=_TSUM_2, content="part b"),
		]
		condensed_mock = MagicMock()
		condensed_mock.id = _TSUM_AUTO

		mock_model = AsyncMock()
		mock_response = MagicMock()
		mock_response.json_content = {"summary": "condensed from auto session"}
		mock_model.generate = AsyncMock(return_value=mock_response)

		mock_session = AsyncMock()

		@contextlib.asynccontextmanager
		async def _fake_scope(
			session: AsyncSession | None = None,
		) -> AsyncGenerator[AsyncSession]:
			yield mock_session

		with (
			patch(
				"api.v1.service.chat.context_compaction.summarization.resolve_task_chat_model",
				AsyncMock(return_value=mock_model),
			),
			patch(
				"api.v1.service.chat.context_compaction.summarization.summary_service"
			) as mock_svc,
			patch(
				"api.v1.service.chat.context_compaction.summarization.session_scope",
				_fake_scope,
			),
		):
			mock_svc.list_active_summaries = AsyncMock(return_value=existing)
			mock_svc.create_summary = AsyncMock(return_value=condensed_mock)
			mock_svc.supersede_summaries = AsyncMock()

			result = await condense_summaries(thread_id=_TID)

		assert result == _TSUM_AUTO
