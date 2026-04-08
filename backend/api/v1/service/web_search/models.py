"""web search domain models."""

from __future__ import annotations

from dataclasses import dataclass, field

from api.schemas.citations import Citation


class WebSearchError(Exception):
	"""raised when a web search operation fails."""


@dataclass(frozen=True, slots=True)
class WebSearchResult:
	"""synthesized result of a web search operation."""

	query: str
	summary: str
	citations: list[Citation] = field(default_factory=list)
