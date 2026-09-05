"""regression tests: tool exchanges reloaded from persistence must reach the provider.

persisted tool messages can lose their ``_provider_data`` metadata (the
provider-issued tool call id) while the assistant's tool_calls keep theirs.
serializers must still pair the exchange via the SDK tool_call id and emit
consistent ids, instead of dropping the tool history from the prompt.
"""

import logging
from typing import Any, cast

import pytest

from nokodo_ai.adapters.anthropic.messages import _messages_to_anthropic
from nokodo_ai.adapters.openai.chat_completions import (
	_messages_to_openai_chatcompletions,
)
from nokodo_ai.adapters.openai.responses import _messages_to_openai_responses_input
from nokodo_ai.messages import (
	AssistantMessage,
	ToolCall,
	ToolMessage,
	UserMessage,
)
from nokodo_ai.utils.provider_meta import provider_tool_call_metadata


def _persisted_exchange(provider: str) -> list[Any]:
	"""build user -> assistant(tool_call) -> tool -> user as loaded from the DB.

	the assistant's tool_call metadata carries the provider id (it survives in
	the tool_calls column); the tool message's metadata does not (sanitized to
	public keys only), so only its SDK ``tool_call_id`` links the pair.
	"""
	call = ToolCall(
		id="tool_call_sdk_1",
		name="fetch_url",
		arguments='{"url": "https://example.com"}',
		metadata=provider_tool_call_metadata(
			provider=provider,
			tool_call_id="provider_id_abc",
		),
	)
	assistant = AssistantMessage.from_text("fetching")
	assistant.tool_calls = [call]
	tool_msg = ToolMessage(
		tool_call_id="tool_call_sdk_1",
		tool_output="fetched content",
		metadata={"run_id": "run_1"},
	)
	return [
		UserMessage.from_text("fetch it"),
		assistant,
		tool_msg,
		UserMessage.from_text("what did it say?"),
	]


def test_anthropic_pairs_persisted_tool_history_by_sdk_id() -> None:
	_, msgs = _messages_to_anthropic(_persisted_exchange("anthropic.messages"))

	assert [m["role"] for m in msgs] == ["user", "assistant", "user", "user"]
	assistant_blocks = cast("list[dict[str, Any]]", msgs[1]["content"])
	tool_use_blocks = [b for b in assistant_blocks if b["type"] == "tool_use"]
	assert len(tool_use_blocks) == 1
	assert tool_use_blocks[0]["name"] == "fetch_url"
	assert tool_use_blocks[0]["input"] == {"url": "https://example.com"}

	result_blocks = cast("list[dict[str, Any]]", msgs[2]["content"])
	assert result_blocks[0]["type"] == "tool_result"
	assert result_blocks[0]["content"] == "fetched content"
	assert result_blocks[0]["is_error"] is False
	# the pair must share one id for anthropic to accept the turn
	assert result_blocks[0]["tool_use_id"] == tool_use_blocks[0]["id"]


def test_anthropic_multiple_calls_pair_by_sdk_id_without_duplicates() -> None:
	calls = [
		ToolCall(
			id=f"tool_call_sdk_{n}",
			name="fetch_url",
			arguments="{}",
			metadata=provider_tool_call_metadata(
				provider="anthropic.messages",
				tool_call_id=f"provider_id_{n}",
			),
		)
		for n in (1, 2)
	]
	assistant = AssistantMessage(content=[], tool_calls=calls)
	tool_msgs = [
		ToolMessage(
			tool_call_id=f"tool_call_sdk_{n}",
			tool_output=f"result {n}",
			metadata={},
		)
		for n in (1, 2)
	]

	_, msgs = _messages_to_anthropic([assistant, *tool_msgs])

	assistant_blocks = cast("list[dict[str, Any]]", msgs[0]["content"])
	tool_use_ids = [b["id"] for b in assistant_blocks if b["type"] == "tool_use"]
	result_blocks = cast("list[dict[str, Any]]", msgs[1]["content"])
	assert [b["tool_use_id"] for b in result_blocks] == tool_use_ids
	assert [b["content"] for b in result_blocks] == ["result 1", "result 2"]
	assert not any(b.get("is_error") for b in result_blocks)


def test_openai_chatcompletions_pairs_persisted_tool_history_by_sdk_id() -> None:
	msgs = _messages_to_openai_chatcompletions(
		_persisted_exchange("openai.chat_completions")
	)

	assert [m["role"] for m in msgs] == ["user", "assistant", "tool", "user"]
	assistant_msg = cast("dict[str, Any]", msgs[1])
	tool_msg = cast("dict[str, Any]", msgs[2])
	assert assistant_msg["tool_calls"][0]["id"] == "provider_id_abc"
	# the tool message must reference the id the assistant turn emitted
	assert tool_msg["tool_call_id"] == assistant_msg["tool_calls"][0]["id"]


def test_openai_responses_pairs_persisted_tool_history_by_sdk_id() -> None:
	items = cast(
		"list[dict[str, Any]]",
		_messages_to_openai_responses_input(_persisted_exchange("openai.responses")),
	)

	calls = [i for i in items if i.get("type") == "function_call"]
	outputs = [i for i in items if i.get("type") == "function_call_output"]
	assert len(calls) == 1
	assert calls[0]["call_id"] == "provider_id_abc"
	assert len(outputs) == 1
	assert outputs[0]["output"] == "fetched content"
	# the pair must share one id for the provider to accept the turn
	assert outputs[0]["call_id"] == calls[0]["call_id"]


def test_anthropic_drops_unmatched_tool_results_loudly(
	caplog: pytest.LogCaptureFixture,
) -> None:
	assistant = AssistantMessage(
		content=[],
		tool_calls=[ToolCall(id="sdk_1", name="t", arguments="{}")],
	)
	with caplog.at_level(logging.WARNING):
		_, msgs = _messages_to_anthropic(
			[
				assistant,
				ToolMessage(tool_call_id="sdk_1", tool_output="ok"),
				ToolMessage(tool_call_id="ghost", tool_output="?"),
			]
		)

	result_blocks = cast("list[dict[str, Any]]", msgs[1]["content"])
	assert [b["tool_use_id"] for b in result_blocks] == ["sdk_1"]
	assert "ghost" in caplog.text
