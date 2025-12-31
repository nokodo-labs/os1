"""adapters for different AI providers and API shapes."""

from nokodo_ai.adapters.base import BaseAdapter
from nokodo_ai.adapters.base.chat import BaseChatAdapter
from nokodo_ai.adapters.base.embedding import BaseEmbeddingAdapter
from nokodo_ai.adapters.base.vectorstore import BaseVectorstoreAdapter


__all__ = [
	"BaseAdapter",
	"BaseChatAdapter",
	"BaseEmbeddingAdapter",
	"BaseVectorstoreAdapter",
]
