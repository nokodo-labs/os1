"""unit coverage for embedding token counting (exact vs estimate fallback)."""

from __future__ import annotations

from nokodo_ai.adapters.ollama.embeddings import OllamaEmbeddingsAdapter
from nokodo_ai.adapters.openai.embeddings import OpenAIEmbeddingsAdapter
from nokodo_ai.embeddings import EmbeddingModel


def test_openai_adapter_counts_tokens_exactly() -> None:
	adapter = OpenAIEmbeddingsAdapter(api_key="test")
	counts = adapter.count_tokens(["hello world", ""], model="text-embedding-3-small")
	assert counts == [2, 0]


def test_openai_adapter_unknown_model_falls_back() -> None:
	adapter = OpenAIEmbeddingsAdapter(api_key="test")
	counts = adapter.count_tokens(["hello world"], model="not-a-real-model")
	assert counts == [2]


def test_ollama_adapter_has_no_tokenizer() -> None:
	adapter = OllamaEmbeddingsAdapter()
	assert adapter.count_tokens(["hello world"], model="nomic-embed-text") is None


def test_embedding_model_delegates_exact_count() -> None:
	model = EmbeddingModel.create(
		"text-embedding-3-small",
		adapter={"type": "openai.embedding", "api_key": "test"},
	)
	assert model.count_tokens(["hello world"]) == [2]


def test_embedding_model_delegates_none_when_unsupported() -> None:
	model = EmbeddingModel.create(
		"nomic-embed-text",
		adapter={"type": "ollama.embedding"},
	)
	assert model.count_tokens(["hello world"]) is None
