"""shared vectorization contract.

VectorSpec is the contract each resource service implements to declare:
  - what text to embed (dense) and store for BM25 retrieval
  - what metadata fields accompany the chunk
  - how to extract the resource ID (used for filter-based identity)
  - when an update requires re-vectorizing
  - which field drives sort order in cursor-based search results

chunk identity is entirely filter-based: (resource_type, resource_id)
identifies a chunk in the vectorstore without relying on the chunk ID.
chunks are assigned random UUIDs so a single resource can grow to N
chunks in the future without any schema changes.

concrete specs live in each resource's service module.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from api.v1.service import vectorstores as vectorstore_service
from api.v1.service.embeddings import embed_text
from nokodo_ai.adapters.base.vectorstores import Chunk
from nokodo_ai.types.json import JSONObject


@dataclass(frozen=True, slots=True)
class VectorSpec[T]:
	"""definition of how a resource type is embedded and stored.

	- resource_id: bare resource ID string extracted from the object;
		(filter-based identity - NOT the chunk ID)

	- dense_text: text for dense (semantic) vector
	- bm25_text: full text for BM25/sparse retrieval
	- metadata: resource-specific fields; resource_type/resource_id injected
	- should_revectorize: async (current, update_data, session) -> bool
	- sort_key: SearchResultItem field name used for cursor sort
	"""

	resource_type: str
	resource_id: Callable[[T], str]
	dense_text: Callable[[T], str]
	bm25_text: Callable[[T], str]
	metadata: Callable[[T], JSONObject]
	should_revectorize: Callable[[T, Any, AsyncSession], Awaitable[bool]]
	sort_key: str = field(default="updated_at")


def build_chunk[T](
	spec: VectorSpec[T],
	resource: T,
	embedding: list[float],
) -> Chunk:
	"""build a Chunk from a resource using its VectorSpec.

	chunks receive a random UUID. identity is filter-based via
	(resource_type, resource_id) in metadata - not via chunk ID.
	this decouples chunk cardinality from resource cardinality.
	"""
	rid = spec.resource_id(resource)
	content = spec.bm25_text(resource)
	meta: JSONObject = {
		**spec.metadata(resource),
		"resource_type": spec.resource_type,
		"resource_id": rid,
	}
	return Chunk(
		id=str(uuid.uuid4()),
		content=content,
		embedding=embedding,
		metadata=meta,
	)


async def remove_vectorized_resource[T](
	spec: VectorSpec[T],
	resource_id: str,
	session: AsyncSession,
) -> None:
	"""remove all chunks for a resource from the vectorstore."""
	await vectorstore_service.delete(
		target=vectorstore_service.resource_filter(
			spec.resource_type, resource_id=resource_id
		),
		session=session,
	)


async def vectorize_resource[T](
	spec: VectorSpec[T],
	resource: T,
	session: AsyncSession,
) -> None:
	"""vectorize a single resource: delete existing chunks then insert fresh.

	delete-before-insert keeps the vectorstore consistent without relying
	on stable chunk IDs. a new random UUID is assigned each time.
	"""
	dense = spec.dense_text(resource)
	if not dense.strip():
		return
	await remove_vectorized_resource(spec, spec.resource_id(resource), session)
	embedding = await embed_text(text=dense, session=session)
	chunk = build_chunk(spec, resource, embedding)
	await vectorstore_service.upsert_chunks(chunks=[chunk], session=session)
