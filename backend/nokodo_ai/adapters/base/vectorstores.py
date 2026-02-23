"""base vectorstore adapter - capability ABC for vector databases."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Literal, overload

from pydantic import Field

from ...base import Base
from ...types.json import JSONObject
from .adapter import BaseAdapter


IndexFieldType = Literal[
	"keyword",
	"integer",
	"float",
	"bool",
	"text",
	"datetime",
	"uuid",
	"geo",
]
"""scalar field types that adapters may index for fast filtered search.

adapters that don't support explicit indexing (e.g. chroma, weaviate)
silently ignore the indexes parameter.
"""


class FieldMatch(Base):
	"""a single field equality condition for filtered search."""

	key: str
	"""payload field name to match."""
	value: str | int | float | bool
	"""exact value to match against."""


class ChunkFilter(Base):
	"""adapter-agnostic filter for chunk search queries.

	all conditions in `must` are ANDed together.
	"""

	must: list[FieldMatch] = Field(default_factory=list)
	"""conditions that must all match (AND logic)."""


Index = dict[str, IndexFieldType]
"""mapping of field names to scalar index types for collection provisioning."""


class Chunk(Base):
	"""a single chunk of data to be stored in a vectorstore.

	field combinations determine storage behavior:
	- embedding only (sparse=False on add): dense vector storage
	- embedding + content (sparse=True on add): hybrid dense + BM25 storage
	"""

	id: str
	content: str = Field(default="")
	"""original text content. used for BM25 sparse indexing when sparse=True."""
	embedding: list[float] = Field(default_factory=list)
	"""dense embedding vector."""
	metadata: JSONObject = Field(default_factory=dict)
	"""filterable metadata stored alongside the chunk."""


class ChunkSearchResult(Chunk):
	"""a search result from any vectorstore search mode.

	returned by dense, sparse, and hybrid searches alike.
	scores are normalized to 0-1 where 1 is most similar.
	"""

	score: float
	"""relevance score normalized to 0-1, where 1 is most similar."""


class BaseVectorstoreAdapter(BaseAdapter, ABC):
	"""capability ABC for vectorstore APIs.

	adapters implementing this interface provide unified vector operations
	that support dense, sparse, and hybrid search through argument
	combinations - similar to how ChatModel supports streaming via a
	single generate() method.

	capabilities:
	- add(): store chunks with dense and/or sparse vectors
	- search(): query by dense vector, text, or hybrid (determined by args)
	- delete(): remove chunks by id
	- ensure_collection(): provision a collection with desired vector config

	the collection parameter is passed to each method to support
	namespace-level operations within a single adapter instance.
	"""

	@abstractmethod
	async def add(
		self,
		collection: str,
		chunks: list[Chunk],
		*,
		sparse: bool = False,
	) -> None:
		"""store chunks in the vectorstore.

		when sparse=False (default), only dense vectors from chunk.embedding
		are stored. when sparse=True, BM25 sparse vectors are also generated
		from chunk.content alongside the dense vectors.

		args:
			collection: target collection/namespace
			chunks: data chunks with id, content, embedding, and metadata
			sparse: also index chunk.content for BM25 sparse retrieval
		"""
		...

	@abstractmethod
	async def search(
		self,
		collection: str,
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
		"""search the vectorstore with flexible mode selection.

		the search mode is determined by which query arguments are provided:
		- query only: dense vector similarity search
		- text_query only: sparse BM25 text search
		- both query and text_query: hybrid search with fusion

		scores are normalized to 0-1 by default (where 1 is most similar).
		set normalize=False to return raw scores from the backend.

		args:
			collection: target collection/namespace
			query: dense embedding vector for similarity search
			text_query: text query for BM25 sparse matching
			limit: maximum number of results to return
			offset: number of results to skip (for pagination)
			query_filter: adapter-agnostic filter conditions
			prefetch_limit: candidates per sub-query before fusion (hybrid)
			fusion: fusion algorithm for hybrid search ("rrf" or "dbsf")
			normalize: normalize scores to 0-1 range (default True)

		returns:
			list of results ordered by relevance score (descending)
		"""
		...

	@overload
	async def delete(
		self,
		collection: str,
		target: list[str],
	) -> None: ...

	@overload
	async def delete(
		self,
		collection: str,
		target: ChunkFilter,
	) -> None: ...

	@abstractmethod
	async def delete(
		self,
		collection: str,
		target: list[str] | ChunkFilter,
	) -> None:
		"""remove chunks by their string ids or by filter.

		args:
			collection: target collection/namespace
			target: identifiers of chunks to remove, or a filter to match
		"""
		...

	@abstractmethod
	async def ensure_collection(
		self,
		collection: str,
		*,
		vector_size: int,
		sparse: bool = False,
		indexes: Index | None = None,
	) -> None:
		"""ensure a collection exists with the desired vector configuration.

		args:
			collection: target collection/namespace
			vector_size: dimensionality of dense vectors
			sparse: also configure BM25 sparse vector support
			indexes: field_name -> field_type mapping for scalar field
				indexes. created once alongside collection provisioning.
				adapters that auto-index or don't support explicit indexing
				silently ignore this parameter.
		"""
		...
