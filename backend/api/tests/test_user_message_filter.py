"""tests for UserMessageFilter (timestamp + speaker decoration).

these cover the timestamp behavior with no app_context (so speaker labeling is
inactive). speaker labeling is exercised end-to-end via the messages flow.
"""

from __future__ import annotations

import pytest

from api.v1.service.chat.filters.user_message import UserMessageFilter
from nokodo_ai.agents import AgentIterationState
from nokodo_ai.chat_models import ChatModel
from nokodo_ai.context import AgentContext
from nokodo_ai.messages import (
	AssistantMessage,
	ImageContent,
	TextContent,
	UserMessage,
)
from nokodo_ai.threads import Thread


def _ctx(thread: Thread) -> AgentContext:
	_ = thread
	return AgentContext(model=ChatModel.model_construct(model_name="test"))


def _user(text: str, created_at: str | None = None) -> UserMessage:
	meta = {}
	if created_at is not None:
		meta["_created_at"] = created_at
	return UserMessage.from_text(text).model_copy(update={"metadata": meta})


async def _process(thread: Thread) -> Thread:
	state = AgentIterationState(thread=thread, tools=[])
	# app_context=None -> no participant lookup, so only timestamps apply.
	result = await UserMessageFilter().process(state, _ctx(thread), None)
	return result.thread


def _user_at(thread: Thread, index: int = 0) -> UserMessage:
	message = thread.messages[index]
	assert isinstance(message, UserMessage)
	return message


@pytest.mark.asyncio
async def test_prepends_timestamp_to_text() -> None:
	thread = Thread(messages=[_user("hello", created_at="2025-06-15T10:30:00+00:00")])
	result = await _process(thread)
	assert _user_at(result).text == "[at: 2025-06-15 10:30 UTC] hello"


@pytest.mark.asyncio
async def test_no_created_at_skips_message() -> None:
	thread = Thread(messages=[_user("no timestamp")])
	result = await _process(thread)
	assert _user_at(result).text == "no timestamp"


@pytest.mark.asyncio
async def test_non_string_created_at_skips() -> None:
	msg = UserMessage.from_text("bad meta").model_copy(
		update={"metadata": {"_created_at": 12345}}
	)
	thread = Thread(messages=[msg])
	result = await _process(thread)
	assert _user_at(result).text == "bad meta"


@pytest.mark.asyncio
async def test_assistant_message_unchanged() -> None:
	user = _user("question", created_at="2025-01-01T00:00:00+00:00")
	thread = Thread(messages=[user, AssistantMessage.from_text("response")])
	result = await _process(thread)
	message = result.messages[1]
	assert isinstance(message, AssistantMessage)
	assert message.text == "response"


@pytest.mark.asyncio
async def test_image_only_gets_text_part_prepended() -> None:
	msg = UserMessage(
		content=[ImageContent(url="https://example.com/img.png")],
		metadata={"_created_at": "2025-07-01T12:00:00+00:00"},
	)
	thread = Thread(messages=[msg])
	result = await _process(thread)
	parts = _user_at(result).content
	assert len(parts) == 2
	assert isinstance(parts[0], TextContent)
	assert parts[0].text == "[at: 2025-07-01 12:00 UTC]"
	assert isinstance(parts[1], ImageContent)


@pytest.mark.asyncio
async def test_idempotent_across_passes() -> None:
	"""running the filter repeatedly (per-iteration) must not accumulate."""
	thread = Thread(messages=[_user("hello", created_at="2025-05-20T08:15:00+00:00")])
	first = await _process(thread)
	first_text = _user_at(first).text
	second = await _process(first)
	assert _user_at(second).text == first_text
