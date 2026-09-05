"""jina provider adapters."""

from .base import BaseJinaAdapter
from .rerankers import JinaRerankerAdapter


__all__ = [
	"BaseJinaAdapter",
	"JinaRerankerAdapter",
]
