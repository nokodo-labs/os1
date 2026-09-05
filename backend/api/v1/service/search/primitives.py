"""primitive types and functions for the search layer.

leaf module with no resource-service dependencies; imported by both
individual resource services and the search aggregator.
"""

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol

from api.schemas.search import SearchResultAnchor, SearchResultItem
from nokodo_ai.types.json import JSONArray


logger = logging.getLogger(__name__)


class _Identifiable(Protocol):
	id: object


@dataclass(frozen=True, slots=True)
class SearchHit:
	"""per-hit search payload that belongs to the result, not the resource.

	a match is made by something inside the container (a message in a thread,
	a chunk of a file), so these fields describe the match itself and are
	unknowable from the resource row alone.
	"""

	anchor: SearchResultAnchor | None = None
	"""sub-resource to focus after routing to the container."""

	preview: str | None = None
	"""excerpt of the matched text, overriding the resource-derived preview."""

	matched_chunks: JSONArray = field(default_factory=list)
	"""top-scoring chunk payloads behind the match."""


@dataclass(frozen=True, slots=True)
class ScoredResult[T]:
	"""service-internal pairing of a hydrated resource with its relevance score.

	the score is never serialized; it exists only so the search layer can rank
	and fuse results across tiers and resource types.
	"""

	item: T
	score: float
	hit: SearchHit = field(default_factory=SearchHit)


def relevance_sort_key[T](
	hit: SearchResultItem | ScoredResult[T],
) -> tuple[bool, float]:
	"""sort key ranking best-scored results first, unscored last."""
	return (hit.score is None, -(hit.score or 0.0))


def apply_hit(item: SearchResultItem, hit: SearchHit) -> SearchResultItem:
	"""return the projected item with its match details filled in.

	the projector only sees the resource row, so anchor and preview - which
	describe what actually matched - are merged in here.
	"""
	updates: dict[str, object] = {}
	if item.anchor is None and hit.anchor is not None:
		updates["anchor"] = hit.anchor
	if hit.preview:
		updates["preview"] = hit.preview
	if not updates:
		return item
	return item.model_copy(update=updates)


def merge_scored[T: _Identifiable](
	tiers: Sequence[list[ScoredResult[T]] | BaseException],
	resource_name: str = "unknown",
) -> list[ScoredResult[T]]:
	"""merge ranked tiers into one ordered list, deduping by resource id.

	tiers must be passed in descending priority; the first occurrence of an id
	fixes its rank (no cross-tier rescoring). failed tiers are logged and
	skipped so a single tier failure degrades rather than breaks search.
	"""
	seen: set[str] = set()
	merged: list[ScoredResult[T]] = []
	for tier in tiers:
		if isinstance(tier, BaseException):
			logger.warning("search tier failed for %s", resource_name, exc_info=tier)
			continue
		for scored in tier:
			key = str(scored.item.id)
			if key in seen:
				continue
			seen.add(key)
			merged.append(scored)
	return merged
