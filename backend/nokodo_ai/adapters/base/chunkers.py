"""base chunker adapter contract."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ...base import Base
from ...types.json import JSONObject
from .adapter import BaseAdapter


if TYPE_CHECKING:
	from nokodo_ai.adapters.base.loaders import Text


@dataclass(slots=True)
class ContentChunk:
	"""text chunk emitted by a content chunker."""

	index: int
	total: int
	text: str
	metadata: JSONObject = field(default_factory=dict)


@dataclass(slots=True)
class ChunkingParams:
	"""shared chunking options for chunker adapters."""

	target_tokens: int = 700
	overlap_tokens: int = 80
	max_chunks: int | None = 200


class BaseChunkerAdapter(BaseAdapter, Base, ABC):
	"""capability ABC for content chunking adapters."""

	@abstractmethod
	def supports(self, text: Text, params: ChunkingParams) -> bool:
		"""return whether this adapter should attempt the text."""
		...

	@abstractmethod
	async def chunk(
		self,
		text: Text,
		params: ChunkingParams,
	) -> list[ContentChunk]:
		"""chunk loaded text content."""
		...
