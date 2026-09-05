"""vectorstore adapter union - single entry point for all vectorstore adapters."""

from typing import Annotated

from pydantic import Field

from .base.vectorstores import BaseVectorstoreAdapter
from .qdrant.vectorstores import QdrantVectorstoreAdapter


VectorstoreAdapter = Annotated[
	QdrantVectorstoreAdapter,
	Field(discriminator="type"),
]


def resolve_vectorstore_adapter(provider: str, adapter: str | None) -> str | None:
	"""resolve the adapter type string from provider."""
	if provider == "qdrant":
		return "qdrant.vectorstore"
	return None


__all__ = [
	"BaseVectorstoreAdapter",
	"QdrantVectorstoreAdapter",
	"VectorstoreAdapter",
	"resolve_vectorstore_adapter",
]
