"""high-level content chunking surface."""

from __future__ import annotations

from typing import ClassVar

from pydantic import model_validator

from .adapter_enabled import AdapterEnabledBase, AdapterResolver
from .adapters.base.chunkers import BaseChunkerAdapter, ChunkingParams, ContentChunk
from .adapters.base.loaders import Text
from .adapters.chunkers import (
	ChunkerAdapter,
	resolve_chunker_adapter,
)


class Chunker(AdapterEnabledBase[BaseChunkerAdapter]):
	"""content chunker that delegates to a concrete adapter."""

	adapter: ChunkerAdapter
	target_tokens: int = 700
	overlap_tokens: int = 80
	max_chunks: int | None = 200

	_adapter_resolver: ClassVar[AdapterResolver] = resolve_chunker_adapter

	@classmethod
	def create(
		cls,
		adapter: str | ChunkerAdapter | dict[str, object],
		**fields: object,
	) -> Chunker:
		"""create a chunker with adapter configuration."""
		return cls.model_validate({"adapter": adapter, **fields})

	@model_validator(mode="before")
	@classmethod
	def _resolve_chunker_adapter_config(cls, data: dict[str, object]) -> object:
		if not isinstance(data, dict):
			return data
		adapter = data.get("adapter")
		if not isinstance(adapter, str):
			return data
		adapter_type = cls._adapter_type_from_string(adapter)
		return {**data, "adapter": {"type": adapter_type}}

	@classmethod
	def _adapter_type_from_string(cls, adapter: str) -> str:
		if "." in adapter:
			return adapter
		resolved = cls._adapter_resolver(adapter, None)
		if resolved is None:
			raise ValueError(f"unknown chunker adapter: {adapter}")
		return resolved

	async def chunk(self, text: Text) -> list[ContentChunk]:
		if text.status != "loaded":
			return []
		params = ChunkingParams(
			target_tokens=self.target_tokens,
			overlap_tokens=self.overlap_tokens,
			max_chunks=self.max_chunks,
		)
		return await self.adapter.chunk(text, params)

	async def close(self) -> None:
		await self.adapter.close()
