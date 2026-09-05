"""voyageai reranker adapter."""

from typing import Literal

from pydantic import Field

from ..base.rerankers import BaseRerankerAdapter, RerankResult
from .base import BaseVoyageAIAdapter


class VoyageAIRerankerAdapter(BaseVoyageAIAdapter, BaseRerankerAdapter):
	"""adapter for voyageai's rerank API."""

	type: Literal["voyageai.rerank"] = "voyageai.rerank"
	truncation: bool = Field(
		default=True,
		description="truncate over-length documents to fit the model context",
	)

	async def rerank(
		self,
		query: str,
		documents: list[str],
		model: str,
		top_k: int | None = None,
	) -> list[RerankResult]:
		result = await self._client.rerank(
			query, documents, model=model, top_k=top_k, truncation=self.truncation
		)
		return [
			RerankResult(index=r.index, score=float(r.relevance_score))
			for r in result.results
		]
