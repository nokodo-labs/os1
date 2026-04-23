"""tests for SDK high-level interfaces."""

from collections.abc import AsyncIterator, Awaitable

import pytest
from pydantic import PrivateAttr, ValidationError

from nokodo_ai import (
	AssistantMessage,
	ChatModel,
	EmbeddingModel,
	Thread,
	ToolMessage,
	UserMessage,
	tool,
)
from nokodo_ai.adapters.chat import BaseChatAdapter, ChatGenerationParams
from nokodo_ai.adapters.embeddings import BaseEmbeddingAdapter
from nokodo_ai.context import AgentContext
from nokodo_ai.tool import ToolDefinition


def test_chat_model_requires_model() -> None:
	with pytest.raises(ValidationError):
		ChatModel.model_validate({})


def test_chat_model_resolves_openai_model() -> None:
	chat_model = ChatModel.model_validate(
		{
			"model_name": "gpt-4o",
			"adapter": {"type": "openai.chat_completions", "api_key": "test"},
		}
	)
	from nokodo_ai.adapters.openai import OpenAIChatCompletionsAdapter

	assert isinstance(chat_model.adapter, OpenAIChatCompletionsAdapter)


def test_chat_model_adapter_shorthand_resolves_to_full_type() -> None:
	"""shorthand provider name in adapter type resolves to default adapter."""
	chat_model = ChatModel.create(
		"gpt-4o",
		adapter={"type": "openai", "api_key": "test"},
	)
	from nokodo_ai.adapters.openai import OpenAIChatCompletionsAdapter

	assert isinstance(chat_model.adapter, OpenAIChatCompletionsAdapter)
	assert chat_model.adapter.type.startswith("openai.")


def test_chat_model_resolves_openai_explicit() -> None:
	chat_model = ChatModel.model_validate(
		{
			"model_name": "gpt-4o-mini",
			"adapter": {"type": "openai.chat_completions", "api_key": "test"},
		}
	)
	from nokodo_ai.adapters.openai import OpenAIChatCompletionsAdapter

	assert isinstance(chat_model.adapter, OpenAIChatCompletionsAdapter)


def test_chat_model_resolves_openai_responses_api() -> None:
	chat_model = ChatModel.model_validate(
		{
			"model_name": "gpt-4o",
			"adapter": {"type": "openai.responses", "api_key": "test"},
		}
	)
	from nokodo_ai.adapters.openai import OpenAIResponsesAdapter

	assert isinstance(chat_model.adapter, OpenAIResponsesAdapter)


def test_chat_model_resolves_anthropic() -> None:
	chat_model = ChatModel.model_validate(
		{
			"model_name": "claude-sonnet-4-20250514",
			"adapter": {"type": "anthropic.messages", "api_key": "test"},
		}
	)
	from nokodo_ai.adapters.anthropic import AnthropicMessagesAdapter

	assert isinstance(chat_model.adapter, AnthropicMessagesAdapter)


def test_chat_model_resolves_ollama() -> None:
	chat_model = ChatModel.model_validate(
		{"model_name": "llama3.2", "adapter": {"type": "ollama.chat"}}
	)
	from nokodo_ai.adapters.ollama import OllamaChatAdapter

	assert isinstance(chat_model.adapter, OllamaChatAdapter)


def test_chat_model_resolves_google() -> None:
	chat_model = ChatModel.model_validate(
		{
			"model_name": "gemini-2.0-flash-001",
			"adapter": {"type": "google.generate_content", "api_key": "test"},
		}
	)
	from nokodo_ai.adapters.google import GoogleGenerateContentAdapter

	assert isinstance(chat_model.adapter, GoogleGenerateContentAdapter)


def test_chat_model_unknown_provider_raises() -> None:
	with pytest.raises(ValidationError):
		ChatModel.model_validate(
			{
				"model_name": "model",
				"adapter": {"type": "unknownprovider.model"},
			}
		)


def test_embedding_requires_model_or_adapter() -> None:
	with pytest.raises(ValidationError):
		EmbeddingModel()  # type: ignore[call-arg]


def test_embedding_resolves_openai() -> None:
	embedder = EmbeddingModel.model_validate(
		{
			"model_name": "text-embedding-3-large",
			"adapter": {"type": "openai.embedding", "api_key": "test"},
		}
	)
	from nokodo_ai.adapters.openai import OpenAIEmbeddingsAdapter

	assert isinstance(embedder.adapter, OpenAIEmbeddingsAdapter)


def test_embedding_resolves_ollama() -> None:
	embedder = EmbeddingModel.model_validate(
		{"model_name": "nomic-embed-text", "adapter": {"type": "ollama.embedding"}}
	)
	from nokodo_ai.adapters.ollama import OllamaEmbeddingsAdapter

	assert isinstance(embedder.adapter, OllamaEmbeddingsAdapter)


def test_embedding_unknown_provider_raises() -> None:
	with pytest.raises(ValidationError):
		EmbeddingModel.model_validate(
			{
				"model_name": "model",
				"adapter": {"type": "unknownprovider.embedding"},
			}
		)


