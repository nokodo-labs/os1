"""base loader adapter contract."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from ...base import Base
from ...types.json import JSONObject
from .adapter import BaseAdapter


if TYPE_CHECKING:
	from nokodo_ai.chat_models import ChatModel


TextLoadStatus = Literal["loaded", "unsupported"]
TextFormat = Literal["plain", "markdown", "raw"]
TextFormatPreference = Literal["auto", "plain", "markdown", "raw"]


@dataclass(slots=True)
class File:
	"""loadable file payload plus basic content metadata."""

	data: bytes
	filename: str | None = None
	mime_type: str | None = None
	metadata: JSONObject = field(default_factory=dict)

	@property
	def size_bytes(self) -> int:
		return len(self.data)


@dataclass(slots=True)
class Text:
	"""text extracted from a file."""

	content: str
	status: TextLoadStatus
	source: str
	format: TextFormat = "plain"
	metadata: JSONObject = field(default_factory=dict)
	skipped_reason: str | None = None


@dataclass(slots=True)
class LoaderContext:
	"""shared context passed to loader adapters."""

	chat_model: ChatModel | None = None


@dataclass(slots=True)
class LoaderConfig:
	"""configuration for file-to-text loading."""

	text_format: TextFormatPreference = "auto"


class BaseLoaderAdapter(BaseAdapter, Base, ABC):
	"""capability ABC for content loading adapters."""

	@abstractmethod
	def supports(self, file: File, config: LoaderConfig) -> bool:
		"""return whether this adapter should attempt the content."""
		...

	@abstractmethod
	async def load(
		self,
		file: File,
		context: LoaderContext,
		config: LoaderConfig,
	) -> Text:
		"""load text content from a file."""
		...
