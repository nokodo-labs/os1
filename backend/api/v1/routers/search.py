"""search router - unified SSE and paginated search across entities."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import StreamingResponse

from api.core.database import get_db
from api.schemas.search import SearchResultItem, SearchResultType
from api.v1.service import search as search_service
from api.v1.service.auth import Principal, get_current_principal
from nokodo_ai.utils.sse import sse_response


router = APIRouter(prefix="/search", tags=["search"])


@router.get("/stream")
async def search_stream(
	q: str = Query(min_length=1, max_length=500),
	types: list[SearchResultType] | None = Query(default=None),
	limit: int = Query(default=10, ge=1, le=50),
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
	"""stream search results as SSE events.

	each result is emitted as an `event: result` as soon as it's found.
	the stream ends with an `event: done`.
	"""
	stream = search_service.search_stream(
		q,
		db,
		principal=principal,
		types=types,
		limit=limit,
	)
	return sse_response(stream)


@router.get("", response_model=list[SearchResultItem])
async def search(
	q: str = Query(min_length=1, max_length=500),
	types: list[SearchResultType] | None = Query(default=None),
	limit: int = Query(default=10, ge=1, le=50),
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[SearchResultItem]:
	"""paginated search across all entity types (non-streaming)."""
	if types is None:
		types = list(SearchResultType)

	results: list[SearchResultItem] = []
	per_type = max(3, limit // len(types)) if types else limit

	if SearchResultType.REMINDER in types:
		results.extend(
			await search_service.search_reminders(
				q,
				db,
				principal=principal,
				limit=per_type,
			)
		)
	if SearchResultType.NOTE in types:
		results.extend(
			await search_service.search_notes(
				q,
				db,
				principal=principal,
				limit=per_type,
			)
		)
	if SearchResultType.THREAD in types:
		results.extend(
			await search_service.search_threads(
				q,
				db,
				principal=principal,
				limit=per_type,
			)
		)

	# sort by updated_at desc, limit to requested total
	results.sort(key=lambda r: r.updated_at, reverse=True)
	return results[:limit]
