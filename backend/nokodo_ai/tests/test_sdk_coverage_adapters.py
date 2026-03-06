"""coverage-driven tests for SDK adapters.

these tests use dummy clients and monkeypatching to avoid network calls.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, cast

import pytest

from nokodo_ai.adapters.anthropic import base as anthropic_base
from nokodo_ai.adapters.anthropic import messages as am
from nokodo_ai.adapters.anthropic.base import BaseAnthropicAdapter
from nokodo_ai.adapters.anthropic.messages import (
	AnthropicMessagesAdapter,
	_messages_to_anthropic,
	_tool_choice_to_anthropic,
	_tools_to_anthropic,
)
from nokodo_ai.adapters.base.chat import BaseChatAdapter, ChatGenerationParams
from nokodo_ai.adapters.base.client import BaseClientAdapter
from nokodo_ai.adapters.ollama.chat import OllamaChatAdapter
from nokodo_ai.adapters.ollama.embeddings import OllamaEmbeddingsAdapter
from nokodo_ai.adapters.openai import base as openai_base
from nokodo_ai.adapters.openai import chat_completions as cc
from nokodo_ai.adapters.openai import responses as resp_mod
from nokodo_ai.adapters.openai.base import BaseOpenAIAdapter
from nokodo_ai.adapters.openai.chat_completions import (
	OpenAIChatCompletionsAdapter,
	_chat_completion_to_assistant_message,
	_logit_bias_to_openai_chatcompletions,
	_messages_to_openai_chatcompletions,
	_openai_stream_to_assistant_messages,
	_openai_tool_calls_to_tool_calls,
	_response_format_to_openai_chatcompletions,
	_tool_choice_to_openai_chatcompletions,
	_tools_to_openai_chatcompletions,
)
from nokodo_ai.adapters.openai.embeddings import OpenAIEmbeddingsAdapter
from nokodo_ai.adapters.openai.responses import (
	OpenAIResponsesAdapter,
	_messages_to_openai_responses_input,
	_tool_choice_to_openai_responses,
	_tools_to_openai_responses,
)
from nokodo_ai.messages import (
	AssistantMessage,
	JsonContent,
	Message,
	SystemMessage,
	ToolCall,
	ToolMessage,
	Usage,
	UserMessage,
)
from nokodo_ai.tool import ToolDefinition


class _DummyAsyncIterator:
	def __init__(self, items: list[Any]) -> None:
		self._items = list(items)

	def __aiter__(self) -> _DummyAsyncIterator:
		return self

	async def __anext__(self) -> Any:
		if not self._items:
			raise StopAsyncIteration
		return self._items.pop(0)


def test_base_api_adapter_not_implemented_get_client_is_covered() -> None:
	class _CallsSuperApi(BaseClientAdapter[object]):
		def _get_client(self) -> object:
			# explicitly call super to cover the NotImplementedError branch
			return super()._get_client()  # type: ignore[safe-super]

		async def close(self) -> None:
			return None

	with pytest.raises(NotImplementedError, match="subclasses must implement"):
		_CallsSuperApi()


def test_openai_and_anthropic_base_get_client_includes_optional_fields(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	# openai

	created: list[dict[str, object]] = []

	class _DummyClient:
		def __init__(self, **kwargs: object):
			created.append(dict(kwargs))

	monkeypatch.setattr(openai_base, "AsyncOpenAI", _DummyClient)
	BaseOpenAIAdapter(api_key="k", base_url="http://x", timeout=1.0)
	assert created and created[-1]["api_key"] == "k"
	assert created[-1]["base_url"] == "http://x"
	assert created[-1]["timeout"] == 1.0

	# anthropic

	created2: list[dict[str, object]] = []

	class _DummyAnthropic:
		def __init__(self, **kwargs: object):
			created2.append(dict(kwargs))

	monkeypatch.setattr(anthropic_base, "AsyncAnthropic", _DummyAnthropic)
	BaseAnthropicAdapter(api_key="k", base_url="http://y", timeout=2.0)
	assert created2 and created2[-1]["api_key"] == "k"
	assert created2[-1]["base_url"] == "http://y"
	assert created2[-1]["timeout"] == 2.0

	BaseAnthropicAdapter(
		api_key="k", base_url="https://api.anthropic.com/v1", timeout=2.0
	)
	assert created2[-1]["base_url"] == "https://api.anthropic.com"


def test_base_chat_adapter_generate_not_implemented_is_covered() -> None:
	class _CallsSuperChat(BaseChatAdapter):
		def generate(  # type: ignore[override]
			self,
			messages: list[Message],
			model: str,
			stream: bool = False,
			tools: list[ToolDefinition] | None = None,
			params: ChatGenerationParams | None = None,
		) -> Awaitable[AssistantMessage] | AsyncIterator[AssistantMessage]:
			return cast(
				Awaitable[AssistantMessage] | AsyncIterator[AssistantMessage],
				cast(Any, super()).generate(
					messages,
					model,
					stream=stream,
					tools=tools or [],
					params=params,
				),
			)

	adapter = _CallsSuperChat()
	with pytest.raises(NotImplementedError, match=r"generate\(\) not implemented"):
		adapter.generate([UserMessage.from_text("hi")], "stub")


@pytest.mark.asyncio
async def test_ollama_adapters_raise_not_implemented_paths() -> None:
	chat = OllamaChatAdapter()
	with pytest.raises(NotImplementedError, match="not yet implemented"):
		await chat.generate([UserMessage.from_text("hi")], model="llama", stream=False)
	with pytest.raises(NotImplementedError, match="not yet implemented"):
		await cast(
			Any,
			chat.generate(
				[UserMessage.from_text("hi")],
				model="llama",
				stream=True,
			),
		)


@pytest.mark.asyncio
async def test_ollama_embedding_adapter_raises_not_implemented() -> None:
	embed = OllamaEmbeddingsAdapter()
	with pytest.raises(NotImplementedError, match="not yet implemented"):
		await embed.embed(["a"], model="m")


def test_anthropic_helpers_cover_branches() -> None:
	assert _tool_choice_to_anthropic("auto")["type"] == "auto"
	assert _tool_choice_to_anthropic("none")["type"] == "none"
	assert _tool_choice_to_anthropic("required")["type"] == "any"
	assert _tool_choice_to_anthropic("my_tool")["type"] == "tool"

	tools = [ToolDefinition(name="t", description="d", parameters={"type": "object"})]
	anthropic_tools = _tools_to_anthropic(tools)
	assert anthropic_tools[0]["name"] == "t"


def test_anthropic_messages_to_anthropic_tool_use_id_fallback_and_errors() -> None:
	tool_call = ToolCall(id="tc1", name="tool", arguments="{bad json", metadata={})
	assistant = AssistantMessage(content=[], tool_calls=[tool_call])
	system = SystemMessage.from_text("sys")
	user = UserMessage.from_text("hi")
	# tool call should fall back to ToolCall.id when provider data missing
	system_text, msgs = _messages_to_anthropic([system, user, assistant])
	assert system_text == "sys"
	assert len(msgs) == 2
	assert msgs[0]["role"] == "user"
	assert msgs[1]["role"] == "assistant"

	# tool message should fall back to tool_call_id when provider data missing
	system_text2, msgs2 = _messages_to_anthropic(
		[user, ToolMessage(tool_call_id="x", tool_output="out", metadata={})]
	)
	assert msgs2[1]["content"][0]["tool_use_id"] == "x"  # type: ignore[index]

	with pytest.raises(TypeError, match="unsupported message type"):
		_messages_to_anthropic([object()])  # type: ignore[list-item]


def test_anthropic_messages_to_anthropic_additional_edge_branches() -> None:
	# empty system message should be ignored (covers SystemMessage.text falsy branch)
	empty_sys = SystemMessage.from_text("")

	# assistant with no text/json/tool_calls triggers the empty assistant content branch
	empty_assistant = AssistantMessage(content=[], tool_calls=[])

	# tool calls cover: tool_use_id fallback, dict args path, str args (list/json error)
	assistant = AssistantMessage.from_text("hi")
	assistant.tool_calls = [
		ToolCall(
			id="tc1",
			name="t1",
			arguments={"a": 1},
			metadata={},
		),
		ToolCall(
			id="tc2",
			name="t2",
			arguments="[]",
			metadata={},
		),
		ToolCall(
			id="tc3",
			name="t3",
			arguments="{bad",
			metadata={
				"_provider_data": {
					"anthropic.messages": {
						"tool_call_id": "tid3",
					}
				}
			},
		),
		ToolCall(
			id="tc4",
			name="t4",
			arguments=None,
			metadata={
				"_provider_data": {
					"anthropic.messages": {
						"tool_call_id": "tid4",
					}
				}
			},
		),
	]

	system_text, msgs = _messages_to_anthropic([empty_sys, empty_assistant, assistant])
	assert system_text is None
	assert any(m.get("role") == "assistant" for m in msgs)


@dataclass
class _DummyOpenAIUsage:
	prompt_tokens: int = 1
	completion_tokens: int = 2
	total_tokens: int = 3


@dataclass
class _DummyOpenAIFunction:
	name: str
	arguments: str | None = None


@dataclass
class _DummyOpenAIToolCall:
	id: str
	function: _DummyOpenAIFunction


@dataclass
class _DummyOpenAIMessage:
	content: str | None = None
	refusal: str | None = None
	tool_calls: list[Any] | None = None


@dataclass
class _DummyOpenAIChoice:
	index: int
	message: _DummyOpenAIMessage
	finish_reason: str | None = None


@dataclass
class _DummyOpenAICompletion:
	id: str = "cmp1"
	choices: list[_DummyOpenAIChoice] | None = None
	usage: _DummyOpenAIUsage | None = None


@dataclass
class _DummyOpenAIDeltaToolCall:
	index: int
	id: str | None = None
	function: Any | None = None


@dataclass
class _DummyOpenAIDelta:
	content: str | None = None
	refusal: str | None = None
	tool_calls: list[_DummyOpenAIDeltaToolCall] | None = None


@dataclass
class _DummyOpenAIChunkChoice:
	index: int
	delta: _DummyOpenAIDelta
	finish_reason: str | None = None


@dataclass
class _DummyOpenAIChunk:
	choices: list[_DummyOpenAIChunkChoice]
	usage: _DummyOpenAIUsage | None = None


def test_openai_chat_helpers_cover_branches(
	monkeypatch: pytest.MonkeyPatch,
	caplog: pytest.LogCaptureFixture,
) -> None:
	# make isinstance checks accept our dummy tool call class
	monkeypatch.setattr(
		cc,
		"OpenAIChatCompletionFunctionToolCall",
		_DummyOpenAIToolCall,
	)

	assert _tool_choice_to_openai_chatcompletions("auto") == "auto"
	assert _tool_choice_to_openai_chatcompletions("none") == "none"
	assert _tool_choice_to_openai_chatcompletions("required") == "required"
	choice = _tool_choice_to_openai_chatcompletions("x")
	assert cast(Any, choice)["function"]["name"] == "x"

	assert _logit_bias_to_openai_chatcompletions({"1": 0.9}) == {"1": 0}

	schema = _response_format_to_openai_chatcompletions({"type": "object"})
	assert schema["type"] == "json_schema"

	tools = [ToolDefinition(name="t", description="d", parameters={"type": "object"})]
	assert _tools_to_openai_chatcompletions(tools)[0]["type"] == "function"

	assistant = AssistantMessage.from_text("hi")
	assistant.tool_calls = [
		ToolCall(
			name="t",
			arguments={"a": 1},
			metadata={
				"_provider_data": {
					"openai.chat_completions": {
						"tool_call_id": "id1",
					}
				}
			},
		)
	]
	openai_msgs = _messages_to_openai_chatcompletions(
		[UserMessage.from_text("u"), SystemMessage.from_text("s"), assistant]
	)
	assert len(openai_msgs) == 3

	# tool message without provider data should fall back to sdk tool_call_id
	tool_msgs = _messages_to_openai_chatcompletions(
		[
			assistant,
			ToolMessage(tool_call_id="fallback_id", tool_output="y"),
		]
	)
	assert tool_msgs[-1]["tool_call_id"] == "fallback_id"  # type: ignore[typeddict-item]

	with pytest.raises(TypeError, match="unsupported message type"):
		_messages_to_openai_chatcompletions([object()])  # type: ignore[list-item]

	tool_calls = _openai_tool_calls_to_tool_calls(
		cast(
			Any,
			[
				_DummyOpenAIToolCall(
					id="id1",
					function=_DummyOpenAIFunction(name="f", arguments=None),
				)
			],
		)
	)
	assert tool_calls[0].name == "f"
	assert _openai_tool_calls_to_tool_calls(cast(Any, [object()])) == []

	# content_filter with missing refusal triggers warning and adds refusal content
	caplog.clear()
	caplog.set_level("WARNING")
	completion = _DummyOpenAICompletion(
		choices=[
			_DummyOpenAIChoice(
				index=0,
				message=_DummyOpenAIMessage(
					content=None,
					refusal=None,
					tool_calls=[],
				),
				finish_reason="content_filter",
			)
		],
		usage=_DummyOpenAIUsage(),
	)
	msg = _chat_completion_to_assistant_message(completion)  # type: ignore[arg-type]
	assert msg.finish_reason == "content_filter"
	assert msg.refusal is not None
	assert any("content filtered" in r.message for r in caplog.records)

	# content_filter with explicit refusal covers the else branch
	completion2 = _DummyOpenAICompletion(
		choices=[
			_DummyOpenAIChoice(
				index=0,
				message=_DummyOpenAIMessage(
					content=None,
					refusal="because",
					tool_calls=[],
				),
				finish_reason="content_filter",
			)
		],
		usage=None,
	)
	msg2 = _chat_completion_to_assistant_message(completion2)  # type: ignore[arg-type]
	assert msg2.refusal == "because"

	# unknown completion finish_reason should leave default finish_reason
	completion3 = _DummyOpenAICompletion(
		choices=[
			_DummyOpenAIChoice(
				index=0,
				message=_DummyOpenAIMessage(content="x", refusal=None, tool_calls=[]),
				finish_reason="weird",
			)
		],
		usage=None,
	)
	msg3 = _chat_completion_to_assistant_message(completion3)  # type: ignore[arg-type]
	assert msg3.finish_reason == "stop"


@pytest.mark.asyncio
async def test_openai_chat_stream_accumulator_covers_finish_reasons(
	monkeypatch: pytest.MonkeyPatch,
	caplog: pytest.LogCaptureFixture,
) -> None:
	# ensure unknown finish reason warning path is hit
	caplog.set_level("WARNING")

	chunks = [
		_DummyOpenAIChunk(
			choices=[
				_DummyOpenAIChunkChoice(index=0, delta=_DummyOpenAIDelta(content="a"))
			]
		),
		_DummyOpenAIChunk(
			choices=[
				_DummyOpenAIChunkChoice(
					index=0,
					delta=_DummyOpenAIDelta(refusal="no"),
					finish_reason="weird",
				)
			]
		),
		_DummyOpenAIChunk(
			choices=[
				_DummyOpenAIChunkChoice(
					index=0,
					delta=_DummyOpenAIDelta(
						tool_calls=[
							_DummyOpenAIDeltaToolCall(
								index=0,
								id="id0",
								function=_DummyOpenAIFunction(name="f", arguments="{"),
							),
							_DummyOpenAIDeltaToolCall(
								index=0,
								function=_DummyOpenAIFunction(name="f", arguments="}"),
							),
						]
					),
					finish_reason="tool_calls",
				)
			],
			usage=_DummyOpenAIUsage(),
		),
	]

	stream = _DummyAsyncIterator(chunks)
	seen: list[AssistantMessage] = []
	async for delta in _openai_stream_to_assistant_messages(stream):  # type: ignore[arg-type]
		seen.append(delta)

	assert any(m.text == "a" for m in seen)
	assert any(m.refusal == "no" for m in seen)
	assert any(m.tool_calls for m in seen)
	assert any(m.finish_reason == "tool_calls" for m in seen)
	assert any("unknown openai finish reason" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_openai_chat_stream_tool_call_delta_missing_fields() -> None:
	# cover the per-delta branches where function exists but name/arguments are missing
	fn = SimpleNamespace(name=None, arguments=None)
	chunks = [
		_DummyOpenAIChunk(
			choices=[
				_DummyOpenAIChunkChoice(
					index=0,
					delta=_DummyOpenAIDelta(
						tool_calls=[
							_DummyOpenAIDeltaToolCall(
								index=0,
								id=None,
								function=fn,
							)
						],
					),
					finish_reason="tool_calls",
				)
			]
		)
	]
	stream = _DummyAsyncIterator(chunks)
	seen: list[AssistantMessage] = []
	async for delta in _openai_stream_to_assistant_messages(stream):  # type: ignore[arg-type]
		seen.append(delta)
	# should not crash; final message should exist due to finish_reason
	assert any(m.finish_reason == "tool_calls" for m in seen)


@pytest.mark.asyncio
async def test_openai_stream_tool_call_metadata_and_created_at() -> None:
	"""tool call deltas carry provider metadata, auto-generated SDK id, and
	timestamps."""
	chunks = [
		_DummyOpenAIChunk(
			choices=[
				_DummyOpenAIChunkChoice(
					index=0,
					delta=_DummyOpenAIDelta(
						tool_calls=[
							_DummyOpenAIDeltaToolCall(
								index=0,
								id="id0",
								function=_DummyOpenAIFunction(
									name="f", arguments='{"a":'
								),
							),
						]
					),
				)
			],
		),
		_DummyOpenAIChunk(
			choices=[
				_DummyOpenAIChunkChoice(
					index=0,
					delta=_DummyOpenAIDelta(
						tool_calls=[
							_DummyOpenAIDeltaToolCall(
								index=0,
								function=_DummyOpenAIFunction(name="f", arguments="1}"),
							),
						]
					),
					finish_reason="tool_calls",
				)
			],
		),
	]
	stream = _DummyAsyncIterator(chunks)
	tc_deltas: list[AssistantMessage] = []
	async for delta in _openai_stream_to_assistant_messages(stream):  # type: ignore[arg-type]
		if delta.tool_calls:
			tc_deltas.append(delta)

	# should have two tool call deltas (one per chunk)
	assert len(tc_deltas) == 2
	first_tc = tc_deltas[0].tool_calls[0]
	second_tc = tc_deltas[1].tool_calls[0]

	# SDK id auto-generated (not the provider's "id0"), stable across deltas
	assert first_tc.id == second_tc.id
	assert first_tc.id.startswith("tool_call_")
	assert first_tc.id != "id0"

	# created_at matches (first-seen for both)
	assert first_tc.created_at == second_tc.created_at

	# updated_at progresses (second should be >= first)
	assert second_tc.updated_at >= first_tc.updated_at

	# first delta carries provider metadata
	assert first_tc.metadata == {
		"_provider_data": {
			"openai.chat_completions": {
				"tool_call_id": "id0",
			}
		}
	}

	# arguments are streamed per-chunk, not accumulated
	assert first_tc.arguments == '{"a":'
	assert second_tc.arguments == "1}"

	# AssistantMessage deltas also carry timestamps
	assert tc_deltas[0].created_at > 0
	assert tc_deltas[0].updated_at >= tc_deltas[0].created_at


def test_openai_messages_to_chatcompletions_tool_message_success() -> None:
	# assistant without tool_calls covers the false branch
	assistant = AssistantMessage.from_text("hi")
	openai_msgs = _messages_to_openai_chatcompletions([assistant])
	assert len(openai_msgs) == 1

	# ToolMessage success branch
	openai_msgs2 = _messages_to_openai_chatcompletions(
		[
			ToolMessage(
				tool_call_id="x",
				tool_output="y",
				metadata={
					"_provider_data": {
						"openai.chat_completions": {
							"tool_call_id": "id1",
						}
					}
				},
			)
		]
	)
	assert len(openai_msgs2) == 1


@pytest.mark.asyncio
async def test_openai_chat_stream_skips_empty_choices_and_indexes() -> None:
	stream = _DummyAsyncIterator(
		[
			_DummyOpenAIChunk(choices=[]),
			_DummyOpenAIChunk(
				choices=[
					_DummyOpenAIChunkChoice(
						index=1,
						delta=_DummyOpenAIDelta(content="x"),
					)
				]
			),
			_DummyOpenAIChunk(
				choices=[
					_DummyOpenAIChunkChoice(
						index=0,
						delta=_DummyOpenAIDelta(),
					)
				]
			),
		]
	)
	seen: list[AssistantMessage] = []
	async for delta in _openai_stream_to_assistant_messages(stream):  # type: ignore[arg-type]
		seen.append(delta)
	assert seen == []


@pytest.mark.asyncio
async def test_openai_chat_stream_content_filter_final_message() -> None:
	stream = _DummyAsyncIterator(
		[
			_DummyOpenAIChunk(
				choices=[
					_DummyOpenAIChunkChoice(
						index=0,
						delta=_DummyOpenAIDelta(),
						finish_reason="content_filter",
					)
				]
			)
		]
	)
	seen: list[AssistantMessage] = []
	async for delta in _openai_stream_to_assistant_messages(stream):  # type: ignore[arg-type]
		seen.append(delta)
	assert seen and seen[-1].refusal == "content filtered"


def test_openai_chat_completion_to_assistant_message_choices_and_length() -> None:
	completion = _DummyOpenAICompletion(
		choices=[],
		usage=None,
	)
	msg = _chat_completion_to_assistant_message(completion)  # type: ignore[arg-type]
	assert msg.finish_reason == "stop"

	completion2 = _DummyOpenAICompletion(
		choices=[
			_DummyOpenAIChoice(
				index=0,
				message=_DummyOpenAIMessage(content="x", refusal=None, tool_calls=[]),
				finish_reason="length",
			)
		],
		usage=None,
	)
	msg2 = _chat_completion_to_assistant_message(completion2)  # type: ignore[arg-type]
	assert msg2.finish_reason == "length"


@pytest.mark.asyncio
async def test_openai_adapters_generate_and_embedding(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	# patch client creation to avoid real OpenAI client
	class _DummyOpenAIClient:
		def __init__(self) -> None:
			self.chat = SimpleNamespace(completions=SimpleNamespace(create=None))
			self.responses = SimpleNamespace(create=None)
			self.embeddings = SimpleNamespace(create=None)

	dummy = _DummyOpenAIClient()

	async def _create_chat(**kwargs: Any) -> Any:
		_ = kwargs
		return _DummyOpenAICompletion(
			choices=[
				_DummyOpenAIChoice(
					index=0,
					message=_DummyOpenAIMessage(
						content="ok",
						refusal=None,
						tool_calls=[],
					),
					finish_reason="stop",
				)
			],
			usage=_DummyOpenAIUsage(),
		)

	async def _create_chat_stream(**kwargs: Any) -> Any:
		_ = kwargs
		return _DummyAsyncIterator(
			[
				_DummyOpenAIChunk(
					choices=[
						_DummyOpenAIChunkChoice(
							index=0,
							delta=_DummyOpenAIDelta(content="x"),
							finish_reason=None,
						)
					]
				),
				_DummyOpenAIChunk(
					choices=[
						_DummyOpenAIChunkChoice(
							index=0,
							delta=_DummyOpenAIDelta(),
							finish_reason="stop",
						)
					],
					usage=_DummyOpenAIUsage(),
				),
			]
		)

	async def _create_responses(**kwargs: Any) -> Any:
		_ = kwargs
		return SimpleNamespace(
			output=[],
			output_text='{"a": 1}',
			usage=SimpleNamespace(input_tokens=1, output_tokens=1, total_tokens=2),
		)

	async def _create_responses_stream(**kwargs: Any) -> Any:
		_ = kwargs
		return _DummyAsyncIterator([_TextDeltaEvent("z")])

	async def _create_embeddings(**kwargs: Any) -> Any:
		_ = kwargs
		return SimpleNamespace(data=[SimpleNamespace(embedding=[0.1, 0.2])])

	dummy.chat.completions.create = _create_chat

	# for stream=True, adapter calls same method; we switch based on kw
	async def _create_chat_router(**kwargs: Any) -> Any:
		if kwargs.get("stream"):
			return await _create_chat_stream(**kwargs)
		return await _create_chat(**kwargs)

	dummy.chat.completions.create = _create_chat_router
	dummy.responses.create = _create_responses
	dummy.embeddings.create = _create_embeddings

	monkeypatch.setattr(BaseOpenAIAdapter, "_get_client", lambda self: dummy)

	class _TextDeltaEvent:
		def __init__(self, delta: str):
			self.delta = delta

	monkeypatch.setattr(resp_mod, "OpenAIResponseTextDeltaEvent", _TextDeltaEvent)

	# now that _TextDeltaEvent exists, route responses.create for stream/non-stream
	async def _create_responses_router(**kwargs: Any) -> Any:
		if kwargs.get("stream"):
			return await _create_responses_stream(**kwargs)
		return await _create_responses(**kwargs)

	dummy.responses.create = _create_responses_router

	# chat completions
	chat = OpenAIChatCompletionsAdapter()
	msg_none_tools = await cast(
		Any,
		cast(Any, chat).generate(
			[UserMessage.from_text("hi")],
			"gpt-4o",
			tools=None,
		),
	)
	assert msg_none_tools.text == "ok"
	msg = await chat.generate([UserMessage.from_text("hi")], "gpt-4o")
	assert msg.text == "ok"

	streamed: list[str] = []
	async for part in chat.generate(
		[UserMessage.from_text("hi")],
		"gpt-4o",
		stream=True,
	):
		streamed.append(part.text)
	assert "x" in "".join(streamed)

	# responses
	responses = OpenAIResponsesAdapter()
	params = resp_mod.ChatGenerationParams(
		response_model={"type": "object"},
		tool_choice="auto",
	)
	msg2 = await responses.generate(
		[UserMessage.from_text("hi")],
		"gpt-4o",
		params=params,
	)
	assert msg2.json_content == {"a": 1}

	seen = []
	async for part in responses.generate(
		[UserMessage.from_text("hi")],
		"gpt-4o",
		stream=True,
	):
		seen.append(part.text)
	assert any("z" in t for t in seen)

	# embedding
	emb = OpenAIEmbeddingsAdapter()
	vectors = await emb.embed(["a"], model="text-embedding-3-small")
	assert vectors == [[0.1, 0.2]]


def test_openai_responses_input_helpers_and_errors() -> None:
	# assistant tool call should fall back to sdk ToolCall.id when provider data missing
	assistant = AssistantMessage.from_text("a")
	assistant.tool_calls = [
		ToolCall(id="sdk_tc_1", name="t", arguments="{}", metadata={})
	]
	items = _messages_to_openai_responses_input([assistant])
	assert cast(Any, items[0])["type"] == "message"
	assert cast(Any, items[1])["call_id"] == "sdk_tc_1"

	# tool message should fall back to sdk tool_call_id when provider data missing
	tool_items = _messages_to_openai_responses_input(
		[ToolMessage(tool_call_id="sdk_tc_2", tool_output="y")]
	)
	assert cast(Any, tool_items[0])["call_id"] == "sdk_tc_2"

	with pytest.raises(TypeError, match="unsupported message type"):
		_messages_to_openai_responses_input([object()])  # type: ignore[list-item]

	assert _tool_choice_to_openai_responses("auto") == "auto"
	assert _tool_choice_to_openai_responses("none") == "none"
	assert _tool_choice_to_openai_responses("required") == "required"
	choice2 = _tool_choice_to_openai_responses("f")
	assert cast(Any, choice2)["name"] == "f"

	tools = [ToolDefinition(name="t", description="d", parameters={"type": "object"})]
	openai_tools = _tools_to_openai_responses(tools)
	assert openai_tools[0]["name"] == "t"


def test_openai_responses_input_happy_paths() -> None:
	assistant = AssistantMessage.from_text("")
	assistant.tool_calls = [
		ToolCall(
			name="t",
			arguments={"a": 1},
			metadata={
				"_provider_data": {
					"openai.responses": {
						"tool_call_id": "id1",
					}
				}
			},
		)
	]
	items = _messages_to_openai_responses_input([assistant])
	first = cast(Any, items[0])
	assert first["type"] == "function_call"
	assert first["call_id"] == "id1"
	assert isinstance(first.get("arguments"), str)

	tool_msg = ToolMessage(
		tool_call_id="x",
		tool_output="ok",
		metadata={
			"_provider_data": {
				"openai.responses": {
					"tool_call_id": "id1",
				}
			}
		},
	)
	items2 = _messages_to_openai_responses_input([tool_msg])
	first2 = cast(Any, items2[0])
	assert first2["type"] == "function_call_output"

	# SystemMessage path
	items3 = _messages_to_openai_responses_input([SystemMessage.from_text("s")])
	first3 = cast(Any, items3[0])
	assert first3["role"] == "system"

	# empty assistant (no text/tool_calls) should produce no items
	items4 = _messages_to_openai_responses_input([AssistantMessage(content=[])])
	assert items4 == []


@pytest.mark.asyncio
async def test_openai_responses_streaming_tools_and_empty_text_delta(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	class _TextDeltaEvent:
		def __init__(self, delta: str):
			self.delta = delta

	monkeypatch.setattr(resp_mod, "OpenAIResponseTextDeltaEvent", _TextDeltaEvent)

	class _DummyClient:
		def __init__(self) -> None:
			async def _create(**kwargs: Any) -> Any:
				_ = kwargs
				return _DummyAsyncIterator(
					[
						_TextDeltaEvent(""),
						object(),
						_TextDeltaEvent("hi"),
					]
				)

			self.responses = SimpleNamespace(create=_create)

	monkeypatch.setattr(BaseOpenAIAdapter, "_get_client", lambda self: _DummyClient())
	adapter = OpenAIResponsesAdapter()
	params = resp_mod.ChatGenerationParams(tool_choice="auto")
	tools = [ToolDefinition(name="t", description="d", parameters={"type": "object"})]
	seen: list[str] = []
	async for part in adapter.generate(
		[UserMessage.from_text("u")],
		"gpt-4o",
		stream=True,
		tools=tools,
		params=params,
	):
		seen.append(part.text)
	assert "hi" in "".join(seen)

	# cover tools present but tool_choice is None (skips openai_tool_choice assignment)
	seen2: list[str] = []
	async for part in adapter.generate(
		[UserMessage.from_text("u")],
		"gpt-4o",
		stream=True,
		tools=tools,
		params=resp_mod.ChatGenerationParams(tool_choice=None),
	):
		seen2.append(part.text)
	assert "hi" in "".join(seen2)


@pytest.mark.asyncio
async def test_openai_responses_generate_once_covers_tool_calls_and_parse_fallback(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	class _FunctionToolCall:
		def __init__(self, call_id: str, name: str, arguments: str):
			self.call_id = call_id
			self.name = name
			self.arguments = arguments

	monkeypatch.setattr(resp_mod, "OpenAIResponseFunctionToolCall", _FunctionToolCall)

	class _DummyClient:
		def __init__(self) -> None:
			async def _create(**kwargs: Any) -> Any:
				# return different output_text based on response_model
				output_text = kwargs.get("text") and "{bad" or "plain"
				return SimpleNamespace(
					output=[
						_FunctionToolCall("c1", "tool", "{}"),
						object(),
					],
					output_text=output_text,
					usage=None,
				)

			self.responses = SimpleNamespace(create=_create)

	monkeypatch.setattr(BaseOpenAIAdapter, "_get_client", lambda self: _DummyClient())
	adapter = OpenAIResponsesAdapter()

	# with response_model: JSON decode error should fall back to TextContent
	params = resp_mod.ChatGenerationParams(response_model={"type": "object"})
	msg = await adapter.generate([UserMessage.from_text("hi")], "gpt-4o", params=params)
	assert msg.text == "{bad"
	assert msg.tool_calls and msg.tool_calls[0].name == "tool"

	# without response_model: plain text path
	msg2 = await adapter.generate([UserMessage.from_text("hi")], "gpt-4o")
	assert msg2.text == "plain"

	# output_text empty should yield an empty content list
	class _DummyClientEmptyText:
		def __init__(self) -> None:
			async def _create(**kwargs: Any) -> Any:
				_ = kwargs
				return SimpleNamespace(output=[], output_text="", usage=None)

			self.responses = SimpleNamespace(create=_create)

	monkeypatch.setattr(
		BaseOpenAIAdapter,
		"_get_client",
		lambda self: _DummyClientEmptyText(),
	)
	adapter_empty = OpenAIResponsesAdapter()
	msg3 = await adapter_empty.generate([UserMessage.from_text("hi")], "gpt-4o")
	assert msg3.text == ""


@pytest.mark.asyncio
async def test_anthropic_adapter_generate_once_and_streaming(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	# patch type checks to accept dummy event/block classes
	class _TextBlock:
		def __init__(self, text: str):
			self.text = text

	class _ToolUseBlock:
		def __init__(self, id: str, name: str, input: dict[str, object] | None = None):
			self.id = id
			self.name = name
			self.input = input or {}

	class _Usage:
		input_tokens = 1
		output_tokens = 2
		cache_creation_input_tokens = 0
		cache_read_input_tokens = 0

	class _Response:
		def __init__(self) -> None:
			self.content = [
				_TextBlock("hi"),
				_TextBlock(""),
				object(),
				_ToolUseBlock("t1", "tool", {"x": 1}),
				_ToolUseBlock("t2", "tool2", None),
			]
			self.usage = _Usage()

	class _StartEvent:
		def __init__(self, index: int, block: Any):
			self.index = index
			self.content_block = block

	class _TextDelta:
		def __init__(self, text: str):
			self.text = text

	class _InputJSONDelta:
		def __init__(self, partial_json: str):
			self.partial_json = partial_json

	class _DeltaEvent:
		def __init__(self, index: int, delta: Any):
			self.index = index
			self.delta = delta

	class _StopEvent:
		def __init__(self, index: int):
			self.index = index

	monkeypatch.setattr(am, "AnthropicTextBlock", _TextBlock)
	monkeypatch.setattr(am, "AnthropicToolUseBlock", _ToolUseBlock)
	monkeypatch.setattr(am, "AnthropicRawContentBlockStartEvent", _StartEvent)
	monkeypatch.setattr(am, "AnthropicRawContentBlockDeltaEvent", _DeltaEvent)
	monkeypatch.setattr(am, "AnthropicRawContentBlockStopEvent", _StopEvent)
	monkeypatch.setattr(am, "AnthropicTextDelta", _TextDelta)
	monkeypatch.setattr(am, "AnthropicInputJSONDelta", _InputJSONDelta)

	class _DummyAnthropicClient:
		def __init__(self) -> None:
			async def _create(**kwargs: Any) -> Any:
				_ = kwargs
				return _Response()

			self.messages = SimpleNamespace(create=_create)

	monkeypatch.setattr(
		am.BaseAnthropicAdapter,
		"_get_client",
		lambda self: _DummyAnthropicClient(),
	)

	adapter = AnthropicMessagesAdapter()
	msg = await adapter.generate(
		[SystemMessage.from_text("sys"), UserMessage.from_text("u")],
		model="claude",
	)
	assert msg.text == "hi"
	assert msg.tool_calls
	assert msg.tool_calls[0].metadata == {
		"_provider_data": {
			"anthropic.messages": {
				"tool_call_id": "t1",
			}
		}
	}
	assert msg.usage == Usage(
		input_tokens=1,
		output_tokens=2,
		total_tokens=3,
		cache_creation_input_tokens=0,
		cache_read_input_tokens=0,
	)
	assert msg.tool_calls[1].arguments == "{}"

	# response_model parsing: dict -> JsonContent
	params = am.ChatGenerationParams(
		response_model={"type": "object"},
		tool_choice="auto",
	)

	class _JsonResponse:
		def __init__(self) -> None:
			self.content = [_TextBlock('{"a": 1}')]
			self.usage = _Usage()

	class _Client2:
		def __init__(self) -> None:
			async def _create(**kwargs: Any) -> Any:
				_ = kwargs
				return _JsonResponse()

			self.messages = SimpleNamespace(create=_create)

	monkeypatch.setattr(
		am.BaseAnthropicAdapter,
		"_get_client",
		lambda self: _Client2(),
	)
	adapter_json = AnthropicMessagesAdapter()
	msg_json = await adapter_json.generate(
		[UserMessage.from_text("u")],
		model="claude",
		params=params,
		tools=[
			ToolDefinition(
				name="t",
				description="d",
				parameters={"type": "object"},
			)
		],
	)
	assert msg_json.json_content == {"a": 1}

	# response_model parsing: non-dict json -> TextContent
	class _ListResponse:
		def __init__(self) -> None:
			self.content = [_TextBlock("[1]")]
			self.usage = _Usage()

	class _ClientList:
		def __init__(self) -> None:
			async def _create(**kwargs: Any) -> Any:
				_ = kwargs
				return _ListResponse()

			self.messages = SimpleNamespace(create=_create)

	monkeypatch.setattr(
		am.BaseAnthropicAdapter,
		"_get_client",
		lambda self: _ClientList(),
	)
	adapter_list = AnthropicMessagesAdapter()
	msg_list = await adapter_list.generate(
		[UserMessage.from_text("u")],
		model="claude",
		params=params,
		tools=[
			ToolDefinition(
				name="t",
				description="d",
				parameters={"type": "object"},
			)
		],
	)
	assert msg_list.text == "[1]"

	# response_model parsing: invalid json -> TextContent
	class _BadJsonResponse:
		def __init__(self) -> None:
			self.content = [_TextBlock("{bad")]
			self.usage = _Usage()

	class _Client3:
		def __init__(self) -> None:
			async def _create(**kwargs: Any) -> Any:
				_ = kwargs
				return _BadJsonResponse()

			self.messages = SimpleNamespace(create=_create)

	monkeypatch.setattr(
		am.BaseAnthropicAdapter,
		"_get_client",
		lambda self: _Client3(),
	)
	adapter_bad = AnthropicMessagesAdapter()
	msg_bad = await adapter_bad.generate(
		[UserMessage.from_text("u")],
		model="claude",
		params=params,
	)
	assert msg_bad.text == "{bad"

	# response_model parsing: empty combined text should not attempt json parsing
	class _EmptyTextResponse:
		def __init__(self) -> None:
			self.content = [_TextBlock("")]
			self.usage = _Usage()

	class _ClientEmptyText:
		def __init__(self) -> None:
			async def _create(**kwargs: Any) -> Any:
				_ = kwargs
				return _EmptyTextResponse()

			self.messages = SimpleNamespace(create=_create)

	monkeypatch.setattr(
		am.BaseAnthropicAdapter,
		"_get_client",
		lambda self: _ClientEmptyText(),
	)
	adapter_empty = AnthropicMessagesAdapter()
	msg_empty = await adapter_empty.generate(
		[UserMessage.from_text("u")],
		model="claude",
		params=params,
	)
	assert msg_empty.text == ""

	# streaming
	class _DummyStreamClient:
		def __init__(self) -> None:
			async def _create(**kwargs: Any) -> Any:
				_ = kwargs
				return _DummyAsyncIterator(
					[
						object(),
						_StartEvent(0, _TextBlock("skip")),
						_StartEvent(0, _ToolUseBlock("t2", "tool2")),
						# this delta has no start state and should be ignored
						_DeltaEvent(1, _InputJSONDelta("{")),
						_DeltaEvent(0, object()),
						_DeltaEvent(0, _TextDelta("")),
						_DeltaEvent(0, _TextDelta("a")),
						_DeltaEvent(0, _InputJSONDelta("{")),
						_DeltaEvent(0, _InputJSONDelta("}")),
						_StopEvent(0),
						# this stop has no state and should be ignored
						_StopEvent(1),
					]
				)

			self.messages = SimpleNamespace(create=_create)

	monkeypatch.setattr(
		am.BaseAnthropicAdapter,
		"_get_client",
		lambda self: _DummyStreamClient(),
	)
	adapter2 = AnthropicMessagesAdapter()
	seen_text = ""
	seen_tool = False
	seen_tool_args: list[str] = []
	async for delta in adapter2.generate(
		[UserMessage.from_text("u")],
		model="claude",
		stream=True,
		params=am.ChatGenerationParams(tool_choice="auto"),
		tools=[
			ToolDefinition(
				name="t",
				description="d",
				parameters={"type": "object"},
			)
		],
	):
		seen_text += delta.text
		if delta.tool_calls:
			seen_tool = True
			for tc in delta.tool_calls:
				if isinstance(tc.arguments, str) and tc.arguments:
					seen_tool_args.append(tc.arguments)
	assert seen_text == "a"
	assert seen_tool is True
	# tool call arguments are now streamed per JSON delta fragment
	assert "{" in seen_tool_args
	assert "}" in seen_tool_args

	# cover tools present but tool_choice is None
	seen_text2 = ""
	async for delta in adapter2.generate(
		[UserMessage.from_text("u")],
		model="claude",
		stream=True,
		params=am.ChatGenerationParams(tool_choice=None),
		tools=[
			ToolDefinition(
				name="t",
				description="d",
				parameters={"type": "object"},
			)
		],
	):
		seen_text2 += delta.text
	assert "a" in seen_text2


def test_anthropic_messages_to_anthropic_json_and_tool_result_blocks() -> None:
	assistant = AssistantMessage(content=[JsonContent(data={"x": 1})])
	assert assistant.text == ""
	sys = SystemMessage.from_text("a")
	user = UserMessage.from_text("u")
	tool_msg = ToolMessage(
		tool_call_id="x",
		tool_output="ok",
		is_error=True,
		metadata={
			"_provider_data": {
				"anthropic.messages": {
					"tool_call_id": "tid",
				}
			}
		},
	)
	system_text, msgs = _messages_to_anthropic([sys, user, assistant, tool_msg])
	assert system_text == "a"
	assert any(m["role"] == "assistant" for m in msgs)
	assert any(m["role"] == "user" for m in msgs)
