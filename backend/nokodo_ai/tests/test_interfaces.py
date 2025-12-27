"""tests for SDK high-level interfaces."""

from collections.abc import AsyncIterator, Awaitable

import pytest

from nokodo_ai import (
	AssistantMessage,
	ChatModel,
	EmbeddingModel,
	Thread,
	UserMessage,
	tool,
)
from nokodo_ai.adapters.chat import BaseChatAdapter, ChatGenerationParams
from nokodo_ai.adapters.embedding import BaseEmbeddingAdapter


def test_llm_requires_model() -> None:
	with pytest.raises(ValueError, match="model must be provided"):
		ChatModel()


def test_llm_resolves_openai_model() -> None:
	llm = ChatModel(model="gpt-4o")
	from nokodo_ai.adapters.openai import OpenAIChatCompletionsAdapter

	assert isinstance(llm._adapter_resolved, OpenAIChatCompletionsAdapter)
	assert llm._adapter_resolved.model == "gpt-4o"


def test_llm_resolves_openai_explicit() -> None:
	llm = ChatModel(model="openai:gpt-4o-mini")
	from nokodo_ai.adapters.openai import OpenAIChatCompletionsAdapter

	assert isinstance(llm._adapter_resolved, OpenAIChatCompletionsAdapter)
	assert llm._adapter_resolved.model == "gpt-4o-mini"


def test_llm_resolves_openai_responses_api() -> None:
	llm = ChatModel(model="openai.responses:gpt-4o")
	from nokodo_ai.adapters.openai import OpenAIResponsesAdapter

	assert isinstance(llm._adapter_resolved, OpenAIResponsesAdapter)


def test_llm_resolves_anthropic() -> None:
	llm = ChatModel(model="anthropic:claude-sonnet-4-20250514")
	from nokodo_ai.adapters.anthropic import AnthropicMessagesAdapter

	assert isinstance(llm._adapter_resolved, AnthropicMessagesAdapter)


def test_llm_resolves_ollama() -> None:
	llm = ChatModel(model="ollama:llama3.2")
	from nokodo_ai.adapters.ollama import OllamaChatAdapter

	assert isinstance(llm._adapter_resolved, OllamaChatAdapter)


def test_llm_unknown_provider_raises() -> None:
	with pytest.raises(ValueError, match="unknown provider"):
		ChatModel(model="unknownprovider:model")


def test_embedding_requires_model_or_adapter() -> None:
	with pytest.raises(ValueError, match="model must be provided"):
		EmbeddingModel()


def test_embedding_resolves_openai() -> None:
	embedder = EmbeddingModel("openai:text-embedding-3-large")
	from nokodo_ai.adapters.openai import OpenAIEmbeddingAdapter

	assert isinstance(embedder._adapter, OpenAIEmbeddingAdapter)


def test_embedding_resolves_ollama() -> None:
	embedder = EmbeddingModel("ollama:nomic-embed-text")
	from nokodo_ai.adapters.ollama import OllamaEmbeddingAdapter

	assert isinstance(embedder._adapter, OllamaEmbeddingAdapter)


def test_embedding_unknown_provider_raises() -> None:
	with pytest.raises(ValueError, match="unknown embedding provider"):
		EmbeddingModel("unknownprovider:model")


class _StubChatAdapter(BaseChatAdapter):
	def __init__(
		self,
		response: AssistantMessage,
		*,
		stream_chunks: list[AssistantMessage] | None = None,
	) -> None:
		self.response = response
		self.stream_chunks = stream_chunks or []
		self.calls: list[dict[str, object]] = []

	def generate(
		self,
		messages: list[UserMessage],
		*,
		stream: bool = False,
		tools=None,
		params: ChatGenerationParams | None = None,
	) -> Awaitable[AssistantMessage] | AsyncIterator[AssistantMessage]:
		params = params or ChatGenerationParams()
		call = {
			"messages": messages,
			"stream": stream,
			"tools": tools,
			"params": params,
		}
		self.calls.append(call)
		if stream:

			async def _gen() -> AsyncIterator[AssistantMessage]:
				for chunk in self.stream_chunks:
					yield chunk

			return _gen()

		async def _resp() -> AssistantMessage:
			return self.response

		return _resp()


