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

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.access_rule import AccessRule
from api.permissions import ResourceType
from api.v1.service import vectorstores as vectorstore_service
from api.v1.service.authorization import RESOURCE_CONFIG
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
# lives here (resource encoding layer) rather than in vectorstores.py because
# it operates on resource-level semantics (access rules) not storage primitives.


def _empty_acl() -> dict[str, Any]:
	return {
		"allowed_user_ids": [],
		"allowed_group_ids": [],
		"allowed_role_ids": [],
	}


async def fetch_bulk_acl_metadata(
	resource_ids: list[str],
	resource_type: ResourceType,
	session: AsyncSession,
) -> dict[str, dict[str, Any]]:
	"""fetch acl metadata for multiple resources in one db query.

	returns resource_id -> {allowed_user_ids, allowed_group_ids, allowed_role_ids}.
	resources with no rules get empty lists.
	"""
	if not resource_ids:
		return {}
	config = RESOURCE_CONFIG[resource_type]
	stmt = select(AccessRule).where(config.rule_fk.in_(resource_ids))
	result = await session.execute(stmt)
	rules = result.scalars().all()

	acl_data: dict[str, dict[str, Any]] = {rid: _empty_acl() for rid in resource_ids}
	fk_attr = config.rule_fk.key
	for r in rules:
		rid = str(getattr(r, fk_attr))
		if rid not in acl_data:
			continue
		if r.subject_user_id is not None:
			acl_data[rid]["allowed_user_ids"].append(str(r.subject_user_id))
		elif r.subject_group_id is not None:
			acl_data[rid]["allowed_group_ids"].append(str(r.subject_group_id))
		elif r.subject_role_id is not None:
			acl_data[rid]["allowed_role_ids"].append(str(r.subject_role_id))
		# public rules (no subject) are skipped - use a role with all members

	return acl_data


async def fetch_acl_metadata(
	resource_id: str,
	resource_type: ResourceType,
	session: AsyncSession,
) -> dict[str, Any]:
	"""fetch acl metadata for a single resource."""
	bulk = await fetch_bulk_acl_metadata([resource_id], resource_type, session)
	return bulk.get(resource_id, _empty_acl())


async def sync_resource_vector_acl(
	resource_id: str,
	resource_type: ResourceType,
	session: AsyncSession,
) -> None:
	"""patch acl payload fields on all chunks for a resource.

	resolves current access rules from postgres then calls vs.update() with
	the latest acl fields. vectors and other metadata are untouched.
	silent no-op when the resource has no chunks (never vectorized).
	"""
	payload = await fetch_acl_metadata(resource_id, resource_type, session)
	target = vectorstore_service.resource_filter(
		str(resource_type), resource_id=resource_id
	)
	coll = await vectorstore_service.get_collection(session)
	vs = vectorstore_service.get_vectorstore(collection=coll)
	await vs.update(target, payload=payload)


async def sync_resources_vector_acl_bulk(
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
	acl_by_id = await fetch_bulk_acl_metadata(resource_ids, resource_type, session)
	coll = await vectorstore_service.get_collection(session)

	async def _sync_one(rid: str) -> None:
		target = vectorstore_service.resource_filter(
			str(resource_type), resource_id=rid
		)
		vs = vectorstore_service.get_vectorstore(collection=coll)
		await vs.update(target, payload=acl_by_id[rid])

	await asyncio.gather(*(_sync_one(rid) for rid in resource_ids))
