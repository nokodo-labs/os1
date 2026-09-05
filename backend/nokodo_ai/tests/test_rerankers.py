"""tests for the reranker interface and adapters."""

from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import ValidationError

from nokodo_ai import Reranker, RerankResult
from nokodo_ai.adapters.cohere.base import BaseCohereAdapter
from nokodo_ai.adapters.cohere.rerankers import CohereRerankerAdapter
from nokodo_ai.adapters.jina.base import BaseJinaAdapter
from nokodo_ai.adapters.jina.rerankers import JinaRerankerAdapter
from nokodo_ai.adapters.voyageai.base import BaseVoyageAIAdapter
from nokodo_ai.adapters.voyageai.rerankers import VoyageAIRerankerAdapter


def test_reranker_requires_model() -> None:
	with pytest.raises(ValidationError):
		Reranker.model_validate({})


def test_reranker_resolves_voyageai_explicit() -> None:
	reranker = Reranker.model_validate(
		{
			"model_name": "rerank-2.5",
			"adapter": {"type": "voyageai.rerank", "api_key": "test"},
		}
	)
	assert isinstance(reranker.adapter, VoyageAIRerankerAdapter)


def test_reranker_adapter_shorthand_resolves_to_full_type() -> None:
	reranker = Reranker.create(
		"rerank-2.5",
		adapter={"type": "voyageai", "api_key": "test"},
	)
	assert isinstance(reranker.adapter, VoyageAIRerankerAdapter)
	assert reranker.adapter.type == "voyageai.rerank"


def test_reranker_resolves_cohere_explicit() -> None:
	reranker = Reranker.model_validate(
		{
			"model_name": "rerank-v3.5",
			"adapter": {"type": "cohere.rerank", "api_key": "test"},
		}
	)
	assert isinstance(reranker.adapter, CohereRerankerAdapter)


def test_reranker_adapter_shorthand_resolves_cohere() -> None:
	reranker = Reranker.create(
		"rerank-v3.5",
		adapter={"type": "cohere", "api_key": "test"},
	)
	assert isinstance(reranker.adapter, CohereRerankerAdapter)
	assert reranker.adapter.type == "cohere.rerank"


def test_reranker_resolves_jina_explicit() -> None:
	reranker = Reranker.model_validate(
		{
			"model_name": "jina-reranker-v3",
			"adapter": {"type": "jina.rerank", "api_key": "test"},
		}
	)
	assert isinstance(reranker.adapter, JinaRerankerAdapter)


def test_reranker_adapter_shorthand_resolves_jina() -> None:
	reranker = Reranker.create(
		"jina-reranker-v3",
		adapter={"type": "jina", "api_key": "test"},
	)
	assert isinstance(reranker.adapter, JinaRerankerAdapter)
	assert reranker.adapter.type == "jina.rerank"


def test_reranker_unknown_provider_raises() -> None:
	with pytest.raises(ValidationError):
		Reranker.model_validate(
			{
				"model_name": "model",
				"adapter": {"type": "unknownprovider"},
			}
		)


@pytest.mark.asyncio
async def test_voyageai_rerank_maps_results(monkeypatch: pytest.MonkeyPatch) -> None:
	captured: dict[str, Any] = {}

	async def _rerank(query: str, documents: list[str], **kwargs: Any) -> Any:
		captured["query"] = query
		captured["documents"] = documents
		captured.update(kwargs)
		return SimpleNamespace(
			results=[
				SimpleNamespace(index=1, relevance_score=0.9),
				SimpleNamespace(index=0, relevance_score=0.2),
			]
		)

	dummy = SimpleNamespace(rerank=_rerank)
	monkeypatch.setattr(BaseVoyageAIAdapter, "_get_client", lambda self: dummy)

	reranker = Reranker.create(
		"rerank-2.5",
		adapter={"type": "voyageai", "api_key": "test"},
	)
	results = await reranker.rerank("q", ["a", "b"], top_k=2)

	assert captured["query"] == "q"
	assert captured["documents"] == ["a", "b"]
	assert captured["model"] == "rerank-2.5"
	assert captured["top_k"] == 2
	assert captured["truncation"] is True
	assert results == [
		RerankResult(index=1, score=0.9),
		RerankResult(index=0, score=0.2),
	]


