"""vectorstore high-level interface - unified access to vector databases."""

from __future__ import annotations

from typing import ClassVar, overload

from pydantic import Field

from .adapter_enabled import AdapterEnabledBase, AdapterResolver
from .adapters.base.vectorstores import (
	Chunk,
	ChunkFilter,
	ChunkSearchResult,
	Index,
)
from .adapters.vectorstores import VectorstoreAdapter, resolve_vectorstore_adapter


class Vectorstore(AdapterEnabledBase[VectorstoreAdapter]):
	"""high-level unified interface for vector databases.

	supports dense, sparse, and hybrid search through argument combinations,
	similar to how ChatModel supports streaming via generate().

	usage:
		store = Vectorstore.create(
			"my-docs",
			adapter={"type": "qdrant", "base_url": "http://localhost:6333"},
		)
		await store.add(chunks)
		results = await store.search(query=embedding)
		results = await store.search(query=embedding, text_query="cats")
	"""

	collection: str = Field(
		..., description="collection/namespace within the vectorstore"
	)

	_adapter_resolver: ClassVar[AdapterResolver] = resolve_vectorstore_adapter

	@classmethod
	def create(
		cls,
		collection: str,
		*,
		adapter: VectorstoreAdapter | dict[str, object],
		**fields: object,
	) -> Vectorstore:
		"""create a vectorstore with explicit adapter configuration."""
		return super()._create(("collection", collection), adapter=adapter, **fields)

	async def add(
		self,
		chunks: list[Chunk],
		*,
		sparse: bool = False,
	) -> None:
		"""store chunks in the vectorstore.

		when sparse=True, BM25 sparse vectors are generated from
		chunk.content alongside the dense vectors for hybrid search.

		the collection must already exist (see ensure_collection).
		"""
		await self.adapter.add(self.collection, chunks, sparse=sparse)

	async def search(
		self,
		*,
		query: list[float] | None = None,
		text_query: str | None = None,
		limit: int = 10,
		offset: int | None = None,
		query_filter: ChunkFilter | None = None,
		prefetch_limit: int | None = None,
		fusion: str = "rrf",
		normalize: bool = True,
	) -> list[ChunkSearchResult]:
		"""search with flexible mode selection.

		search mode is determined by argument combinations:
		- query only: dense vector similarity
		- text_query only: sparse BM25 text search
		- both: hybrid search with fusion (rrf or dbsf)

		scores are normalized to 0-1 by default. set normalize=False
		for raw backend scores.
		"""
		return await self.adapter.search(
			self.collection,
			query=query,
			text_query=text_query,
			limit=limit,
			offset=offset,
			query_filter=query_filter,
			prefetch_limit=prefetch_limit,
			fusion=fusion,
			normalize=normalize,
		)

	@overload
	async def delete(self, target: list[str]) -> None: ...

	@overload
	async def delete(self, target: ChunkFilter) -> None: ...

	async def delete(self, target: list[str] | ChunkFilter) -> None:
		"""remove chunks by their string ids or by filter."""
		await self.adapter.delete(self.collection, target)

	@overload
	async def update(
		self, target: list[str], *, payload: dict[str, object] | None = None
	) -> None: ...

	@overload
	async def update(
		self, target: ChunkFilter, *, payload: dict[str, object] | None = None
	) -> None: ...

	async def update(
		self,
		target: list[str] | ChunkFilter,
		*,
		payload: dict[str, object] | None = None,
	) -> None:
		"""update matching chunks in place. see adapter.update for semantics."""
		await self.adapter.update(self.collection, target, payload=payload)

	async def ensure_collection(
		self,
		*,
		vector_size: int,
		sparse: bool = False,
		indexes: Index | None = None,
	) -> None:
		"""ensure the collection exists with the desired vector config."""
		await self.adapter.ensure_collection(
			self.collection,
			vector_size=vector_size,
			sparse=sparse,
			indexes=indexes,
		)
