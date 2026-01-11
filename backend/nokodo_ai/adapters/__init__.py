"""adapters for different AI providers and API shapes."""

from .base import BaseAdapter
from .base.chat import BaseChatAdapter
from .base.embeddings import BaseEmbeddingAdapter
from .base.vectorstores import BaseVectorstoreAdapter


__all__ = [
	"BaseAdapter",
	"BaseChatAdapter",
	"BaseEmbeddingAdapter",
	"BaseVectorstoreAdapter",
]
