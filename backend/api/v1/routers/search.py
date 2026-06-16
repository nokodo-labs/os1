"""search router - unified SSE and paginated search across entities."""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import StreamingResponse

from api.database import get_db
from api.schemas.search import (
	SearchMode,
	SearchParams,
	SearchResultItem,
	SearchResultType,
)
from api.v1.service.auth import Principal, get_current_principal
from api.v1.service.authorization import require_admin
from api.v1.service.search import aggregator as search_service
from nokodo_ai.utils.sse import sse_done, sse_encode, sse_response


router = APIRouter(prefix="/search", tags=["search"])

# memory is NOT included in global search
_GLOBAL_TYPES = [
	SearchResultType.NOTE,
	SearchResultType.THREAD,
	SearchResultType.REMINDER,
	SearchResultType.CALENDAR_EVENT,
	SearchResultType.PROJECT,
	SearchResultType.FILE,
]


async def _results_to_sse(
	stream: AsyncIterator[SearchResultItem],
) -> AsyncIterator[bytes]:
	"""convert a SearchResultItem stream into SSE-encoded bytes."""
	async for item in stream:
		yield sse_encode(event="result", data=item)
	yield sse_done()


@router.get("/stream")
async def search_stream(
	q: str = Query(min_length=1, max_length=500),
	types: list[SearchResultType] | None = Query(default=None),
	limit: int = Query(default=10, ge=1, le=50),
	mode: SearchMode = Query(default=SearchMode.FULL),
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
	"""stream search results as SSE events.

	each result is emitted as an `event: result` as soon as it's found.
	the stream ends with an `event: done`.
	"""
	effective_types = [t for t in (types or _GLOBAL_TYPES) if t in _GLOBAL_TYPES]
	stream = search_service.search_stream(
		q,
		db,
		principal=principal,
		types=effective_types or _GLOBAL_TYPES,
		limit=limit,
		search_params=SearchParams(mode=mode),
	)
	return sse_response(_results_to_sse(stream))


@router.get("", response_model=list[SearchResultItem])
async def search(
	q: str = Query(min_length=1, max_length=500),
	types: list[SearchResultType] | None = Query(default=None),
	limit: int = Query(default=10, ge=1, le=50),
	mode: SearchMode = Query(default=SearchMode.FULL),
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[SearchResultItem]:
	"""non-streaming search across all entity types."""
	effective_types = [t for t in (types or _GLOBAL_TYPES) if t in _GLOBAL_TYPES]
	results: list[SearchResultItem] = []
	async for item in search_service.search_stream(
		q,
		db,
		principal=principal,
		types=effective_types or _GLOBAL_TYPES,
		limit=limit,
		search_params=SearchParams(mode=mode),
	):
		results.append(item)
	# sort by score DESC (relevance), unscored items last, id as tiebreaker
	results.sort(key=lambda r: (r.score is None, -(r.score or 0.0), str(r.id)))
	return results[:limit]


@router.post("/revectorize")
async def revectorize_all(
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> dict[str, int]:
	"""vectorize all searchable resources into qdrant. admin only."""
	require_admin(principal)
	return await search_service.vectorize_all(db)
