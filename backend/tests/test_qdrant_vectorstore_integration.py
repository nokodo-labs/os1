import hashlib
import math
import os
import uuid
from typing import Any

import pytest
from qdrant_client import AsyncQdrantClient

from nokodo_ai import Vectorstore
from nokodo_ai.adapters.base.vectorstores import (
	Chunk,
	ChunkFilter,
	FieldMatch,
	FieldMatchAny,
)
from nokodo_ai.adapters.qdrant.vectorstores import QdrantVectorstoreAdapter


def _toy_embed(text: str, dim: int = 64) -> list[float]:
	"""small deterministic embedding for local integration tests.

	keeps tests self-contained (no external embedding API keys).
	"""
	vector = [0.0] * dim
	for token in text.lower().split():
		digest = hashlib.blake2b(token.encode("utf-8"), digest_size=16).digest()
		idx = int.from_bytes(digest[:2], "little") % dim
		sign = 1.0 if (digest[2] % 2 == 0) else -1.0
		vector[idx] += sign

	norm = math.sqrt(sum(x * x for x in vector))
	if norm == 0:
		return vector
	return [x / norm for x in vector]


async def _qdrant_reachable(url: str) -> bool:
	client_kwargs: dict[str, Any]
	if url == ":memory:" or "://" not in url:
		client_kwargs = {"location": url}
	else:
		client_kwargs = {"url": url}
	client = AsyncQdrantClient(**client_kwargs, timeout=5)
	try:
		await client.get_collections()
		return True
	finally:
		await client.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_qdrant_create_upsert_search_and_cleanup() -> None:
	qdrant_url = os.environ.get("QDRANT_URL", "http://localhost:6333")
	if not await _qdrant_reachable(qdrant_url):
		pytest.skip(f"qdrant not reachable at {qdrant_url}")

	collection = f"test-qdrant-{uuid.uuid4().hex}"
	local_mode = qdrant_url == ":memory:" or "://" not in qdrant_url
	if local_mode:
		# note: each AsyncQdrantClient(location=':memory:') has isolated state.
		# use the adapter's client for verification and cleanup.
		admin: AsyncQdrantClient | None = None
		adapter = QdrantVectorstoreAdapter(location=qdrant_url)
	else:
		admin = AsyncQdrantClient(url=qdrant_url, timeout=10)
		adapter = QdrantVectorstoreAdapter(base_url=qdrant_url)

	store = Vectorstore(
		collection=collection,
		adapter=adapter,
	)

	chunks = [
		Chunk(
			id="doc-cats",
			content="cats are small animals that like naps",
			embedding=_toy_embed("cats are small animals that like naps"),
			metadata={"topic": "cats"},
		),
		Chunk(
			id="doc-dogs",
			content="dogs are loyal animals and enjoy walks",
			embedding=_toy_embed("dogs are loyal animals and enjoy walks"),
			metadata={"topic": "dogs"},
		),
		Chunk(
			id="doc-space",
			content="space is vast and contains many galaxies",
			embedding=_toy_embed("space is vast and contains many galaxies"),
			metadata={"topic": "space"},
		),
	]

	try:
		await store.ensure_collection(vector_size=64)
		await store.add(chunks)
		client = adapter._client if local_mode else admin
		assert client is not None
		exists = await client.collection_exists(collection_name=collection)
		assert exists

		query = _toy_embed("cats like naps")
		results = await store.search(query=query, limit=3)
		assert results
		assert results[0].id == "doc-cats"
		assert results[0].metadata.get("topic") == "cats"
		assert all(0.0 <= r.score <= 1.0 for r in results)
	finally:
		if local_mode:
			await adapter._client.delete_collection(collection_name=collection)
			await store.close()
		else:
			await store.close()
			assert admin is not None
			await admin.delete_collection(collection_name=collection)
			await admin.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_qdrant_scroll_enumerates_matching_chunks() -> None:
	qdrant_url = os.environ.get("QDRANT_URL", "http://localhost:6333")
	if not await _qdrant_reachable(qdrant_url):
		pytest.skip(f"qdrant not reachable at {qdrant_url}")

	collection = f"test-qdrant-scroll-{uuid.uuid4().hex}"
	local_mode = qdrant_url == ":memory:" or "://" not in qdrant_url
	adapter = (
		QdrantVectorstoreAdapter(location=qdrant_url)
		if local_mode
		else QdrantVectorstoreAdapter(base_url=qdrant_url)
	)
	store = Vectorstore(collection=collection, adapter=adapter)

	chunks = [
		Chunk(
			id=f"mem-{i}",
			content=f"memory chunk {i}",
			embedding=_toy_embed(f"memory chunk {i}"),
			metadata={"resource_type": "memory", "resource_id": f"mem_{i}"},
		)
		for i in range(5)
	]
	chunks.append(
		Chunk(
			id="note-1",
			content="note chunk",
			embedding=_toy_embed("note chunk"),
			metadata={"resource_type": "note", "resource_id": "note_1"},
		)
	)

	try:
		await store.ensure_collection(vector_size=64)
		await store.add(chunks)

		# scroll with a small page size to exercise internal paging.
		all_chunks = await store.scroll(page_size=2)
		assert len(all_chunks) == 6

		memory_only = await store.scroll(
			query_filter=ChunkFilter(
				all_of=[FieldMatch(key="resource_type", value="memory")]
			),
			page_size=2,
		)
		present = {c.metadata.get("resource_id") for c in memory_only}
		assert present == {f"mem_{i}" for i in range(5)}

		subset = await store.scroll(
			query_filter=ChunkFilter(
				all_of=[
					FieldMatch(key="resource_type", value="memory"),
					FieldMatchAny(key="resource_id", values=["mem_1", "mem_3", "nope"]),
				]
			)
		)
		assert {c.metadata.get("resource_id") for c in subset} == {"mem_1", "mem_3"}
	finally:
		await adapter._client.delete_collection(collection_name=collection)
		await store.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_qdrant_scroll_missing_collection_returns_empty() -> None:
	qdrant_url = os.environ.get("QDRANT_URL", "http://localhost:6333")
	if not await _qdrant_reachable(qdrant_url):
		pytest.skip(f"qdrant not reachable at {qdrant_url}")

	local_mode = qdrant_url == ":memory:" or "://" not in qdrant_url
	adapter = (
		QdrantVectorstoreAdapter(location=qdrant_url)
		if local_mode
		else QdrantVectorstoreAdapter(base_url=qdrant_url)
	)
	store = Vectorstore(collection=f"missing-{uuid.uuid4().hex}", adapter=adapter)
	try:
		assert await store.scroll() == []
	finally:
		await store.close()
