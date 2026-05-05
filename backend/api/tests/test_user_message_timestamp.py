"""tests for UserMessageTimestampFilter."""

from __future__ import annotations

import pytest

from api.v1.service.chat.filters.user_message_timestamp import (
	UserMessageTimestampFilter,
)
from nokodo_ai.messages import (
	AssistantMessage,
	ImageContent,
	TextContent,
	UserMessage,
)
from nokodo_ai.threads import Thread


def _make_filter() -> UserMessageTimestampFilter:
	return UserMessageTimestampFilter()


def _user(text: str, created_at: str | None = None) -> UserMessage:
	meta = {}
	if created_at is not None:
		meta["_created_at"] = created_at
	return UserMessage.from_text(text).model_copy(update={"metadata": meta})


def _result_user(thread: Thread, index: int = 0) -> UserMessage:
	message = thread.messages[index]
	assert isinstance(message, UserMessage)
	return message


def _result_assistant(thread: Thread, index: int = 1) -> AssistantMessage:
	message = thread.messages[index]
	assert isinstance(message, AssistantMessage)
	return message


class TestTimestampPrepend:
	"""basic prepend behavior."""

	@pytest.mark.asyncio
	async def test_prepends_timestamp_to_text(self) -> None:
		msg = _user("hello", created_at="2025-06-15T10:30:00+00:00")
		thread = Thread(messages=[msg])

		result = await _make_filter().process(thread, None)

		text = _result_user(result).text
		assert text == "[2025-06-15 10:30 UTC] hello"

	@pytest.mark.asyncio
	async def test_formats_utc_correctly(self) -> None:
		msg = _user("hi", created_at="2024-12-31T23:59:00+00:00")
		thread = Thread(messages=[msg])

		result = await _make_filter().process(thread, None)

		assert _result_user(result).text == "[2024-12-31 23:59 UTC] hi"

	@pytest.mark.asyncio
	async def test_converts_non_utc_to_local_representation(self) -> None:
		msg = _user("test", created_at="2025-03-10T15:00:00+05:00")
		thread = Thread(messages=[msg])

		result = await _make_filter().process(thread, None)

		# strftime uses the tz-aware datetime as-is (15:00 in +05:00)
		assert "[2025-03-10 15:00 UTC]" in _result_user(result).text


class TestSkipWithoutTimestamp:
	"""messages without created_at metadata are left untouched."""

	@pytest.mark.asyncio
	async def test_no_created_at_skips_message(self) -> None:
		msg = _user("no timestamp")
		thread = Thread(messages=[msg])

		result = await _make_filter().process(thread, None)

		assert _result_user(result).text == "no timestamp"

	@pytest.mark.asyncio
	async def test_non_string_created_at_skips(self) -> None:
		msg = UserMessage.from_text("bad meta").model_copy(
			update={"metadata": {"_created_at": 12345}}
		)
		thread = Thread(messages=[msg])

		result = await _make_filter().process(thread, None)

		assert _result_user(result).text == "bad meta"


class TestNonUserMessagesUntouched:
	"""non-user messages pass through unchanged."""

	@pytest.mark.asyncio
	async def test_assistant_message_unchanged(self) -> None:
		assistant = AssistantMessage.from_text("response")
		user = _user("question", created_at="2025-01-01T00:00:00+00:00")
		thread = Thread(messages=[user, assistant])

		result = await _make_filter().process(thread, None)

		assert _result_assistant(result).text == "response"


class TestImageOnlyMessage:
	"""user messages with only non-text content."""

	@pytest.mark.asyncio
	async def test_image_only_gets_text_part_prepended(self) -> None:
		msg = UserMessage(
			content=[ImageContent(url="https://example.com/img.png")],
			metadata={"_created_at": "2025-07-01T12:00:00+00:00"},
		)
		thread = Thread(messages=[msg])

		result = await _make_filter().process(thread, None)

		parts = _result_user(result).content
		assert len(parts) == 2
		assert isinstance(parts[0], TextContent)
		assert parts[0].text == "[2025-07-01 12:00 UTC]"
		assert isinstance(parts[1], ImageContent)


class TestNoAccumulation:
	"""prove that running the filter multiple times does NOT accumulate timestamps.

	this simulates the agent loop where filters run before each model call
	on the same thread object. the filter must be idempotent with respect
	to the original messages.
	"""

	@pytest.mark.asyncio
	async def test_two_passes_same_result(self) -> None:
		msg = _user("hello world", created_at="2025-05-20T08:15:00+00:00")
		thread = Thread(messages=[msg])
		f = _make_filter()

		first_pass = await f.process(thread, None)
		first_text = _result_user(first_pass).text

		second_pass = await f.process(first_pass, None)
		second_text = _result_user(second_pass).text

		assert first_text == "[2025-05-20 08:15 UTC] hello world"
		assert second_text == first_text, (
			f"timestamp accumulated on second pass: {second_text!r}"
		)

	@pytest.mark.asyncio
	async def test_five_passes_no_drift(self) -> None:
		msg = _user("stable", created_at="2025-01-01T00:00:00+00:00")
		thread = Thread(messages=[msg])
		f = _make_filter()

		for i in range(5):
			thread = await f.process(thread, None)

		text = _result_user(thread).text
		assert text == "[2025-01-01 00:00 UTC] stable", (
			f"after 5 passes, text drifted: {text!r}"
		)

	@pytest.mark.asyncio
	async def test_original_message_not_mutated(self) -> None:
		msg = _user("original", created_at="2025-03-15T09:00:00+00:00")
		thread = Thread(messages=[msg])

		await _make_filter().process(thread, None)

		# the original message object must still have its original text
		assert msg.text == "original"
