"""web search service result schemas."""

from __future__ import annotations

from dataclasses import dataclass, field

from api.schemas.message import Citation


@dataclass(frozen=True, slots=True)
class WebSearchSource:
	"""source resource returned by a web search engine."""

	title: str
	url: str
	snippet: str
	date: str | None = None
	last_updated: str | None = None


@dataclass(frozen=True, slots=True)
class WebSearchImage:
	"""image resource returned by a web search provider."""

	url: str
	title: str | None = None
	source_url: str | None = None


@dataclass(frozen=True, slots=True)
class WebSearchResult:
	"""non-agentic web search result."""

	results: list[WebSearchSource]
	engine: str
	images: list[WebSearchImage] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class AgenticWebSearchResult:
	"""agentic web search result with synthesized answer and citations."""

	summary: str
	citations: list[Citation]
	agent: str
	engine: str | None = None
	images: list[WebSearchImage] = field(default_factory=list)


__all__ = [
	"AgenticWebSearchResult",
	"WebSearchImage",
	"WebSearchResult",
	"WebSearchSource",
]
