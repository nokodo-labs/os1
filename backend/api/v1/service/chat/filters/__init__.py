"""chat filters package - registry + resolution for sdk filters."""

from __future__ import annotations

from api.v1.service.chat.context import AppContext
from api.v1.service.chat.filters.attachment_decay import AttachmentDecayFilter
from api.v1.service.chat.filters.base import Filter
from api.v1.service.chat.filters.chat_context import ChatContextFilter
from api.v1.service.chat.filters.citation_index import CitationIndexFilter
from api.v1.service.chat.filters.context_windowing import ContextWindowingFilter
from api.v1.service.chat.filters.file_resolve import FileResolveFilter
from api.v1.service.chat.filters.memory import MemoryContextFilter
from api.v1.service.chat.filters.tool_result_truncation import (
	ToolResultTruncationFilter,
)
from nokodo_ai.filters import Filter as SDKFilter


type AppFilter = SDKFilter[AppContext]


FILTER_REGISTRY: dict[str, AppFilter] = {
	"memory_context": MemoryContextFilter(),
	"chat_context": ChatContextFilter(),
	"attachment_decay": AttachmentDecayFilter(),
}


def get_registered_names() -> frozenset[str]:
	"""return registered filter names."""
	return frozenset(filter_.name for filter_ in FILTER_REGISTRY.values())


def resolve_filters(filter_ids: list[str]) -> list[AppFilter]:
	"""resolve filter ids to instantiated sdk Filter objects."""
	filters: list[AppFilter] = []
	for filter_id in filter_ids:
		filter_ = FILTER_REGISTRY.get(filter_id)
		if filter_ is None:
			continue
		filters.append(filter_)
	return filters


__all__ = [
	"AttachmentDecayFilter",
	"ChatContextFilter",
	"CitationIndexFilter",
	"ContextWindowingFilter",
	"FileResolveFilter",
	"Filter",
	"MemoryContextFilter",
	"ToolResultTruncationFilter",
	"FILTER_REGISTRY",
	"get_registered_names",
	"resolve_filters",
]
