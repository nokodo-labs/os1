"""search router - unified SSE and paginated search across entities."""

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
from api.v1.service.authentication import Principal, get_current_principal
from api.v1.service.authorization import require_admin
from api.v1.service.search.aggregator import (
	count_stale_vectors,
	vectorize,
)
from api.v1.service.search.aggregator import (
	search_stream as search_stream_service,
)
from api.v1.service.search.primitives import relevance_sort_key
from api.v1.service.vectorize import StaleBy
from nokodo_ai.types.json import JSONObject
from nokodo_ai.utils.sse import sse_done, sse_encode, sse_response


router = APIRouter(prefix="/search", tags=["search"])

# memory is NOT included in global search
_GLOBAL_TYPES = [
	SearchResultType.NOTE,
	SearchResultType.THREAD,
	SearchResultType.REMINDER_LIST,
	SearchResultType.CALENDAR,
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
	stream = search_stream_service(
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
	async for item in search_stream_service(
		q,
		db,
		principal=principal,
		types=effective_types or _GLOBAL_TYPES,
		limit=limit,
		search_params=SearchParams(mode=mode),
	):
		results.append(item)
	# id tiebreaker keeps equal-scored results stable across calls
	results.sort(key=lambda r: (*relevance_sort_key(r), str(r.id)))
	return results[:limit]


@router.get("/revectorize")
async def revectorize_preview(
	by: list[StaleBy] | None = Query(default=None),
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> JSONObject:
	"""count provenance-stale vectors per pipeline without rebuilding. admin only.

	repeat `by` to narrow to specific causes (OR); omit for all causes.
	"""
	require_admin(principal)
	return await count_stale_vectors(by or list(StaleBy), db)


@router.post("/revectorize")
async def revectorize(
	by: list[StaleBy] | None = Query(default=None),
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> JSONObject:
	"""rebuild vectors across every pipeline. admin only.

	without `by`, rebuilds everything: every resource point plus a passage
	reconcile per thread. with `by` (repeatable, OR), rebuilds only resources
	provenance-stale by those causes.
	"""
	require_admin(principal)
	return await vectorize(db, by=by or None)
