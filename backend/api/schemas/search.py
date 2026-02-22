"""search result schemas."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field

from api.schemas.common import ORMModel
from nokodo_ai.utils.typeid import TypeID


class SearchResultType(StrEnum):
	THREAD = "thread"
	REMINDER = "reminder"
	NOTE = "note"


class SearchResultItem(ORMModel):
	"""a single search result across any searchable entity."""

	type: SearchResultType
	id: TypeID
	title: str
	subtitle: str | None = None
	created_at: datetime
	updated_at: datetime


class SearchRequest(ORMModel):
	"""request body for search (used in non-SSE paginated mode)."""

	query: str = Field(min_length=1, max_length=500)
	types: list[SearchResultType] = Field(
		default_factory=lambda: list(SearchResultType),
		description="entity types to search",
	)
	limit: int = Field(default=10, ge=1, le=50)
