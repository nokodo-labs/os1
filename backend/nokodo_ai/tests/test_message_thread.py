"""tests for SDK message and thread models."""

from time import monotonic

import pytest

from nokodo_ai import (
	AssistantMessage,
	JsonContent,
	RefusalContent,
	SystemMessage,
	TextContent,
	Thread,
	ToolCall,
	ToolMessage,
	UserMessage,
)
from nokodo_ai.messages import _HasTextContentHelpers


def test_user_message_creation() -> None:
	msg = UserMessage.from_text("hello")
	assert len(msg.content) == 1
	assert isinstance(msg.content[0], TextContent)
	assert msg.text == "hello"


def test_assistant_message_creation() -> None:
	msg = AssistantMessage.from_text("hi there")
	assert msg.text == "hi there"
	assert msg.tool_calls == []


def test_assistant_message_with_tool_calls() -> None:
	tool_call = ToolCall(id="call_1", name="get_weather", arguments={"city": "paris"})
	msg = AssistantMessage(content=[], tool_calls=[tool_call])
	assert len(msg.tool_calls) == 1
	assert msg.tool_calls[0].name == "get_weather"
	assert msg.tool_calls[0].arguments["city"] == "paris"  # type: ignore[index, call-overload]


def test_tool_call_default_id_is_set() -> None:
	tool_call = ToolCall(name="get_weather")
	assert tool_call.id != ""


# -- ToolCall monotonic timing ------------------------------------------------


def test_tool_call_created_at_monotonic_is_set() -> None:
	"""created_at_monotonic should be populated by default using monotonic clock."""
	before = monotonic()
	tc = ToolCall(name="test")
	after = monotonic()
	assert before <= tc.created_at_monotonic <= after


def test_tool_call_created_at_monotonic_excluded_from_dump() -> None:
	"""created_at_monotonic must never appear in serialized output (DB/API)."""
	tc = ToolCall(name="test")
	dumped = tc.model_dump()
	assert "created_at_monotonic" not in dumped

	dumped_json = tc.model_dump(mode="json")
	assert "created_at_monotonic" not in dumped_json


def test_tool_call_created_at_monotonic_survives_model_copy() -> None:
	"""model_copy (used in delta merge for new tool calls) preserves monotonic."""
	tc = ToolCall(name="test")
	copied = tc.model_copy(deep=True)
	assert copied.created_at_monotonic == tc.created_at_monotonic


def test_tool_call_model_validate_sets_monotonic_even_without_input() -> None:
	"""when deserializing from DB/API data (no monotonic field), a fresh
	monotonic value must still be generated."""
	before = monotonic()
	tc = ToolCall.model_validate({"name": "from_db", "id": "tc_1"})
	after = monotonic()
	assert before <= tc.created_at_monotonic <= after


# -- assistant merge preserves earliest monotonic -----------------------------


def test_assistant_merge_preserves_earliest_tool_call_monotonic() -> None:
	"""delta merge must keep the smallest created_at_monotonic across chunks."""
	base = AssistantMessage.from_text("")
	early_mono = monotonic() - 100.0
	late_mono = monotonic()

	base.tool_calls = [
		ToolCall(id="tc1", name="t", arguments="{", created_at_monotonic=late_mono)
	]
	delta = AssistantMessage.from_text("")
	delta.tool_calls = [
		ToolCall(id="tc1", name="t", arguments="}", created_at_monotonic=early_mono)
	]

	base.merge(delta)
	assert base.tool_calls[0].created_at_monotonic == early_mono


def test_assistant_merge_does_not_overwrite_earlier_monotonic() -> None:
	"""if base already has the earlier monotonic, delta should not overwrite it."""
	early_mono = monotonic() - 100.0
	late_mono = monotonic()

	base = AssistantMessage.from_text("")
	base.tool_calls = [
		ToolCall(id="tc1", name="t", arguments="{", created_at_monotonic=early_mono)
	]
	delta = AssistantMessage.from_text("")
	delta.tool_calls = [
		ToolCall(id="tc1", name="t", arguments="}", created_at_monotonic=late_mono)
	]

	base.merge(delta)
	assert base.tool_calls[0].created_at_monotonic == early_mono


def test_tool_message_creation() -> None:
	msg = ToolMessage(tool_call_id="call_1", tool_output="sunny")
	assert msg.tool_output == "sunny"
	assert msg.is_error is False


def test_tool_result_error() -> None:
	msg = ToolMessage(tool_call_id="call_1", tool_output="not found", is_error=True)
	assert msg.is_error is True


def test_system_message_creation() -> None:
	msg = SystemMessage.from_text("you are a helpful assistant")
	assert msg.text == "you are a helpful assistant"


def test_thread_creation_empty() -> None:
	thread = Thread()
	assert len(thread.messages) == 0


def test_thread_add_messages() -> None:
	thread = Thread()
	thread.add(UserMessage.from_text("hello"))
	thread.add(AssistantMessage.from_text("hi"))
	assert len(thread.messages) == 2


def test_assistant_json_and_refusal_helpers() -> None:
	msg = AssistantMessage(
		content=[
			JsonContent(data={"foo": "bar"}),
			RefusalContent(reason="nope"),
		],
	)
	assert msg.json_content == {"foo": "bar"}
	assert msg.refusal == "nope"

	plain = AssistantMessage.from_text("hi")
	assert plain.json_content is None
	assert plain.refusal is None


def test_text_content_helpers_raise() -> None:
	class Dummy(_HasTextContentHelpers):
		"""dummy helper implementation"""

		pass

	dummy = Dummy()
	with pytest.raises(NotImplementedError):
		Dummy.from_text("x")

	with pytest.raises(NotImplementedError):
		_ = dummy.text
