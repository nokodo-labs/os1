"""base vectorstore adapter - capability ABC for vector databases."""

from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import Field

from ...base import Base
from ...types.json import JSONObject
from .adapter import BaseAdapter


class Chunk(Base):
	"""a single chunk of data to be stored in a vectorstore."""

	id: str
	content: str = Field(default="")
	"""original content of the chunk."""
	embedding: list[float]
	"""embedding vector representing the chunk."""
	metadata: JSONObject = Field(default_factory=dict)
	"""optional metadata associated with the chunk."""


class ChunkSearchResult(Chunk):
	"""a search result for a chunk in a vectorstore."""

	score: float
	"""
	similarity score with respect to the query embedding

	normalized 0-1, higher is more similar
	"""


class BaseVectorstoreAdapter(BaseAdapter, ABC):
	"""capability ABC for vectorstore APIs.

	adapters implementing this interface provide:
	- add(): store documents with embeddings
	- search(): query by vector similarity
	- delete(): remove documents

	the collection parameter is passed to each method to support
	namespace-level operations within a single adapter instance.
	"""

	@abstractmethod
	async def add(
		self,
		collection: str,
		chunks: list[Chunk],
	) -> None:
		"""add documents with their embeddings to the store.

		args:
			collection: target collection/namespace
			ids: unique identifiers for each document
			embeddings: vector representations
			contents: original text content
			metadata: optional metadata for each document
		"""
		...

	@abstractmethod
	async def search(
		self,
		collection: str,
		query: list[float],
		limit: int = 10,
	) -> list[ChunkSearchResult]:
		"""search for similar documents by embedding.

		args:
			collection: target collection/namespace
			embedding: query vector
			limit: maximum number of results

		returns:
			list of search results ordered by similarity
		"""
		...

	@abstractmethod
	async def delete(self, collection: str, chunks: list[Chunk]) -> None:
		"""remove documents by their ids.

		args:
			collection: target collection/namespace
			ids: identifiers of documents to remove
		"""
		...
