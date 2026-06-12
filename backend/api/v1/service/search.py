"""search service - aggregator for cross-resource search.

this module imports search functions FROM individual resource services
and orchestrates global (cross-resource) search operations.

for resource-specific search (notes, threads, reminders, memories),
the logic lives in each resource's service module.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Coroutine

from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.search import (
	CursorPage,
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
from api.v1.service.embeddings import embed_text


logger = logging.getLogger(__name__)


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

	per_type = max(3, limit // len(types)) if types else limit
	coros: list[Coroutine[None, None, CursorPage[SearchResultItem]]] = []
	if SearchResultType.NOTE in types:
		coros.append(
			notes_service.search_notes(
				q,
				db,
				principal=principal,
				limit=per_type,
				search_params=search_params,
				query_embedding=query_embedding,
			)
		)
	if SearchResultType.THREAD in types:
		coros.append(
			threads_service.search_threads(
				q,
				db,
				principal=principal,
				limit=per_type,
				search_params=search_params,
				query_embedding=query_embedding,
			)
		)
	if SearchResultType.REMINDER in types:
		coros.append(
			reminders_service.search_reminders(
				q,
				db,
				principal=principal,
				limit=per_type,
				search_params=search_params,
				query_embedding=query_embedding,
			)
		)
	if SearchResultType.CALENDAR_EVENT in types:
		coros.append(
			calendar_service.search_calendar_events(
				q,
				db,
				principal=principal,
				limit=per_type,
				search_params=search_params,
				query_embedding=query_embedding,
			)
		)
	if SearchResultType.PROJECT in types:
		coros.append(
			projects_service.search_projects(
				q,
				db,
				principal=principal,
				limit=per_type,
				search_params=search_params,
			)
		)
	if SearchResultType.FILE in types:
		coros.append(
			files_service.search_files(
				q,
				db,
				principal=principal,
				limit=per_type,
				search_params=search_params,
				query_embedding=query_embedding,
			)
		)

	count = 0
	for task in asyncio.as_completed(coros):
		try:
			page = await task
			for item in page.items:
				if count >= limit:
					return
				yield item
				count += 1
		except Exception:
			logger.warning("search stream tier failed", exc_info=True)


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
