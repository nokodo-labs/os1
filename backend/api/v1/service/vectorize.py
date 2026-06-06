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

from api.permissions import ResourceType
from api.v1.service import vectorstores as vectorstore_service
from api.v1.service.authorization import (
	ACL_SYNC_VECTOR_CHUNK_RESOURCE_TYPES,
	VECTOR_CHUNK_PARENT_RESOURCE_TYPES,
	fetch_acl_metadata,
	fetch_bulk_acl_metadata,
	load_descendant_resource_ids,
)
from api.v1.service.embeddings import embed_text
from api.v1.service.vectorstores import VectorChunkResourceType
from nokodo_ai.adapters.base.vectorstores import Chunk, ChunkFilter
from nokodo_ai.types.json import JSONObject
from nokodo_ai.utils.concurrency import map_concurrently
from nokodo_ai.utils.typeid import TypeID


_VECTOR_ACL_UPDATE_CONCURRENCY = 32


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

	resource_type: VectorChunkResourceType
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
	extra_metadata: dict[str, Any] | None = None,
) -> Chunk:
	"""build a Chunk from a resource using its VectorSpec.

	chunks receive a random UUID. identity is filter-based via
	(resource_type, resource_id) in metadata - not via chunk ID.
	this decouples chunk cardinality from resource cardinality.

	extra_metadata is merged after spec.metadata() and before the
	injected resource_type/resource_id so callers (e.g. ACL sync) can
	add fields without risk of clobbering identity fields.
	"""
	rid = spec.resource_id(resource)
	content = spec.bm25_text(resource)
	meta: JSONObject = {
		**spec.metadata(resource),
		**(extra_metadata or {}),
		"resource_type": spec.resource_type.value,
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
		target=vectorstore_service.resource_types_filter(
			[spec.resource_type], resource_id=resource_id
		),
		session=session,
	)


async def vectorize_resource[T](
	spec: VectorSpec[T],
	resource: T,
	session: AsyncSession,
	extra_metadata: dict[str, Any] | None = None,
) -> None:
	"""vectorize a single resource: delete existing chunks then insert fresh.

	delete-before-insert keeps the vectorstore consistent without relying
	on stable chunk IDs. a new random UUID is assigned each time.

	extra_metadata is merged into the chunk payload (e.g. acl fields).
	"""
	dense = spec.dense_text(resource)
	if not dense.strip():
		return
	await remove_vectorized_resource(spec, spec.resource_id(resource), session)
	embedding = await embed_text(text=dense, session=session)
	chunk = build_chunk(spec, resource, embedding, extra_metadata=extra_metadata)
	await vectorstore_service.upsert_chunks(chunks=[chunk], session=session)


# -- ACL sync ----------------------------------------------------------------
# DB -> qdrant metadata sync for resource types that use per-chunk ACL fields.
# ACL principal resolution lives in authorization.metadata; this layer only
# patches vectorstore payloads.


async def sync_resource_vector_acl(
	resource_id: str,
	resource_type: ResourceType,
	session: AsyncSession,
) -> None:
	"""patch acl payload fields for a resource and all inheriting resources."""
	resources_by_type: dict[ResourceType, set[str]] = {
		resource_type: {resource_id},
	}
	descendants = await load_descendant_resource_ids(
		resource_type,
		TypeID(resource_id),
		session,
	)
	for descendant_type, descendant_ids in descendants.items():
		resources_by_type.setdefault(descendant_type, set()).update(
			str(descendant_id) for descendant_id in descendant_ids
		)
	for affected_type, affected_ids in resources_by_type.items():
		await _sync_resource_vector_acl_payloads(
			list(affected_ids),
			affected_type,
			session,
		)


async def _sync_resource_vector_acl_payload(
	resource_id: str,
	resource_type: ResourceType,
	session: AsyncSession,
) -> None:
	"""patch acl payload fields on all chunks for a resource.

	resolves current access rules from postgres then calls vs.update() with
	the latest acl fields. vectors and other metadata are untouched.
	silent no-op when the resource has no chunks (never vectorized).
	"""
	payload: dict[str, object] = {
		key: value
		for key, value in (
			await fetch_acl_metadata(resource_id, resource_type, session)
		).items()
	}
	targets = _acl_sync_chunk_filters(resource_type, resource_id)
	if not targets:
		return
	coll = await vectorstore_service.get_collection(session)
	vs = vectorstore_service.get_vectorstore(collection=coll)
	for target in targets:
		await vs.update(target, payload=payload)


async def _sync_resource_vector_acl_payloads(
	resource_ids: list[str],
	resource_type: ResourceType,
	session: AsyncSession,
) -> None:
	"""sync acl metadata for multiple resources in parallel.

	fetches all access rules for all resource ids in ONE db query then
	fires parallel qdrant update calls - optimized for bulk acl changes.
	"""
	if not resource_ids:
		return
	if resource_type not in ACL_SYNC_VECTOR_CHUNK_RESOURCE_TYPES:
		return
	unique_resource_ids = list(dict.fromkeys(resource_ids))
	acl_by_id = await fetch_bulk_acl_metadata(
		unique_resource_ids,
		resource_type,
		session,
	)
	coll = await vectorstore_service.get_collection(session)
	vs = vectorstore_service.get_vectorstore(collection=coll)

	async def _sync_one(rid: str) -> None:
		payload: dict[str, object] = {
			key: value for key, value in acl_by_id[rid].items()
		}
		for target in _acl_sync_chunk_filters(resource_type, rid):
			await vs.update(target, payload=payload)

	await map_concurrently(
		_sync_one,
		unique_resource_ids,
		limit=_VECTOR_ACL_UPDATE_CONCURRENCY,
	)


def _acl_sync_chunk_filters(
	resource_type: ResourceType,
	resource_id: str,
) -> list[ChunkFilter]:
	chunk_resource_types = ACL_SYNC_VECTOR_CHUNK_RESOURCE_TYPES.get(resource_type)
	if chunk_resource_types is None:
		return []
	direct_resource_types: list[VectorChunkResourceType] = []
	targets: list[ChunkFilter] = []
	for chunk_resource_type in chunk_resource_types:
		parent_resource_type = VECTOR_CHUNK_PARENT_RESOURCE_TYPES.get(
			chunk_resource_type
		)
		if parent_resource_type is None:
			direct_resource_types.append(chunk_resource_type)
			continue
		targets.append(
			vectorstore_service.parent_resource_filter(
				parent_resource_type,
				resource_id,
				resource_types=[chunk_resource_type],
			)
		)
	if direct_resource_types:
		targets.append(
			vectorstore_service.resource_types_filter(
				direct_resource_types,
				resource_id=resource_id,
			)
		)
	return targets
