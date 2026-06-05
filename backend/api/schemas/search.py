"""search result schemas."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field

from api.schemas.common import ORMModel
from nokodo_ai.types.json import JSONObject
from nokodo_ai.utils.typeid import TypeID


class SearchResultType(StrEnum):
	THREAD = "thread"
	REMINDER = "reminder"
	CALENDAR_EVENT = "calendar_event"
	NOTE = "note"
	MEMORY = "memory"
	PROJECT = "project"
	FILE = "file"


class SearchResourceReferenceType(StrEnum):
	"""known resource types that can be referenced by search result context."""

	THREAD = "thread"
	NOTE = "note"
	REMINDER = "reminder"
	REMINDER_LIST = "reminder_list"
	PROJECT = "project"
	FILE = "file"
	CALENDAR_EVENT = "calendar_event"
	CALENDAR = "calendar"


class SearchMode(StrEnum):
	"""determines which search tiers to run.

	hybrid: dense + sparse (BM25) with RRF fusion
	dense: vector similarity only
	sparse: BM25 text matching only
	autocomplete: pg_trgm fuzzy matching only
	full: all tiers (autocomplete + hybrid)
	"""

	HYBRID = "hybrid"
	DENSE = "dense"
	SPARSE = "sparse"
	AUTOCOMPLETE = "autocomplete"
	FULL = "full"


class RerankStrategy(StrEnum):
	"""post-search reranking strategy.

	none: no reranking, return raw scores
	native: backend-side reranking (built-in RRF/score fusion)
	external: delegate to an external reranker model (not yet implemented)
	"""

	NONE = "none"
	NATIVE = "native"
	EXTERNAL = "external"


class SearchParams(ORMModel):
	"""configurable search behavior for all search endpoints.

	controls which search tiers are executed and how results
	are post-processed.
	"""

	mode: SearchMode = Field(
		default=SearchMode.FULL,
		description="search mode determining which tiers to run",
	)
	rerank: RerankStrategy = Field(
		default=RerankStrategy.NATIVE,
		description="reranking strategy applied after search",
	)
	normalize: bool = Field(
		default=True,
		description="normalize vectorstore scores to 0-1",
	)


class SearchResultParent(ORMModel):
	"""immediate parent resource needed to display or route a nested result."""

	type: SearchResourceReferenceType
	id: TypeID


class SearchResultItem(ORMModel):
	"""a single search result across any searchable entity."""

	type: SearchResultType
	id: TypeID
	title: str
	preview: str | None = None
	score: float | None = None
	parent: SearchResultParent | None = None
	metadata: JSONObject = Field(default_factory=dict)
	created_at: datetime
	updated_at: datetime


class CursorPage[T](ORMModel):
	"""cursor-paginated response wrapper."""

	items: list[T]
	next_cursor: str | None = None
	has_more: bool = False


class SearchRequest(ORMModel):
	"""request body for search (used in non-SSE paginated mode)."""

	query: str = Field(min_length=1, max_length=500)
	types: list[SearchResultType] = Field(
		default_factory=lambda: list(SearchResultType),
		description="entity types to search",
	)
	limit: int = Field(default=10, ge=1, le=50)
	params: SearchParams = Field(
		default_factory=SearchParams,
		description="search behavior parameters",
	)
