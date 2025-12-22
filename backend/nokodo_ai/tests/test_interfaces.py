"""tests for SDK high-level interfaces."""

import pytest

from nokodo_ai import ChatModel, EmbeddingModel


def test_llm_requires_model() -> None:
	with pytest.raises(ValueError, match="model must be provided"):
		ChatModel()


def test_llm_resolves_openai_model() -> None:
	llm = ChatModel("gpt-4o")
	from nokodo_ai.adapters.openai import OpenAIChatCompletionsAdapter

	assert isinstance(llm._adapter, OpenAIChatCompletionsAdapter)
	assert llm._adapter.model == "gpt-4o"


def test_llm_resolves_openai_explicit() -> None:
	llm = ChatModel("openai:gpt-4o-mini")
	from nokodo_ai.adapters.openai import OpenAIChatCompletionsAdapter

	assert isinstance(llm._adapter, OpenAIChatCompletionsAdapter)
	assert llm._adapter.model == "gpt-4o-mini"


def test_llm_resolves_openai_responses_api() -> None:
	llm = ChatModel("openai.responses:gpt-4o")
	from nokodo_ai.adapters.openai import OpenAIResponsesAdapter

	assert isinstance(llm._adapter, OpenAIResponsesAdapter)


def test_llm_resolves_anthropic() -> None:
	llm = ChatModel("anthropic:claude-sonnet-4-20250514")
	from nokodo_ai.adapters.anthropic import AnthropicMessagesAdapter

	assert isinstance(llm._adapter, AnthropicMessagesAdapter)


def test_llm_resolves_ollama() -> None:
	llm = ChatModel("ollama:llama3.2")
	from nokodo_ai.adapters.ollama import OllamaChatAdapter

	assert isinstance(llm._adapter, OllamaChatAdapter)


def test_llm_unknown_provider_raises() -> None:
	with pytest.raises(ValueError, match="unknown provider"):
		ChatModel("unknownprovider:model")


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
