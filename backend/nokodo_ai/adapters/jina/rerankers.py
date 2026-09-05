"""jina reranker adapter."""

from typing import Any, Literal

from ..base.rerankers import BaseRerankerAdapter, RerankResult
from .base import BaseJinaAdapter


class JinaRerankerAdapter(BaseJinaAdapter, BaseRerankerAdapter):
	"""adapter for jina's rerank API and jina-compatible rerank endpoints."""

	type: Literal["jina.rerank"] = "jina.rerank"

	async def rerank(
		self,
		query: str,
		documents: list[str],
		model: str,
		top_k: int | None = None,
	) -> list[RerankResult]:
		# strict common-denominator body accepted by jina v1 and cohere
		# v2 shaped endpoints alike (jina.ai, vllm, llama.cpp, TEI, ...)
		payload: dict[str, Any] = {
			"model": model,
			"query": query,
			"documents": documents,
		}
		if top_k is not None:
			payload["top_n"] = top_k

		response = await self._client.post("/rerank", json=payload)
		response.raise_for_status()
		data = response.json()

		results = [
			RerankResult(index=int(r["index"]), score=float(r["relevance_score"]))
			for r in data["results"]
		]
		# self-hosted jina-compatible servers differ in whether results come
		# back sorted and whether top_n is honored; enforce the contract here
		results.sort(key=lambda r: r.score, reverse=True)
		if top_k is not None:
			results = results[:top_k]
		return results
