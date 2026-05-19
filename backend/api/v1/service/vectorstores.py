"""vectorstore operations for the api.

provides the process-wide vectorstore adapter, collection resolution,
provisioning, CRUD operations (upsert, search, delete), and cursor-based
pagination helpers used by all resource services.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from functools import lru_cache
from typing import overload
from urllib.parse import urlparse

from qdrant_client import AsyncQdrantClient
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.search import SearchResultItem
from api.settings import settings
from api.v1.service.embeddings import resolve_embedding_model
from nokodo_ai.adapters.base.vectorstores import (
	Chunk,
	ChunkFilter,
	ChunkSearchResult,
	FieldMatch,
	FieldMatchAny,
	Index,
)
from nokodo_ai.adapters.vectorstores import VectorstoreAdapter
from nokodo_ai.vectorstores import Vectorstore


logger = logging.getLogger(__name__)

DEFAULT_INDEXES: Index = {
	"resource_type": "keyword",
	"resource_id": "keyword",
	"owner_id": "keyword",
	# acl fields - indexed for fast principal-scoped search
	"allowed_user_ids": "keyword",
	"allowed_group_ids": "keyword",
	"allowed_role_ids": "keyword",
}
"""scalar field indexes for the default collection.

created once when the collection is first provisioned. these enable
fast filtered search by resource type and owner without full scans.
"""


# adapter and store setup


def _is_local_qdrant_location(value: str) -> bool:
	return (
		value == ":memory:"
		or value.startswith(("./", "../", "/", "\\"))
		or bool(re.match(r"^[a-zA-Z]:[\\/]", value))
	)


def _parse_qdrant_endpoint(value: str) -> tuple[str, int | None, bool | None]:
	if "://" in value:
		parsed = urlparse(value)
		if parsed.hostname is None:
			raise RuntimeError(f"invalid qdrant url: {value}")
		https = parsed.scheme == "https" if parsed.scheme else None
		return parsed.hostname, parsed.port, https

	host, separator, port_text = value.rpartition(":")
	if separator and host and port_text.isdigit():
		return host, int(port_text), None
	return value, None, None


def _vectorstore_adapter_config() -> dict[str, object]:
	provider = settings.assets.vector_database.provider

	if provider == "qdrant":
		qdrant = settings.assets.vector_database.qdrant
		value = qdrant.url
		config: dict[str, object]
		if _is_local_qdrant_location(value):
			config = {"type": "qdrant.vectorstore", "location": value}
		else:
			host, endpoint_port, https = _parse_qdrant_endpoint(value)
			config = {
				"type": "qdrant.vectorstore",
				"host": host,
				"use_grpc": qdrant.use_grpc,
			}
			if https is not None:
				config["https"] = https
			if qdrant.use_grpc:
				if "://" in value:
					if endpoint_port is not None:
						config["port"] = endpoint_port
				else:
					config["port"] = 6333
					if endpoint_port is not None:
						config["grpc_port"] = endpoint_port
			elif endpoint_port is not None:
				config["port"] = endpoint_port

		api_key = qdrant.api_key
		if api_key:
			config["api_key"] = api_key
		return config

	raise RuntimeError(
		f"unsupported vector database provider: {provider}. currently supported: qdrant"
	)


@lru_cache(maxsize=1)
def _vectorstore_adapter() -> VectorstoreAdapter:
	"""get the process-wide vector database adapter.

	this exists primarily to support in-memory test mode, where we must
	reuse a single process-wide instance across all calls within a test.
	"""
	return Vectorstore.create(
		"_adapter_init",
		adapter=_vectorstore_adapter_config(),
	).adapter


async def reset_runtime_state() -> None:
	"""clear cached vectorstore clients and collection state after settings changes."""
	global _cached_collection_name
	if _vectorstore_adapter.cache_info().currsize > 0:
		await _vectorstore_adapter().close()
	_vectorstore_adapter.cache_clear()
	_cached_collection_name = None
	_ensured_collections.clear()


def get_vectorstore(*, collection: str) -> Vectorstore:
	"""get a vectorstore for a given collection."""
	return Vectorstore.create(collection, adapter=_vectorstore_adapter())


def _admin_client_for_collection_ops() -> AsyncQdrantClient:
	"""get provider-specific admin client for collection operations."""
	provider = settings.assets.vector_database.provider
	if provider != "qdrant":
		raise RuntimeError(
			"collection admin operations are currently available only for qdrant"
		)
	return _vectorstore_adapter()._client


# collection naming and resolution


def _slugify_model(name: str) -> str:
	"""turn an embedding model name into a safe collection name slug.

	e.g. 'text-embedding-3-small' -> 'text_embedding_3_small',
	'voyage-3-large' -> 'voyage_3_large'.
	"""
	return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def collection_name(model_name: str) -> str:
	"""build the default collection name for a given model."""
	return settings.assets.vector.collection_template.format(
		model=_slugify_model(model_name)
	)


def resource_filter(
	resource_type: str,
	resource_id: str | None = None,
	owner_id: str | None = None,
) -> ChunkFilter:
	"""build a filter for a specific resource type.

	always filters by resource_type. adds resource_id for precise chunk
	identification (used for upsert/delete). adds owner_id for user-scoped
	access-controlled search.
	"""
	all_of: list[FieldMatch | FieldMatchAny] = [
		FieldMatch(key="resource_type", value=resource_type),
	]
	if resource_id is not None:
		all_of.append(FieldMatch(key="resource_id", value=resource_id))
	if owner_id is not None:
		all_of.append(FieldMatch(key="owner_id", value=owner_id))
	return ChunkFilter(all_of=all_of)


def acl_filter(
	resource_type: str,
	is_admin: bool,
	user_id: str,
	group_ids: tuple[str, ...] | list[str] = (),
	role_ids: tuple[str, ...] | list[str] = (),
) -> ChunkFilter:
	"""build a principal-scoped filter for qdrant that enforces ACL at the vector layer.

	for admins: returns a resource-type-only filter (sees everything).
	for regular principals: adds should-conditions for owner + stored ACL principals:
	- owner_id == me
	- me in allowed_user_ids
	- any(group_ids) in allowed_group_ids
	- any(role_ids) in allowed_role_ids
	"""
	all_of: list[FieldMatch | FieldMatchAny] = [
		FieldMatch(key="resource_type", value=resource_type),
	]
	if is_admin:
		return ChunkFilter(all_of=all_of)
	any_of: list[FieldMatch | FieldMatchAny] = [
		FieldMatch(key="owner_id", value=user_id),
		FieldMatch(key="allowed_user_ids", value=user_id),
	]
	if group_ids:
		any_of.append(FieldMatchAny(key="allowed_group_ids", values=list(group_ids)))
	if role_ids:
		any_of.append(FieldMatchAny(key="allowed_role_ids", values=list(role_ids)))
	return ChunkFilter(all_of=all_of, any_of=any_of)


# collection resolution and provisioning

_cached_collection_name: str | None = None
_ensured_collections: set[str] = set()


async def get_collection(session: AsyncSession) -> str:
	"""resolve the default collection name from the embedding model.

	cached for the process lifetime after first resolution.
	"""
	global _cached_collection_name
	if _cached_collection_name is None:
		model = await resolve_embedding_model(session)
		_cached_collection_name = collection_name(model.name)
	return _cached_collection_name


async def _ensure_collection(
	collection: str,
	vector_size: int,
) -> None:
	"""provision a collection if not yet ensured this process."""
	if collection in _ensured_collections:
		return
	store = get_vectorstore(collection=collection)
	await store.ensure_collection(
		vector_size=vector_size,
		sparse=True,
		indexes=DEFAULT_INDEXES,
	)
	_ensured_collections.add(collection)


# CRUD operations


async def upsert_chunks(
	chunks: list[Chunk],
	session: AsyncSession,
	collection: str | None = None,
	store: Vectorstore | None = None,
) -> None:
	"""upsert chunks (sparse=True) to the given or default collection."""
	if not chunks:
		return
	coll = collection or await get_collection(session)
	await _ensure_collection(coll, len(chunks[0].embedding))
	vs = store or get_vectorstore(collection=coll)
	await vs.add(chunks, sparse=True)


@overload
async def delete(
	target: list[str],
	session: AsyncSession,
	collection: str | None = None,
	store: Vectorstore | None = None,
) -> None: ...


@overload
async def delete(
	target: ChunkFilter,
	session: AsyncSession,
	collection: str | None = None,
	store: Vectorstore | None = None,
) -> None: ...


async def delete(
	target: list[str] | ChunkFilter,
	session: AsyncSession,
	collection: str | None = None,
	store: Vectorstore | None = None,
) -> None:
	"""remove chunks by ID list or by filter from the default collection.

	- list[str]: delete specific chunk IDs (idempotent when empty)
	- ChunkFilter: delete all chunks matching the filter conditions
	"""
	if isinstance(target, list) and not target:
		return
	coll = collection or await get_collection(session)
	vs = store or get_vectorstore(collection=coll)
	await vs.delete(target)


async def search(
	session: AsyncSession,
	query: list[float] | None = None,
	text_query: str | None = None,
	limit: int = 10,
	query_filter: ChunkFilter | None = None,
	fusion: str | None = None,
	normalize: bool | None = None,
	collection: str | None = None,
	store: Vectorstore | None = None,
) -> list[ChunkSearchResult]:
	"""search the given or default collection via the vectorstore facade.

	fusion and normalize default to settings values when not set.
	"""
	coll = collection or await get_collection(session)
	vs = store or get_vectorstore(collection=coll)
	return await vs.search(
		query=query,
		text_query=text_query,
		limit=limit,
		query_filter=query_filter,
		fusion=fusion or settings.assets.vector.fusion_algorithm,
		normalize=(
			normalize
			if normalize is not None
			else settings.assets.vector.normalize_scores
		),
	)


def merge_deduplicate(
	results: Sequence[list[SearchResultItem] | BaseException],
	limit: int,
	resource_name: str = "unknown",
) -> list[SearchResultItem]:
	"""merge parallel search results, deduplicating by id.

	priority: first result_set in the sequence wins on duplicates.
	callers should put higher-priority tiers first (hybrid before autocomplete).
	"""
	seen: set[str] = set()
	merged: list[SearchResultItem] = []
	for result_set in results:
		if isinstance(result_set, BaseException):
			logger.warning(
				"search tier failed for %s",
				resource_name,
				exc_info=result_set,
			)
			continue
		for item in result_set:
			key = str(item.id)
			if key not in seen:
				seen.add(key)
				merged.append(item)
	return merged[:limit]


# admin operations


async def list_collections() -> list[dict[str, object]]:
	"""list all collections with basic info."""
	client = _admin_client_for_collection_ops()
	response = await client.get_collections()
	result: list[dict[str, object]] = []
	for col in response.collections:
		info = await client.get_collection(col.name)
		result.append(
			{
				"name": col.name,
				"points_count": info.points_count or 0,
				"vectors_count": getattr(info, "vectors_count", 0) or 0,
				"status": str(info.status),
			}
		)
	return result


async def get_collection_info(name: str) -> dict[str, object]:
	"""get detailed info about a specific collection."""
	client = _admin_client_for_collection_ops()
	info = await client.get_collection(name)
	return {
		"name": name,
		"points_count": info.points_count or 0,
		"vectors_count": getattr(info, "vectors_count", 0) or 0,
		"status": str(info.status),
		"config": {
			"params": str(info.config.params) if info.config else None,
		},
		"indexed_vectors_count": info.indexed_vectors_count or 0,
	}


async def delete_collection(name: str) -> bool:
	"""delete a collection. returns True if deleted."""
	global _cached_collection_name
	client = _admin_client_for_collection_ops()
	result = await client.delete_collection(name)
	_ensured_collections.discard(name)
	if _cached_collection_name == name:
		_cached_collection_name = None
	return bool(result)


async def wipe_all_collections() -> list[str]:
	"""delete ALL collections. returns list of deleted names."""
	global _cached_collection_name
	client = _admin_client_for_collection_ops()
	response = await client.get_collections()
	deleted: list[str] = []
	for col in response.collections:
		await client.delete_collection(col.name)
		_ensured_collections.discard(col.name)
		deleted.append(col.name)
	_cached_collection_name = None
	return deleted