class _StubEmbeddingAdapter(BaseEmbeddingAdapter):
	def __init__(self) -> None:
		self.seen: list[list[str]] = []

	async def embed(self, texts: list[str]) -> list[list[float]]:
		self.seen.append(texts)
		return [[float(len(t))] for t in texts]


@pytest.mark.asyncio
async def test_chat_model_generate_with_thread(monkeypatch: pytest.MonkeyPatch) -> None:
	adapter = _StubChatAdapter(AssistantMessage.from_text("ok"))
	llm = ChatModel(model="stub", adapter=adapter)
	thread = Thread()
	thread.add(UserMessage.from_text("hi"))

	result = await llm.generate(thread)

	assert result.text == "ok"
	call = adapter.calls[-1]
	assert call["messages"] == thread.messages
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
	llm = ChatModel(model="stub", adapter=adapter)

	@tool(description="noop")
	def noop() -> str:
		return "ok"

	chunks = [
		chunk
		async for chunk in llm.generate(
			[UserMessage.from_text("hi")],
			stream=True,
			tools=[noop],
			params=ChatGenerationParams(),
		)
	]

	assert [c.text for c in chunks] == ["c1", "c2"]
	call = adapter.calls[-1]
	assert call["stream"] is True
	params = call["params"]
	assert isinstance(params, ChatGenerationParams)
	assert params.tool_choice == "auto"


@pytest.mark.asyncio
async def test_chat_model_parses_params_dict() -> None:
	adapter = _StubChatAdapter(AssistantMessage.from_text("ok"))
	llm = ChatModel(model="stub", adapter=adapter)

	result = await llm.generate(
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
async def test_chat_model_resolves_default_provider(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	adapter = _StubChatAdapter(AssistantMessage.from_text("resolved"))

	def fake_get_chat_adapter(variant: str | None, model: str):
		assert variant is None
		assert model == "gpt-4o"
		return adapter

	monkeypatch.setattr(
		"nokodo_ai.adapters.openai.get_chat_adapter", fake_get_chat_adapter
	)
	llm = ChatModel(model="gpt-4o")

	result = await llm.generate([UserMessage.from_text("hi")])
	assert result.text == "resolved"


@pytest.mark.asyncio
async def test_embedding_uses_provided_adapter() -> None:
	adapter = _StubEmbeddingAdapter()
	embedder = EmbeddingModel(model="custom", adapter=adapter)
	result = await embedder.embed(["a", "bc"])

	assert result == [[1.0], [2.0]]
	assert adapter.seen[-1] == ["a", "bc"]


@pytest.mark.asyncio
async def test_embedding_resolves_default_provider(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	adapter = _StubEmbeddingAdapter()

	def fake_get_embedding_adapter(variant: str | None, model: str):
		assert variant is None
		assert model == "text-embedding-3-small"
		return adapter

	monkeypatch.setattr(
		"nokodo_ai.adapters.openai.get_embedding_adapter", fake_get_embedding_adapter
	)
	embedder = EmbeddingModel("text-embedding-3-small")

	result = await embedder.embed(["hi"])
	assert result == [[2.0]]


@pytest.mark.asyncio
async def test_embedding_variant_is_forwarded(monkeypatch: pytest.MonkeyPatch) -> None:
	adapter = _StubEmbeddingAdapter()
	seen: list[tuple[str | None, str]] = []

	def fake_get_embedding_adapter(variant: str | None, model: str):
		seen.append((variant, model))
		return adapter

	monkeypatch.setattr(
		"nokodo_ai.adapters.openai.get_embedding_adapter", fake_get_embedding_adapter
	)
	embedder = EmbeddingModel("openai.beta:text-embedding-3-large")

	result = await embedder.embed(["hi"])
	assert result == [[2.0]]
	assert seen == [("beta", "text-embedding-3-large")]
