"""vectorstore operations for the api."""

from __future__ import annotations

from functools import lru_cache

from api.settings import settings
from nokodo_ai.adapters.base.vectorstores import Chunk
from nokodo_ai.adapters.vectorstores import VectorstoreAdapter
from nokodo_ai.vectorstores import Vectorstore


def _qdrant_adapter_config() -> dict[str, object]:
	value = settings.assets.qdrant_url
	if value == ":memory:" or "://" not in value:
		return {"type": "qdrant.vectorstore", "location": value}
	return {"type": "qdrant.vectorstore", "base_url": value}


@lru_cache(maxsize=1)
def _qdrant_adapter() -> VectorstoreAdapter:
	"""get the process-wide qdrant adapter.

	this exists primarily to support `settings.assets.qdrant_url=":memory:"`, where we
	must reuse a single in-memory qdrant instance across all calls within a test.
	"""
	return Vectorstore.create("_adapter_init", adapter=_qdrant_adapter_config()).adapter


def get_vectorstore(*, collection: str) -> Vectorstore:
	"""get a qdrant-backed vectorstore for a given collection."""
	return Vectorstore.create(collection, adapter=_qdrant_adapter())


async def add_chunks(*, collection: str, chunks: list[Chunk]) -> None:
	"""add chunks to a vectorstore collection."""
	await get_vectorstore(collection=collection).add(chunks)


async def delete_chunks(*, collection: str, chunks: list[Chunk]) -> None:
	"""delete chunks from a vectorstore collection."""
	await get_vectorstore(collection=collection).delete(chunks)