@pytest.mark.asyncio
async def test_voyageai_rerank_defaults_top_k_none(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	captured: dict[str, Any] = {}

	async def _rerank(query: str, documents: list[str], **kwargs: Any) -> Any:
		_ = (query, documents)
		captured.update(kwargs)
		return SimpleNamespace(results=[])

	dummy = SimpleNamespace(rerank=_rerank)
	monkeypatch.setattr(BaseVoyageAIAdapter, "_get_client", lambda self: dummy)

	reranker = Reranker.create(
		"rerank-2.5-lite",
		adapter={"type": "voyageai", "api_key": "test"},
	)
	results = await reranker.rerank("q", ["a"])

	assert captured["top_k"] is None
	assert results == []


@pytest.mark.asyncio
async def test_cohere_rerank_maps_results(monkeypatch: pytest.MonkeyPatch) -> None:
	captured: dict[str, Any] = {}

	async def _rerank(**kwargs: Any) -> Any:
		captured.update(kwargs)
		return SimpleNamespace(
			results=[
				SimpleNamespace(index=2, relevance_score=0.95),
				SimpleNamespace(index=0, relevance_score=0.4),
			]
		)

	dummy = SimpleNamespace(rerank=_rerank)
	monkeypatch.setattr(BaseCohereAdapter, "_get_client", lambda self: dummy)

	reranker = Reranker.create(
		"rerank-v3.5",
		adapter={"type": "cohere", "api_key": "test", "max_tokens_per_doc": 2048},
	)
	results = await reranker.rerank("q", ["a", "b", "c"], top_k=2)

	assert captured["model"] == "rerank-v3.5"
	assert captured["query"] == "q"
	assert captured["documents"] == ["a", "b", "c"]
	assert captured["top_n"] == 2
	assert captured["max_tokens_per_doc"] == 2048
	assert results == [
		RerankResult(index=2, score=0.95),
		RerankResult(index=0, score=0.4),
	]


@pytest.mark.asyncio
async def test_cohere_rerank_omits_unset_options(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	captured: dict[str, Any] = {}

	async def _rerank(**kwargs: Any) -> Any:
		captured.update(kwargs)
		return SimpleNamespace(results=[])

	dummy = SimpleNamespace(rerank=_rerank)
	monkeypatch.setattr(BaseCohereAdapter, "_get_client", lambda self: dummy)

	reranker = Reranker.create(
		"rerank-v3.5",
		adapter={"type": "cohere", "api_key": "test"},
	)
	results = await reranker.rerank("q", ["a"])

	assert "top_n" not in captured
	assert "max_tokens_per_doc" not in captured
	assert results == []


class _FakeJinaResponse:
	def __init__(self, data: Any) -> None:
		self._data = data

	def raise_for_status(self) -> None:
		pass

	def json(self) -> Any:
		return self._data


@pytest.mark.asyncio
async def test_jina_rerank_posts_payload_and_enforces_contract(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	captured: dict[str, Any] = {}

	class _FakeClient:
		async def post(self, url: str, json: Any) -> Any:
			captured["url"] = url
			captured["payload"] = json
			return _FakeJinaResponse(
				{
					"results": [
						{"index": 0, "relevance_score": 0.2},
						{"index": 1, "relevance_score": 0.9},
						{"index": 2, "relevance_score": 0.5},
					]
				}
			)

	monkeypatch.setattr(BaseJinaAdapter, "_get_client", lambda self: _FakeClient())

	reranker = Reranker.create(
		"jina-reranker-v3",
		adapter={"type": "jina", "api_key": "test"},
	)
	results = await reranker.rerank("q", ["a", "b", "c"], top_k=2)

	assert captured["url"] == "/rerank"
	assert captured["payload"]["model"] == "jina-reranker-v3"
	assert captured["payload"]["query"] == "q"
	assert captured["payload"]["documents"] == ["a", "b", "c"]
	assert captured["payload"]["top_n"] == 2
	assert "return_documents" not in captured["payload"]
	# unsorted server results are sorted by score and cut to top_k
	assert results == [
		RerankResult(index=1, score=0.9),
		RerankResult(index=2, score=0.5),
	]


@pytest.mark.asyncio
async def test_jina_rerank_omits_top_n_when_unset(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	captured: dict[str, Any] = {}

	class _FakeClient:
		async def post(self, url: str, json: Any) -> Any:
			captured["payload"] = json
			return _FakeJinaResponse(
				{"results": [{"index": 0, "relevance_score": 0.7}]}
			)

	monkeypatch.setattr(BaseJinaAdapter, "_get_client", lambda self: _FakeClient())

	reranker = Reranker.create(
		"jina-reranker-v3",
		adapter={"type": "jina", "api_key": "test"},
	)
	results = await reranker.rerank("q", ["a"])

	assert "top_n" not in captured["payload"]
	assert results == [RerankResult(index=0, score=0.7)]


@pytest.mark.asyncio
async def test_jina_client_defaults_and_auth() -> None:
	adapter = JinaRerankerAdapter(api_key="k")
	assert str(adapter._client.base_url) == "https://api.jina.ai/v1/"
	assert adapter._client.headers["authorization"] == "Bearer k"
	await adapter.close()


@pytest.mark.asyncio
async def test_jina_client_custom_base_url_without_key() -> None:
	adapter = JinaRerankerAdapter(base_url="http://localhost:8000/v1")
	assert str(adapter._client.base_url) == "http://localhost:8000/v1/"
	assert "authorization" not in adapter._client.headers
	await adapter.close()
