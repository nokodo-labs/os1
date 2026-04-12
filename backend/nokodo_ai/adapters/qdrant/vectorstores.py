"""qdrant vectorstore adapter."""

from __future__ import annotations

import uuid
from typing import Literal, overload

from qdrant_client.models import (
	Condition,
	Distance,
	Document,
	ExtendedPointId,
	FieldCondition,
	Filter,
	FilterSelector,
	Fusion,
	FusionQuery,
	MatchAny,
	MatchValue,
	Modifier,
	PayloadSchemaType,
	PointIdsList,
	PointStruct,
	Prefetch,
	Range,
	ScoredPoint,
	SparseVectorParams,
	VectorParams,
)

from ...utils.vectors import normalize_cosine_score, normalize_scores
from ..base.vectorstores import (
	BaseVectorstoreAdapter,
	Chunk,
	ChunkFilter,
	ChunkSearchResult,
	FieldMatch,
	FieldMatchAny,
	Index,
)
from .base import BaseQdrantAdapter


class QdrantVectorstoreAdapter(BaseQdrantAdapter, BaseVectorstoreAdapter):
	"""adapter for Qdrant vector database.

	supports dense, sparse (BM25), and hybrid (dense + BM25 with RRF fusion)
	operations through unified add() and search() methods.

	usage:
		# local instance over gRPC
		adapter = QdrantVectorstoreAdapter(host="qdrant", grpc_port=6334)

		# Qdrant Cloud
		adapter = QdrantVectorstoreAdapter(
			base_url="https://xyz.qdrant.io",
			api_key="your-api-key",
		)

		# in-memory (for testing)
		adapter = QdrantVectorstoreAdapter(location=":memory:")
	"""

	type: Literal["qdrant.vectorstore"] = "qdrant.vectorstore"

	def _to_point_id(self, id_: str) -> uuid.UUID:
		"""convert an external string id into a Qdrant-compatible point id."""
		try:
			return uuid.UUID(id_)
		except ValueError:
			return uuid.uuid5(uuid.NAMESPACE_URL, f"nokodo:{id_}")

	async def ensure_collection(
		self,
		collection: str,
		*,
		vector_size: int,
		sparse: bool = False,
		indexes: Index | None = None,
	) -> None:
		"""ensure a collection exists with the desired vector configuration.

		indexes maps field names to scalar field types (e.g.
		{"resource_type": "keyword", "owner_id": "keyword"}).
		indexes are applied every time (idempotent) so fields added later
		are automatically indexed on existing collections.
		"""
		exists = await self._client.collection_exists(collection_name=collection)
		if not exists:
			if sparse:
				await self._client.create_collection(
					collection_name=collection,
					vectors_config={
						"dense": VectorParams(
							size=vector_size,
							distance=Distance.COSINE,
						),
					},
					sparse_vectors_config={
						"bm25": SparseVectorParams(modifier=Modifier.IDF),
					},
				)
			else:
				await self._client.create_collection(
					collection_name=collection,
					vectors_config=VectorParams(
						size=vector_size,
						distance=Distance.COSINE,
					),
				)
		# always apply indexes (idempotent - no-op if field already indexed)
		if indexes:
			for field_name, field_type in indexes.items():
				await self._client.create_payload_index(
					collection_name=collection,
					field_name=field_name,
					field_schema=PayloadSchemaType(field_type),
				)

	async def add(
		self,
		collection: str,
		chunks: list[Chunk],
		*,
		sparse: bool = False,
	) -> None:
		"""store chunks with dense and optionally sparse (BM25) vectors."""
		if not chunks:
			return
		points: list[PointStruct] = []
		for chunk in chunks:
			payload = self._build_payload(chunk)
			if sparse:
				points.append(
					PointStruct(
						id=self._to_point_id(chunk.id),
						payload=payload,
						vector={
							"dense": chunk.embedding,
							"bm25": Document(text=chunk.content, model="Qdrant/bm25"),
						},
					)
				)
			else:
				points.append(
					PointStruct(
						id=self._to_point_id(chunk.id),
						payload=payload,
						vector=chunk.embedding,
					)
				)
		await self._client.upsert(collection_name=collection, points=points)

	async def search(
		self,
		collection: str,
		*,
		query: list[float] | None = None,
		text_query: str | None = None,
		limit: int = 10,
		offset: int | None = None,
		query_filter: ChunkFilter | None = None,
		fusion: str = "rrf",
		normalize: bool = True,
	) -> list[ChunkSearchResult]:
		"""search with mode determined by argument combinations."""
		qf = self._to_qdrant_filter(query_filter) if query_filter else None
		if query is not None and text_query is not None:
			return await self._search_hybrid(
				collection,
				query=query,
				text_query=text_query,
				limit=limit,
				offset=offset,
				query_filter=qf,
				fusion=fusion,
				normalize=normalize,
			)
		if query is not None:
			return await self._search_dense(
				collection,
				query=query,
				limit=limit,
				offset=offset,
				query_filter=qf,
				normalize=normalize,
			)
		if text_query is not None:
			return await self._search_sparse(
				collection,
				text_query=text_query,
				limit=limit,
				offset=offset,
				query_filter=qf,
				normalize=normalize,
			)
		raise ValueError("at least one of query or text_query must be provided")

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

	async def delete(
		self,
		collection: str,
		target: list[str] | ChunkFilter,
	) -> None:
		"""remove chunks by their string ids or by filter."""
		exists = await self._client.collection_exists(collection_name=collection)
		if not exists:
			return
		if isinstance(target, list):
			if not target:
				return
			point_ids: list[ExtendedPointId] = [
				self._to_point_id(id_) for id_ in target
			]
			await self._client.delete(
				collection_name=collection,
				points_selector=PointIdsList(points=point_ids),
			)
		else:
			await self._client.delete(
				collection_name=collection,
				points_selector=FilterSelector(filter=self._to_qdrant_filter(target)),
			)

	async def _search_dense(
		self,
		collection: str,
		*,
		query: list[float],
		limit: int,
		offset: int | None,
		query_filter: Filter | None,
		normalize: bool,
	) -> list[ChunkSearchResult]:
		"""dense cosine similarity search."""
		response = await self._client.query_points(
			collection_name=collection,
			query=query,
			limit=limit,
			offset=offset,
			with_payload=True,
			with_vectors=True,
			query_filter=query_filter,
		)
		if normalize:
			return [
				self._build_result(p, score=normalize_cosine_score(p.score))
				for p in response.points
			]
		return [
			self._build_result(p, score=p.score if p.score is not None else 0.0)
			for p in response.points
		]

	async def _search_sparse(
		self,
		collection: str,
		*,
		text_query: str,
		limit: int,
		offset: int | None,
		query_filter: Filter | None,
		normalize: bool,
	) -> list[ChunkSearchResult]:
		"""BM25 sparse text search."""
		response = await self._client.query_points(
			collection_name=collection,
			query=Document(text=text_query, model="Qdrant/bm25"),
			using="bm25",
			limit=limit,
			offset=offset,
			with_payload=True,
			query_filter=query_filter,
		)
		if normalize:
			return self._normalize_batch(response.points)
		return self._raw_batch(response.points)

	async def _search_hybrid(
		self,
		collection: str,
		*,
		query: list[float],
		text_query: str,
		limit: int,
		offset: int | None,
		query_filter: Filter | None,
		fusion: str,
		normalize: bool,
	) -> list[ChunkSearchResult]:
		"""hybrid fusion of dense + BM25 search."""
		fusion_mode = Fusion.DBSF if fusion == "dbsf" else Fusion.RRF
		# qdrant runs prefetch stages in parallel; give each enough
		# candidates for the fusion algorithm to work well.
		prefetch_n = max(limit * 3, 30)
		response = await self._client.query_points(
			collection_name=collection,
			prefetch=[
				Prefetch(
					query=query,
					using="dense",
					limit=prefetch_n,
					filter=query_filter,
				),
				Prefetch(
					query=Document(text=text_query, model="Qdrant/bm25"),
					using="bm25",
					limit=prefetch_n,
					filter=query_filter,
				),
			],
			query=FusionQuery(fusion=fusion_mode),
			limit=limit,
			offset=offset,
			with_payload=True,
		)
		if normalize:
			return self._normalize_batch(response.points)
		return self._raw_batch(response.points)

	@staticmethod
	def _build_payload(chunk: Chunk) -> dict[str, object]:
		"""build the Qdrant payload dict from a chunk."""
		payload: dict[str, object] = {
			"id": chunk.id,
			"content": chunk.content,
		}
		if chunk.metadata:
			payload.update(chunk.metadata)
		return payload

	@staticmethod
	def _build_field_condition(match: FieldMatch | FieldMatchAny) -> FieldCondition:
		"""convert a FieldMatch or FieldMatchAny to a Qdrant FieldCondition."""
		if isinstance(match, FieldMatchAny):
			return FieldCondition(key=match.key, match=MatchAny(any=match.values))
		# FieldMatch - MatchValue only accepts str | int | bool, not float.
		# for integral floats, coerce to int. for non-integral floats, use a
		# Range condition (gte=lte) to do exact numeric matching.
		if isinstance(match.value, float):
			if match.value == int(match.value):
				return FieldCondition(
					key=match.key, match=MatchValue(value=int(match.value))
				)
			return FieldCondition(
				key=match.key,
				range=Range(gte=match.value, lte=match.value),
			)
		return FieldCondition(key=match.key, match=MatchValue(value=match.value))

	@classmethod
	def _to_qdrant_filter(cls, cf: ChunkFilter) -> Filter:
		"""convert a library ChunkFilter to a Qdrant Filter."""
		all_conds: list[Condition] = [cls._build_field_condition(m) for m in cf.all_of]
		any_conds: list[Condition] = [cls._build_field_condition(s) for s in cf.any_of]
		return Filter(
			must=all_conds or None,
			should=any_conds or None,
		)

	async def update(
		self,
		collection: str,
		target: list[str] | ChunkFilter,
		*,
		payload: dict[str, object] | None = None,
	) -> None:
		"""update matching chunks in place."""
		if payload is None:
			return
		exists = await self._client.collection_exists(collection_name=collection)
		if not exists:
			if isinstance(target, list) and target:
				raise ValueError(
					f"chunks not found: {target} (collection does not exist)"
				)
			return
		if isinstance(target, list):
			if not target:
				return
			point_ids = [self._to_point_id(id_) for id_ in target]
			found = await self._client.retrieve(
				collection_name=collection,
				ids=point_ids,
				with_payload=False,
				with_vectors=False,
			)
			if len(found) != len(target):
				found_ids = {str(p.id) for p in found}
				missing = [
					i for i in target if str(self._to_point_id(i)) not in found_ids
				]
				raise ValueError(f"chunks not found: {missing}")
			await self._client.set_payload(
				collection_name=collection,
				payload=payload,
				points=PointIdsList(points=point_ids),  # type: ignore[arg-type]
			)
		else:
			await self._client.set_payload(
				collection_name=collection,
				payload=payload,
				points=FilterSelector(filter=self._to_qdrant_filter(target)),
			)

	def _build_result(
		self,
		point: ScoredPoint,
		*,
		score: float,
	) -> ChunkSearchResult:
		"""convert a Qdrant ScoredPoint to a ChunkSearchResult."""
		payload = dict(point.payload or {})
		point_id = str(payload.pop("id", point.id))
		content = str(payload.pop("content", ""))
		# backward compat: handle nested metadata from older collections
		nested = payload.pop("metadata", None)
		if isinstance(nested, dict):
			payload.update(nested)
		return ChunkSearchResult(
			id=point_id,
			content=content,
			score=score,
			metadata=payload,
			embedding=self._extract_dense_vector(point),
		)

	def _normalize_batch(
		self,
		points: list[ScoredPoint],
	) -> list[ChunkSearchResult]:
		"""convert points and normalize scores to 0-1 as a batch."""
		if not points:
			return []
		raw_scores = [p.score if p.score is not None else 0.0 for p in points]
		normed = normalize_scores(raw_scores)
		return [
			self._build_result(p, score=s) for p, s in zip(points, normed, strict=True)
		]

	def _raw_batch(
		self,
		points: list[ScoredPoint],
	) -> list[ChunkSearchResult]:
		"""convert points keeping raw scores without normalization."""
		return [
			self._build_result(p, score=p.score if p.score is not None else 0.0)
			for p in points
		]

	@staticmethod
	def _extract_dense_vector(point: ScoredPoint) -> list[float]:
		"""extract the dense embedding from a scored point."""
		vector = point.vector
		if vector is None:
			return []
		if isinstance(vector, list):
			return [float(x) for x in vector if isinstance(x, (float, int))]
		if isinstance(vector, dict):
			dense = vector.get("dense")
			if isinstance(dense, list):
				return [float(x) for x in dense if isinstance(x, (float, int))]
		return []
