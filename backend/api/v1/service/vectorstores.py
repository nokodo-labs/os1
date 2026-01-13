"""vectorstore operations for the api."""

from __future__ import annotations

import os
from functools import lru_cache

from nokodo_ai.adapters.base.vectorstores import Chunk
from nokodo_ai.adapters.qdrant.vectorstores import QdrantVectorstoreAdapter
from nokodo_ai.vectorstores import Vectorstore


def _qdrant_url() -> str:
	url = os.environ.get("QDRANT_URL")
	return url if url else "http://localhost:6333"


@lru_cache(maxsize=1)
def _qdrant_adapter() -> QdrantVectorstoreAdapter:
	# qdrant sdk adapter supports using `location` as a url string
	return QdrantVectorstoreAdapter(location=_qdrant_url())


def get_vectorstore(*, collection: str) -> Vectorstore:
	"""get a qdrant-backed vectorstore for a given collection.

	vectorstore connection details are intentionally hardcoded here for now.
	"""
	return Vectorstore(
		model_name="qdrant",
		collection=collection,
		adapter=_qdrant_adapter(),
	)


async def add_chunks(*, collection: str, chunks: list[Chunk]) -> None:
	"""add chunks to a vectorstore collection."""
	await get_vectorstore(collection=collection).add(chunks)


async def delete_chunks(*, collection: str, chunks: list[Chunk]) -> None:
	"""delete chunks from a vectorstore collection."""
	await get_vectorstore(collection=collection).delete(chunks)
