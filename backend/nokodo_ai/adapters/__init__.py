"""adapters for different AI providers and API shapes."""

from .base import (
	BaseChatAdapter,
	BaseClientAdapter,
	BaseEmbeddingAdapter,
	BaseVectorstoreAdapter,
)


__all__ = [
	"BaseClientAdapter",
	"BaseChatAdapter",
	"BaseEmbeddingAdapter",
	"BaseVectorstoreAdapter",
]
