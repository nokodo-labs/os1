"""primitive types and functions for the search layer.

leaf module with no resource-service dependencies; imported by both
individual resource services and the search aggregator.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from nokodo_ai.types.json import JSONObject


logger = logging.getLogger(__name__)


class _Identifiable(Protocol):
	id: Any


@dataclass(frozen=True, slots=True)
class ScoredResult[T]:
	"""service-internal pairing of a hydrated resource with its relevance score.

	the score is never serialized; it exists only so the search layer can rank
	and fuse results across tiers and resource types. extra carries optional
	per-hit search payloads (e.g. matched chunks) that belong to the search
	result, not the resource itself.
	"""

	item: T
	score: float
	extra: JSONObject | None = None


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
