"""adapters for different AI providers and API shapes."""

from .base import BaseAdapter
from .base.chat import BaseChatAdapter
from .base.embedding import BaseEmbeddingAdapter
from .base.vectorstore import BaseVectorstoreAdapter


__all__ = [
	"BaseAdapter",
	"BaseChatAdapter",
	"BaseEmbeddingAdapter",
	"BaseVectorstoreAdapter",
]
