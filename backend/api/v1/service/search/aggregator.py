"""cross-resource search aggregator.

imports search functions FROM individual resource services and
orchestrates global (cross-resource) search operations.

for resource-specific search (notes, threads, reminders, memories),
the logic lives in each resource's service module.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Callable, Coroutine
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.search import (
	SearchMode,
	SearchParams,
	SearchResultItem,
	SearchResultType,
)
from api.v1.service import calendar as calendar_service
from api.v1.service import files as files_service
from api.v1.service import memories as memories_service
from api.v1.service import notes as notes_service
from api.v1.service import projects as projects_service
from api.v1.service import reminders as reminders_service
from api.v1.service import threads as threads_service
from api.v1.service.auth import Principal
from api.v1.service.calendar.search import calendar_event_to_search_item
from api.v1.service.embeddings import embed_text
from api.v1.service.files.search import file_to_search_item
from api.v1.service.projects import project_to_search_item
from api.v1.service.reminders.search import reminder_to_search_item
from api.v1.service.search.primitives import ScoredResult
from api.v1.service.threads.search import thread_to_search_item


logger = logging.getLogger(__name__)


async def _collect[T: Any](
	coro: Coroutine[None, None, list[ScoredResult[T]]],
	projector: Callable[[T, float | None], SearchResultItem],
	limit: int,
) -> list[SearchResultItem]:
	"""await a scored coro and map results to SearchResultItem."""
	return [projector(s.item, s.score) for s in (await coro)[:limit]]


async def search_stream(
	q: str,
	db: AsyncSession,
	principal: Principal,
	types: list[SearchResultType] | None = None,
	limit: int = 10,
	search_params: SearchParams | None = None,
) -> AsyncIterator[SearchResultItem]:
	"""stream search results as they complete from each resource type.

	memories are excluded from global search.
	"""
	if types is None:
		types = [
			SearchResultType.NOTE,
			SearchResultType.THREAD,
			SearchResultType.REMINDER,
			SearchResultType.CALENDAR_EVENT,
			SearchResultType.PROJECT,
			SearchResultType.FILE,
		]

	# embed query once instead of per-resource-type to avoid redundant API calls
	params = search_params or SearchParams()
	need_dense = params.mode in (SearchMode.DENSE, SearchMode.HYBRID, SearchMode.FULL)
	dense_types = {
		SearchResultType.NOTE,
		SearchResultType.THREAD,
		SearchResultType.REMINDER,
		SearchResultType.CALENDAR_EVENT,
		SearchResultType.FILE,
	}
	query_embedding = (
		await embed_text(text=q, session=db, input_type="query")
		if need_dense and any(result_type in dense_types for result_type in types)
		else None
	)

	coros: list[Coroutine[None, None, list[SearchResultItem]]] = []
	if SearchResultType.NOTE in types:
		coros.append(
			_collect(
				notes_service.search_notes(
					q,
					db,
					principal=principal,
					limit=limit,
					search_params=search_params,
					query_embedding=query_embedding,
				),
				notes_service.note_to_search_item,
				limit,
			)
		)
	if SearchResultType.THREAD in types:
		coros.append(
			_collect(
				threads_service.search_threads(
					q,
					db,
					principal=principal,
					limit=limit,
					search_params=search_params,
					query_embedding=query_embedding,
				),
				thread_to_search_item,
				limit,
			)
		)
	if SearchResultType.REMINDER in types:
		coros.append(
			_collect(
				reminders_service.search_reminders(
					q,
					db,
					principal=principal,
					limit=limit,
					search_params=search_params,
					query_embedding=query_embedding,
				),
				reminder_to_search_item,
				limit,
			)
		)
	if SearchResultType.CALENDAR_EVENT in types:
		coros.append(
			_collect(
				calendar_service.search_calendar_events(
					q,
					db,
					principal=principal,
					limit=limit,
					search_params=search_params,
					query_embedding=query_embedding,
				),
				calendar_event_to_search_item,
				limit,
			)
		)
	if SearchResultType.PROJECT in types:
		coros.append(
			_collect(
				projects_service.search_projects(
					q,
					db,
					principal=principal,
					limit=limit,
				),
				project_to_search_item,
				limit,
			)
		)
	if SearchResultType.FILE in types:
		coros.append(
			_collect(
				files_service.search_files(
					q,
					db,
					principal=principal,
					limit=limit,
					search_params=search_params,
					query_embedding=query_embedding,
				),
				file_to_search_item,
				limit,
			)
		)

	tier_results = await asyncio.gather(*coros, return_exceptions=True)
	all_items: list[SearchResultItem] = []
	for tier in tier_results:
		if isinstance(tier, BaseException):
			logger.warning("search tier failed", exc_info=tier)
			continue
		all_items.extend(tier)

	# deduplicate by id (first occurrence wins — per-type results are already
	# relevance-ordered so earlier = higher scored within its type)
	seen: set[str] = set()
	deduped: list[SearchResultItem] = []
	for item in all_items:
		key = str(item.id)
		if key not in seen:
			seen.add(key)
			deduped.append(item)

	# sort by score DESC; unscored items fall to the end
	deduped.sort(key=lambda r: (r.score is None, -(r.score or 0.0)))

	# TODO: reranking hook — when a reranker is available in the SDK, call it
	# here on `deduped[:limit]` before yielding. reranking normalises scores
	# across resource types and makes cross-type ordering meaningful.

	for item in deduped[:limit]:
		yield item


async def vectorize_all(
	db: AsyncSession,
) -> dict[str, int]:
	"""vectorize all searchable resources. returns per-type counts."""
	notes = await notes_service.vectorize_all_notes(db)
	threads = await threads_service.vectorize_all_threads(db)
	reminders = await reminders_service.vectorize_all_reminders(db)
	calendar_events = await calendar_service.vectorize_all_calendar_events(db)
	files = await files_service.vectorize_all_files(db)
	memories = await memories_service.vectorize_all_memories(db)
	return {
		"notes": notes,
		"threads": threads,
		"reminders": reminders,
		"calendar_events": calendar_events,
		"files": files,
		"memories": memories,
	}
