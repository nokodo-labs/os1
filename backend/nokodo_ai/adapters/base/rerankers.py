"""base reranker adapter - capability ABC for reranking models."""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from .adapter import BaseAdapter


@dataclass(slots=True)
class RerankResult:
	"""relevance judgement for one input document."""

	index: int
	"""position of the document in the input list"""
	score: float
	"""relevance score of the document for the query"""


class BaseRerankerAdapter(BaseAdapter, ABC):
	"""capability ABC for reranking APIs.

	adapters implementing this interface provide:
	- rerank(): score documents by relevance to a query
	"""

	@abstractmethod
	async def rerank(
		self,
		query: str,
		documents: list[str],
		model: str,
		top_k: int | None = None,
	) -> list[RerankResult]:
		"""score documents by relevance to the query.

		args:
			query: query the documents are scored against
			documents: candidate texts to rerank
			model: provider model identifier
			top_k: number of results to return; None returns all documents

		returns:
			results ordered by score descending, referencing input positions
		"""
		...