class _StubChatAdapter(BaseChatAdapter):
	_response: AssistantMessage = PrivateAttr()
	_stream_chunks: list[AssistantMessage] = PrivateAttr(default_factory=list)
	_calls: list[dict[str, object]] = PrivateAttr(default_factory=list)

	def __init__(
		self,
		response: AssistantMessage,
		*,
		stream_chunks: list[AssistantMessage] | None = None,
	) -> None:
		super().__init__()
		self._response = response
		self._stream_chunks = stream_chunks or []

	@property
	def calls(self) -> list[dict[str, object]]:
		return self._calls

	def generate(  # type: ignore[override]
		self,
		messages: list[UserMessage],
		*,
		model: str,
		stream: bool = False,
		tools: list[ToolDefinition] | None = None,
		params: ChatGenerationParams | None = None,
	) -> Awaitable[AssistantMessage] | AsyncIterator[AssistantMessage]:
		params = params or ChatGenerationParams()
		call = {
			"messages": messages,
			"model": model,
			"stream": stream,
			"tools": tools,
			"params": params,
		}
		self._calls.append(call)
		if stream:

			async def _gen() -> AsyncIterator[AssistantMessage]:
				for chunk in self._stream_chunks:
					yield chunk

			return _gen()

		async def _resp() -> AssistantMessage:
			return self._response

		return _resp()


class _StubEmbeddingAdapter(BaseEmbeddingAdapter):
	def __init__(self) -> None:
		self.seen: list[list[str]] = []
		self.seen_models: list[str] = []

	async def embed(self, texts: list[str], *, model: str) -> list[list[float]]:
		self.seen.append(texts)
		self.seen_models.append(model)
		return [[float(len(t))] for t in texts]


@pytest.mark.asyncio
async def test_chat_model_generate_with_thread(monkeypatch: pytest.MonkeyPatch) -> None:
	adapter = _StubChatAdapter(AssistantMessage.from_text("ok"))
	chat_model = ChatModel.model_construct(
		model_name="stub",
		adapter=adapter,
	)
	thread = Thread()
	thread.add(UserMessage.from_text("hi"))

	result = await chat_model.generate(thread)

	assert result.text == "ok"
	call = adapter.calls[-1]
	assert call["messages"] == thread.messages
	assert call["model"] == "stub"
	params = call["params"]
	assert isinstance(params, ChatGenerationParams)
	assert params.tool_choice is None
	assert call["stream"] is False


@pytest.mark.asyncio
async def test_chat_model_streaming_with_tools() -> None:
	adapter = _StubChatAdapter(
		AssistantMessage.from_text("unused"),
		stream_chunks=[
			AssistantMessage.from_text("c1"),
			AssistantMessage.from_text("c2"),
		],
	)
	chat_model = ChatModel.model_construct(
		model_name="stub",
		adapter=adapter,
	)

	@tool(description="noop")
	def noop(
		__agent_context__: AgentContext,
		__app_context__: None,
	) -> ToolMessage:
		return ToolMessage(
			tool_call_id=__agent_context__.tool_call_id,
			tool_output="ok",
		)

	chunks = [
		delta
		async for delta in chat_model.generate(
			[UserMessage.from_text("hi")],
			stream=True,
			tools=[noop],  # type: ignore[call-overload]
			params=ChatGenerationParams(),
		)
	]
	message_chunks = [d.message for d in chunks if not d.done]

	assert [c.text for c in message_chunks] == ["c1", "c2"]
	call = adapter.calls[-1]
	assert call["stream"] is True
	assert call["model"] == "stub"
	params = call["params"]
	assert isinstance(params, ChatGenerationParams)
	assert params.tool_choice == "auto"


@pytest.mark.asyncio
async def test_chat_model_parses_params_dict() -> None:
	adapter = _StubChatAdapter(AssistantMessage.from_text("ok"))
	chat_model = ChatModel.model_construct(
		model_name="stub",
		adapter=adapter,
	)

	result = await chat_model.generate(
		[UserMessage.from_text("hi")],
		params={"temperature": 0.123, "max_tokens": 7},
	)
	assert result.text == "ok"
	call = adapter.calls[-1]
	params = call["params"]
	assert isinstance(params, ChatGenerationParams)
	assert params.temperature == 0.123
	assert params.max_tokens == 7


@pytest.mark.asyncio
async def test_chat_model_rejects_provider_fields() -> None:
	with pytest.raises(ValidationError):
		ChatModel.model_validate(
			{
				"provider": "openai",
				"variant": None,
				"model_name": "gpt-4o",
				"adapter": {"type": "openai.chat_completions", "api_key": "test"},
			}
		)


@pytest.mark.asyncio
async def test_embedding_uses_provided_adapter() -> None:
	adapter = _StubEmbeddingAdapter()
	embedder = EmbeddingModel.model_construct(
		model_name="custom",
		adapter=adapter,
	)
	result = await embedder.embed(["a", "bc"])

	assert result == [[1.0], [2.0]]
	assert adapter.seen[-1] == ["a", "bc"]


@pytest.mark.asyncio
async def test_embedding_rejects_provider_fields() -> None:
	with pytest.raises(ValidationError):
		EmbeddingModel.model_validate(
			{
				"provider": "openai",
				"variant": None,
				"model_name": "text-embedding-3-small",
				"adapter": {"type": "openai.embedding", "api_key": "test"},
			}
		)


@pytest.mark.asyncio
async def test_embedding_rejects_variant_field() -> None:
	with pytest.raises(ValidationError):
		EmbeddingModel.model_validate(
			{
				"variant": "beta",
				"model_name": "text-embedding-3-large",
				"adapter": {"type": "openai.embedding", "api_key": "test"},
			}
		)
