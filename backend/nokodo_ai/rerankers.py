"""Reranker high-level interface - unified access to reranking models."""

from typing import Any, ClassVar

from pydantic import ConfigDict, Field

from .adapter_enabled import AdapterEnabledBase, AdapterResolver
from .adapters.base.rerankers import RerankResult
from .adapters.rerankers import (
	RerankerAdapter,
	resolve_reranker_adapter,
)


class Reranker(AdapterEnabledBase[RerankerAdapter]):
	"""high-level unified interface for reranking models.

	usage:
		reranker = Reranker.create(
			"rerank-2.5",
			adapter={"type": "voyageai", "api_key": "..."},
		)
		results = await reranker.rerank("query", ["doc a", "doc b"])
	"""

	model_name: str = Field(..., description="model identifier")

	model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

	_adapter_resolver: ClassVar[AdapterResolver] = resolve_reranker_adapter

	@classmethod
	def create(
		cls,
		model_name: str,
		adapter: RerankerAdapter | dict[str, Any],
		**fields: Any,
	) -> Reranker:
		"""create a reranker with explicit adapter configuration."""
		return super()._create(("model_name", model_name), adapter=adapter, **fields)

	async def rerank(
		self,
		query: str,
		documents: list[str],
		top_k: int | None = None,
	) -> list[RerankResult]:
		"""score documents by relevance to the query, best first.

		top_k limits how many results are returned; None returns all
		documents scored.
		"""
		return await self.adapter.rerank(
			query, documents, model=self.model_name, top_k=top_k
		)
