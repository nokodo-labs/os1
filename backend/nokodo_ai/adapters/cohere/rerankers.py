"""cohere reranker adapter."""

from typing import Any, Literal

from pydantic import Field

from ..base.rerankers import BaseRerankerAdapter, RerankResult
from .base import BaseCohereAdapter


class CohereRerankerAdapter(BaseCohereAdapter, BaseRerankerAdapter):
	"""adapter for cohere's rerank API."""

	type: Literal["cohere.rerank"] = "cohere.rerank"
	max_tokens_per_doc: int | None = Field(
		default=None,
		description="token budget per document; longer documents are truncated",
	)

	async def rerank(
		self,
		query: str,
		documents: list[str],
		model: str,
		top_k: int | None = None,
	) -> list[RerankResult]:
		kwargs: dict[str, Any] = {}
		if top_k is not None:
			kwargs["top_n"] = top_k
		if self.max_tokens_per_doc is not None:
			kwargs["max_tokens_per_doc"] = self.max_tokens_per_doc

		response = await self._client.rerank(
			model=model, query=query, documents=documents, **kwargs
		)
		return [
			RerankResult(index=r.index, score=float(r.relevance_score))
			for r in response.results
		]
