"""vectorstore high-level interface - unified access to vector databases."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from .adapter_enabled import AdapterEnabledBase
from .adapters.base.vectorstores import Chunk, ChunkSearchResult
from .adapters.vectorstores import VectorstoreAdapter, resolve_vectorstore_adapter


class Vectorstore(AdapterEnabledBase[VectorstoreAdapter]):
	"""high-level unified interface for vector databases.

	usage:
		store = Vectorstore.create(
			"my-docs",
			adapter={"type": "qdrant", "base_url": "http://localhost:6333"},
		)
		await store.add(chunks)
		results = await store.search(query_embedding)
	"""

	collection: str = Field(
		..., description="collection/namespace within the vectorstore"
	)

	_adapter_resolver: ... = resolve_vectorstore_adapter

	@classmethod
	def create(
		cls,
		collection: str,
		*,
		adapter: VectorstoreAdapter | dict[str, Any],
		**fields: Any,
	) -> Vectorstore:
		"""Create a vectorstore with explicit adapter configuration."""
		return super()._create(("collection", collection), adapter=adapter, **fields)

	async def add(
		self,
		chunks: list[Chunk],
	) -> None:
		"""add documents with their embeddings to the store.

		args:
			ids: unique identifiers for each document
			embeddings: vector representations
			contents: original text content
			metadata: optional metadata for each document
		"""
		await self.adapter.add(self.collection, chunks)

	async def search(
		self,
		query: list[float],
		limit: int = 10,
	) -> list[ChunkSearchResult]:
		"""search for similar documents by embedding.

		args:
			query: query vector
			limit: maximum number of results

		returns:
			list of search results ordered by similarity
		"""
		return await self.adapter.search(self.collection, query, limit=limit)

	async def delete(self, chunks: list[Chunk]) -> None:
		"""remove documents by their ids.

		args:
			ids: identifiers of documents to remove
		"""
		await self.adapter.delete(self.collection, chunks)
