"""vectorstore high-level interface - unified access to vector databases."""

from __future__ import annotations

from pydantic import Field

from .adapter_enabled import AdapterEnabledBase
from .adapters.base.vectorstores import Chunk, ChunkSearchResult
from .adapters.vectorstores import VectorstoreAdapter, resolve_vectorstore_adapter


class Vectorstore(AdapterEnabledBase[VectorstoreAdapter]):
	"""high-level unified interface for vector databases.

	usage (magic - auto-selects adapter):
		store = Vectorstore("qdrant", collection="my-docs")
		await store.add(ids, embeddings, contents)
		results = await store.search(query_embedding)

	usage (explicit adapter):
		from nokodo_ai.adapters.qdrant.vectorstores import QdrantVectorstoreAdapter
		adapter = QdrantVectorstoreAdapter(url="http://localhost:6333")
		store = Vectorstore(
			"qdrant",
			collection="my-docs",
			adapter=adapter,
		)
	"""

	collection: str = Field(
		..., description="collection/namespace within the vectorstore"
	)

	_adapter_resolver: ... = resolve_vectorstore_adapter

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
