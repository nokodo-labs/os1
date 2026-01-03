"""chat filters package - registry + resolution for sdk filters."""

from __future__ import annotations

from api.v1.service.chat.context import AppContext
from api.v1.service.chat.filters.base import Filter
from api.v1.service.chat.filters.memory import MemoryContextFilter
from nokodo_ai.filters import Filter as SDKFilter


type AppFilter = SDKFilter[AppContext]


FILTER_REGISTRY: dict[str, AppFilter] = {
	"memory_context": MemoryContextFilter(),
}


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
	"Filter",
	"MemoryContextFilter",
	"FILTER_REGISTRY",
	"resolve_filters",
]
