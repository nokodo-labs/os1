"""qdrant vectorstore adapter."""

from __future__ import annotations

import uuid
from typing import Literal

from qdrant_client.models import (
	Distance,
	ExtendedPointId,
	PointIdsList,
	PointStruct,
	ScoredPoint,
	VectorParams,
)

from ...types.json import JSONObject
from ...utils.vectors import normalize_cosine_score
from ..base.vectorstores import BaseVectorstoreAdapter, Chunk, ChunkSearchResult
from .base import BaseQdrantAdapter


class QdrantVectorstoreAdapter(BaseQdrantAdapter, BaseVectorstoreAdapter):
	"""adapter for Qdrant vector database.

	supports both Qdrant Cloud and self-hosted instances.

	usage:
		# local instance
		adapter = QdrantVectorstoreAdapter(url="http://localhost:6333")

		# Qdrant Cloud
		adapter = QdrantVectorstoreAdapter(
			url="https://xyz.qdrant.io",
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

	async def _ensure_collection(self, collection: str, vector_size: int) -> None:
		exists = await self._client.collection_exists(collection_name=collection)
		if exists:
			return
		await self._client.create_collection(
			collection_name=collection,
			vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
		)

	async def add(
		self,
		collection: str,
		chunks: list[Chunk],
	) -> None:
		"""add documents with their embeddings to the specified collection."""
		if chunks:
			await self._ensure_collection(
				collection, vector_size=len(chunks[0].embedding)
			)
		points = []
		for chunk in chunks:
			payload: JSONObject = {"id": chunk.id, "content": chunk.content}
			if chunk.metadata:
				payload["metadata"] = chunk.metadata
			points.append(
				PointStruct(
					id=self._to_point_id(chunk.id),
					vector=chunk.embedding,
					payload=payload,
				)
			)

		await self._client.upsert(
			collection_name=collection,
			points=points,
		)

	async def search(
		self,
		collection: str,
		query: list[float],
		*,
		limit: int = 10,
	) -> list[ChunkSearchResult]:
		"""search for similar documents by embedding in the specified collection."""
		response = await self._client.query_points(
			collection_name=collection,
			query=query,
			limit=limit,
			with_payload=True,
			with_vectors=True,
		)
		return [self._convert_result(r) for r in response.points]

	async def delete(self, collection: str, chunks: list[Chunk]) -> None:
		"""remove documents by their ids from the specified collection."""
		point_ids: list[ExtendedPointId] = [
			self._to_point_id(chunk.id) for chunk in chunks
		]
		await self._client.delete(
			collection_name=collection,
			points_selector=PointIdsList(points=point_ids),
		)

	def _convert_result(self, result: ScoredPoint) -> ChunkSearchResult:
		"""convert a Qdrant ScoredPoint to ChunkSearchResult."""
		payload = result.payload or {}
		id_value = payload.get("id")
		metadata = payload.get("metadata")

		return ChunkSearchResult(
			id=id_value if isinstance(id_value, str) else str(result.id),
			content=str(payload.get("content", "")),
			score=normalize_cosine_score(result.score),
			metadata=metadata if isinstance(metadata, dict) else {},
			embedding=self._extract_embedding(result) or [],
		)

	def _extract_embedding(self, result: ScoredPoint) -> list[float] | None:
		vector = result.vector
		if vector is None:
			return None
		if isinstance(vector, list):
			if not vector:
				return []
			first = vector[0]
			if isinstance(first, (float, int)):
				return [float(x) for x in vector if isinstance(x, (float, int))]
			return None
		if isinstance(vector, dict):
			for value in vector.values():
				if (
					isinstance(value, list)
					and value
					and isinstance(value[0], (float, int))
				):
					return [float(x) for x in value if isinstance(x, (float, int))]
		return None
