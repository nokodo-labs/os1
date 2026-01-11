"""Vectorstore high-level interface - unified access to vector databases."""

from __future__ import annotations

from .adapters.base.vectorstores import BaseVectorstoreAdapter, SearchResult
from .types.json import JSONObject


class Vectorstore:
	"""high-level unified interface for vector databases.

	usage:
		from nokodo_ai.adapters.chroma import ChromaAdapter
		adapter = ChromaAdapter(collection="my-docs")
		store = Vectorstore(adapter=adapter)

		await store.add(ids, embeddings, contents)
		results = await store.search(query_embedding)
	"""

	def __init__(
		self,
		*,
		adapter: BaseVectorstoreAdapter,
	) -> None:
		"""initialize vectorstore interface.

		args:
			adapter: vectorstore adapter instance
		"""
		self._adapter = adapter

	async def add(
		self,
		ids: list[str],
		embeddings: list[list[float]],
		contents: list[str],
		metadata: list[JSONObject] | None = None,
	) -> None:
		"""add documents with their embeddings to the store.

		args:
			ids: unique identifiers for each document
			embeddings: vector representations
			contents: original text content
			metadata: optional metadata for each document
		"""
		await self._adapter.add(ids, embeddings, contents, metadata)

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
		return await self._adapter.search(embedding, limit=limit)

	async def delete(self, ids: list[str]) -> None:
		"""remove documents by their ids.

		args:
			ids: identifiers of documents to remove
		"""
		await self._adapter.delete(ids)
