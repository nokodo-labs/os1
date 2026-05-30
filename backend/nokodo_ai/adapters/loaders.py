"""loader adapter union - single entry point for content loaders."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field, TypeAdapter

from .base.loaders import BaseLoaderAdapter
from .markitdown.loader import MarkItDownLoaderAdapter
from .nokodo_ai.chatmodel_loader import ChatModelLoaderAdapter
from .nokodo_ai.plain import PlainLoaderAdapter


LoaderAdapter = Annotated[
	PlainLoaderAdapter | MarkItDownLoaderAdapter | ChatModelLoaderAdapter,
	Field(discriminator="type"),
]
LoaderAdapterTypeAdapter: TypeAdapter[LoaderAdapter] = TypeAdapter(LoaderAdapter)


def resolve_loader_adapter(provider: str, adapter: str | None) -> str | None:
	"""resolve the adapter type string from provider and adapter variant."""
	match provider:
		case "plain":
			return "nokodo_ai.plain"
		case "markitdown":
			return "markitdown.loader"
		case "chatmodel" | "chatmodel_loader":
			return "nokodo_ai.chatmodel_loader"
		case "nokodo_ai":
			if adapter in {"chatmodel", "chatmodel_loader"}:
				return "nokodo_ai.chatmodel_loader"
			return "nokodo_ai.plain"
	return None


def loader_adapter_from_type(adapter_type: str) -> BaseLoaderAdapter:
	"""create a concrete loader adapter from its fully-qualified type."""
	return LoaderAdapterTypeAdapter.validate_python({"type": adapter_type})


__all__ = [
	"BaseLoaderAdapter",
	"LoaderAdapter",
	"loader_adapter_from_type",
	"resolve_loader_adapter",
]
