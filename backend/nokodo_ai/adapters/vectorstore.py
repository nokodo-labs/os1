"""base vectorstore adapter - capability ABC for vector databases."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class SearchResult:
	"""a single search result from a vectorstore query."""

	id: str
	content: str
	score: float
	metadata: dict[str, object] | None = None


class BaseVectorstoreAdapter(ABC):
	"""capability ABC for vectorstore APIs.

	adapters implementing this interface provide:
	- add(): store documents with embeddings
	- search(): query by vector similarity
	- delete(): remove documents
	"""

	@abstractmethod
	async def add(
		self,
		ids: list[str],
		embeddings: list[list[float]],
		contents: list[str],
		metadata: list[dict[str, object]] | None = None,
	) -> None:
		"""add documents with their embeddings to the store.

		args:
			ids: unique identifiers for each document
			embeddings: vector representations
			contents: original text content
			metadata: optional metadata for each document
		"""
		...

	@abstractmethod
	async def search(
		self,
		embedding: list[float],
		*,
		limit: int = 10,
	) -> list[SearchResult]:
		"""search for similar documents by embedding.

		args:
			embedding: query vector
			limit: maximum number of results

		returns:
			list of search results ordered by similarity
		"""
		...

	@abstractmethod
	async def delete(self, ids: list[str]) -> None:
		"""remove documents by their ids.

		args:
			ids: identifiers of documents to remove
		"""
		...
