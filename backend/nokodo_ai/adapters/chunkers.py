"""chunker adapter union - single entry point for content chunkers."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field, TypeAdapter

from .base.chunkers import BaseChunkerAdapter
from .nokodo_ai.markdown import MarkdownChunkerAdapter
from .nokodo_ai.recursive import RecursiveChunkerAdapter


ChunkerAdapter = Annotated[
	RecursiveChunkerAdapter | MarkdownChunkerAdapter,
	Field(discriminator="type"),
]
ChunkerAdapterTypeAdapter: TypeAdapter[ChunkerAdapter] = TypeAdapter(ChunkerAdapter)


def resolve_chunker_adapter(provider: str, adapter: str | None) -> str | None:
	"""resolve the adapter type string from provider and adapter variant."""
	match provider:
		case "recursive":
			return "nokodo_ai.recursive"
		case "markdown":
			return "nokodo_ai.markdown"
		case "nokodo_ai":
			if adapter == "markdown":
				return "nokodo_ai.markdown"
			return "nokodo_ai.recursive"
	return None


def chunker_adapter_from_type(adapter_type: str) -> BaseChunkerAdapter:
	"""create a concrete chunker adapter from its fully-qualified type."""
	return ChunkerAdapterTypeAdapter.validate_python({"type": adapter_type})


__all__ = [
	"BaseChunkerAdapter",
	"ChunkerAdapter",
	"chunker_adapter_from_type",
	"resolve_chunker_adapter",
]
