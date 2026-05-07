"""tests for tool result truncation filter."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from api.v1.service.chat.filters.tool_result_truncation import (
	ToolResultTruncationFilter,
	_compute_char_limit,
	_truncate_text,
)
from nokodo_ai.context import AgentContext
from nokodo_ai.messages import (
	AssistantMessage,
	SystemMessage,
	TextContent,
	ToolCall,
	ToolMessage,
	UserMessage,
)
from nokodo_ai.threads import Thread


def _mock_app_ctx(context_window: int | None = 128_000) -> MagicMock:
	ctx = MagicMock()
	ctx.context_window = context_window
	return ctx


def _agent_context(thread: Thread) -> AgentContext:
	return AgentContext(thread=thread)


# -- _truncate_text --


class TestTruncateText:
	def test_short_text_unchanged(self) -> None:
		result = _truncate_text("hello", 100)
		assert result == "hello"

	def test_at_limit_unchanged(self) -> None:
		text = "x" * 100
		result = _truncate_text(text, 100)
		assert result == text

	def test_over_limit_truncated(self) -> None:
		text = "x" * 200
		result = _truncate_text(text, 100)
		assert len(result) <= 100 + 100  # truncated + notice overhead
		assert "[... truncated:" in result
		assert "200 chars total" in result

	def test_truncation_preserves_head(self) -> None:
		text = "HEADER_START " + "x" * 500
		result = _truncate_text(text, 200)
		assert result.startswith("HEADER_START ")

	def test_zero_limit(self) -> None:
		text = "hello world"
		result = _truncate_text(text, 0)
		# should still produce the notice even if no content fits
		assert "[... truncated:" in result


# -- _compute_char_limit --


class TestComputeCharLimit:
	def test_no_context_window_uses_hard_cap(self) -> None:
		limit = _compute_char_limit(None)
		# should return hard_cap when no context_window
		assert limit == 100_000  # default hard_cap

	def test_large_context_window_uses_hard_cap(self) -> None:
		# with a huge context window, budget-relative share exceeds hard cap
		limit = _compute_char_limit(2_000_000)
		assert limit == 100_000

	def test_small_context_window_uses_share(self) -> None:
		# with a small window, budget share should be smaller than hard cap
		limit = _compute_char_limit(10_000)
		assert limit < 100_000
		assert limit > 0

	def test_share_scales_with_context_window(self) -> None:
		small = _compute_char_limit(10_000)
		large = _compute_char_limit(50_000)
		assert large > small


# -- ToolResultTruncationFilter --


class TestToolResultTruncationFilter:
	@pytest.fixture()
	def filter_(self) -> ToolResultTruncationFilter:
		return ToolResultTruncationFilter()

	@pytest.fixture()
	def ctx(self) -> MagicMock:
		return _mock_app_ctx(128_000)

	@pytest.fixture()
	def ctx_small(self) -> MagicMock:
		return _mock_app_ctx(8_000)

	@pytest.fixture()
	def ctx_none(self) -> MagicMock:
		return _mock_app_ctx(None)

	@pytest.mark.asyncio()
	async def test_no_tool_messages_unchanged(
		self,
		filter_: ToolResultTruncationFilter,
		ctx: MagicMock,
	) -> None:
		thread = Thread(
			messages=[
				UserMessage(content=[TextContent(text="hello")]),
				AssistantMessage(content=[TextContent(text="hi")]),
			]
		)
		result = await filter_.process(thread, _agent_context(thread), ctx)
		assert result.messages[0] == thread.messages[0]
		assert result.messages[1] == thread.messages[1]

	@pytest.mark.asyncio()
	async def test_short_tool_result_unchanged(
		self,
		filter_: ToolResultTruncationFilter,
		ctx: MagicMock,
	) -> None:
		thread = Thread(
			messages=[
				ToolMessage(
					tool_call_id="tc_1",
					tool_output="short result",
				),
			]
		)
		result = await filter_.process(thread, _agent_context(thread), ctx)
		msg = result.messages[0]
		assert isinstance(msg, ToolMessage)
		assert msg.tool_output == "short result"

	@pytest.mark.asyncio()
	async def test_oversized_tool_result_truncated(
		self,
		filter_: ToolResultTruncationFilter,
		ctx: MagicMock,
	) -> None:
		big_output = "x" * 150_000  # exceeds 100K hard cap
		thread = Thread(
			messages=[
				ToolMessage(
					tool_call_id="tc_1",
					tool_output=big_output,
				),
			]
		)
		result = await filter_.process(thread, _agent_context(thread), ctx)
		msg = result.messages[0]
		assert isinstance(msg, ToolMessage)
		truncated = msg.tool_output
		assert len(truncated) < len(big_output)
		assert "[... truncated:" in truncated
		assert "150000 chars total" in truncated

	@pytest.mark.asyncio()
	async def test_small_window_truncates_sooner(
		self,
		filter_: ToolResultTruncationFilter,
		ctx_small: MagicMock,
	) -> None:
		# with 8K context window, budget share is much smaller
		limit = _compute_char_limit(8_000)
		output = "x" * (limit + 1000)
		thread = Thread(
			messages=[
				ToolMessage(
					tool_call_id="tc_1",
					tool_output=output,
				),
			]
		)
		result = await filter_.process(thread, _agent_context(thread), ctx_small)
		msg = result.messages[0]
		assert isinstance(msg, ToolMessage)
		truncated = msg.tool_output
		assert "[... truncated:" in truncated

	@pytest.mark.asyncio()
	async def test_multiple_tool_messages(
		self,
		filter_: ToolResultTruncationFilter,
		ctx: MagicMock,
	) -> None:
		thread = Thread(
			messages=[
				UserMessage(content=[TextContent(text="do stuff")]),
				AssistantMessage(
					content=[TextContent(text="calling tools")],
					tool_calls=[
						ToolCall(id="tc_1", name="tool1", arguments={}),
						ToolCall(id="tc_2", name="tool2", arguments={}),
					],
				),
				ToolMessage(tool_call_id="tc_1", tool_output="x" * 150_000),
				ToolMessage(tool_call_id="tc_2", tool_output="small result"),
			]
		)
		result = await filter_.process(thread, _agent_context(thread), ctx)
		# first tool message should be truncated
		msg2 = result.messages[2]
		assert isinstance(msg2, ToolMessage)
		assert "[... truncated:" in msg2.tool_output
		# second tool message should be unchanged
		msg3 = result.messages[3]
		assert isinstance(msg3, ToolMessage)
		assert msg3.tool_output == "small result"

	@pytest.mark.asyncio()
	async def test_system_messages_not_affected(
		self,
		filter_: ToolResultTruncationFilter,
		ctx: MagicMock,
	) -> None:
		long_system = "x" * 150_000
		thread = Thread(
			messages=[
				SystemMessage(content=[TextContent(text=long_system)]),
			]
		)
		result = await filter_.process(thread, _agent_context(thread), ctx)
		msg = result.messages[0]
		assert isinstance(msg, SystemMessage)
		assert isinstance(msg.content[0], TextContent)
		assert msg.content[0].text == long_system

	@pytest.mark.asyncio()
	async def test_empty_tool_output_unchanged(
		self,
		filter_: ToolResultTruncationFilter,
		ctx: MagicMock,
	) -> None:
		thread = Thread(
			messages=[
				ToolMessage(tool_call_id="tc_1", tool_output=""),
			]
		)
		result = await filter_.process(thread, _agent_context(thread), ctx)
		msg = result.messages[0]
		assert isinstance(msg, ToolMessage)
		assert msg.tool_output == ""

	@pytest.mark.asyncio()
	async def test_no_window_applies_hard_cap(
		self,
		filter_: ToolResultTruncationFilter,
		ctx_none: MagicMock,
	) -> None:
		# with no context window, only hard cap applies
		output = "x" * 150_000
		thread = Thread(
			messages=[
				ToolMessage(tool_call_id="tc_1", tool_output=output),
			]
		)
		result = await filter_.process(thread, _agent_context(thread), ctx_none)
		msg = result.messages[0]
		assert isinstance(msg, ToolMessage)
		assert "[... truncated:" in msg.tool_output

	@pytest.mark.asyncio()
	async def test_returns_same_thread_when_no_changes(
		self,
		filter_: ToolResultTruncationFilter,
		ctx: MagicMock,
	) -> None:
		thread = Thread(
			messages=[
				UserMessage(content=[TextContent(text="hi")]),
				ToolMessage(tool_call_id="tc_1", tool_output="ok"),
			]
		)
		result = await filter_.process(thread, _agent_context(thread), ctx)
		assert result is thread
