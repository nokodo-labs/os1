"""service helpers for reminders and reminder lists."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.database import build_cursor_page, decode_cursor
from api.models.access_rule import AccessLevel
from api.models.event import Event, EventScope
from api.models.event_types import EventType
from api.models.reminder import Reminder, ReminderList, ReminderStatus
from api.permissions import ResourceType
from api.schemas.reminder import (
	Reminder as ReminderOut,
)
from api.schemas.reminder import (
	ReminderCreate,
	ReminderListCreate,
	ReminderListUpdate,
	ReminderListWithCounts,
	ReminderUpdate,
	ReminderWithSubtasks,
)
from api.schemas.reminder import (
	ReminderList as ReminderListOut,
)
from api.schemas.search import (
	CursorPage,
	SearchMode,
	SearchParams,
	SearchResultItem,
	SearchResultType,
)
from api.settings.settings import settings
from api.v1.service import events as event_service
from api.v1.service import vectorstores as vectorstore_service
from api.v1.service.auth import Principal
from api.v1.service.authorization import (
	require_permission,
	require_project_access,
	require_resource_access,
	resource_access_predicate,
)
from api.v1.service.embeddings import embed_text, embed_texts
from api.v1.service.sorting import SortDir, apply_sort
from api.v1.service.vectorize import (
	VectorSpec,
	build_chunk,
	remove_vectorized_resource,
	vectorize_resource,
)
from nokodo_ai.types import JSONObject
from nokodo_ai.utils.typeid import TypeID


logger = logging.getLogger(__name__)


# sort column mappings
_REMINDER_LIST_SORT_COLUMNS = {
	"position": ReminderList.position,
	"name": ReminderList.name,
	"created_at": ReminderList.created_at,
	"updated_at": ReminderList.updated_at,
}
_REMINDER_SORT_COLUMNS = {
	"position": Reminder.position,
	"due_at": Reminder.due_at,
	"remind_at": Reminder.remind_at,
	"title": Reminder.title,
	"created_at": Reminder.created_at,
	"updated_at": Reminder.updated_at,
}


# --- ReminderList service ---


async def create_reminder_list(
	data: ReminderListCreate,
	session: AsyncSession,
	*,
	principal: Principal,
	origin_session_id: str | None = None,
) -> ReminderList:
	"""create a new reminder list."""
	require_permission(principal, "reminders:create")
	if data.project_id is not None:
		await require_project_access(
			data.project_id,
			session,
			principal,
			required_level=AccessLevel.EDITOR,
		)
	reminder_list = ReminderList(
		owner_id=principal.user_id,
		**data.model_dump(exclude_unset=True),
	)
	session.add(reminder_list)
	await session.flush()
	await session.refresh(reminder_list)

	# emit reminder_list.created event
	event = Event(
		scope=EventScope.USER,
		scope_id=principal.user_id,
		type=EventType.REMINDER_LIST_CREATED,
		data=ReminderListOut.model_validate(reminder_list).model_dump(mode="json"),
		user_id=principal.user_id,
	)
	await event_service.publish_event(
		session, event=event, origin_session_id=origin_session_id
	)

	return reminder_list


async def list_reminder_lists(
	session: AsyncSession,
	*,
	principal: Principal,
	include_counts: bool = False,
	skip: int = 0,
	limit: int = 50,
	sort_by: str = "position",
	sort_dir: SortDir = "asc",
) -> list[ReminderListWithCounts]:
	"""list reminder lists, optionally with counts (single query)."""
	if not include_counts:
		stmt = select(ReminderList).where(
			resource_access_predicate(principal, ResourceType.REMINDER_LIST)
		)
		stmt = apply_sort(
			stmt,
			sort_by=sort_by,
			sort_dir=sort_dir,
			columns=_REMINDER_LIST_SORT_COLUMNS,
		)
		stmt = stmt.offset(skip).limit(limit)
		result = await session.execute(stmt)
		return list(result.scalars().all())

	# single query with subquery for counts - fixes N+1
	counts_subq = (
		select(
			Reminder.list_id,
			func.count(Reminder.id).label("total"),
			func.sum(
				case((Reminder.status == ReminderStatus.PENDING, 1), else_=0)
			).label("pending"),
			func.sum(
				case((Reminder.status == ReminderStatus.COMPLETED, 1), else_=0)
			).label("completed"),
		)
		.where(Reminder.parent_id.is_(None))
		.group_by(Reminder.list_id)
		.subquery()
	)

	stmt = (
		select(
			ReminderList,
			func.coalesce(counts_subq.c.total, 0).label("total_count"),
			func.coalesce(counts_subq.c.pending, 0).label("pending_count"),
			func.coalesce(counts_subq.c.completed, 0).label("completed_count"),
		)
		.outerjoin(counts_subq, ReminderList.id == counts_subq.c.list_id)
		.where(resource_access_predicate(principal, ResourceType.REMINDER_LIST))
	)
	stmt = apply_sort(
		stmt, sort_by=sort_by, sort_dir=sort_dir, columns=_REMINDER_LIST_SORT_COLUMNS
	)
	stmt = stmt.offset(skip).limit(limit)

	result = await session.execute(stmt)
	rows = result.all()

	return [
		ReminderListWithCounts(
			**ReminderListWithCounts.model_validate(row.ReminderList).model_dump(
				exclude={"total_count", "pending_count", "completed_count"}
			),
			total_count=row.total_count,
			pending_count=row.pending_count,
			completed_count=row.completed_count,
		)
		for row in rows
	]


async def get_list_counts(
	session: AsyncSession,
	*,
	principal: Principal,
	list_id: TypeID | None = None,
) -> dict[str, int]:
	"""get counts for a specific list or default list (list_id=None)."""
	stmt = (
		select(
			func.count(Reminder.id).label("total"),
			func.sum(
				case((Reminder.status == ReminderStatus.PENDING, 1), else_=0)
			).label("pending"),
			func.sum(
				case((Reminder.status == ReminderStatus.COMPLETED, 1), else_=0)
			).label("completed"),
		)
		.where(Reminder.owner_id == principal.user_id)
		.where(Reminder.parent_id.is_(None))
	)
	if list_id is None:
		stmt = stmt.where(Reminder.list_id.is_(None))
	else:
		stmt = stmt.where(Reminder.list_id == list_id)

	result = await session.execute(stmt)
	row = result.one()
	return {
		"total_count": row.total or 0,
		"pending_count": int(row.pending or 0),
		"completed_count": int(row.completed or 0),
	}


async def get_reminder_list(
	list_id: TypeID,
	session: AsyncSession,
	*,
	principal: Principal,
) -> ReminderList:
	"""get a reminder list by id."""
	reminder_list = await session.get(ReminderList, list_id)
	if not reminder_list:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="reminder list not found",
		)
	await require_resource_access(
		str(list_id),
		session,
		principal,
		ResourceType.REMINDER_LIST,
		owner_id=reminder_list.owner_id,
	)
	return reminder_list


async def update_reminder_list(
	list_id: TypeID,
	data: ReminderListUpdate,
	session: AsyncSession,
	*,
	principal: Principal,
	origin_session_id: str | None = None,
) -> ReminderList:
	"""update a reminder list."""
	reminder_list = await get_reminder_list(list_id, session, principal=principal)
	update_data = data.model_dump(exclude_unset=True)
	new_project_id = update_data.get("project_id")
	if new_project_id is not None and str(new_project_id) != str(
		reminder_list.project_id or ""
	):
		await require_project_access(
			new_project_id,
			session,
			principal,
			required_level=AccessLevel.EDITOR,
		)
	for key, value in update_data.items():
		setattr(reminder_list, key, value)
	await session.flush()
	await session.refresh(reminder_list)

	# partial event: only changed fields + id + updated_at
	event_data = data.model_dump(mode="json", exclude_unset=True)
	event_data["id"] = str(reminder_list.id)
	event_data["updated_at"] = reminder_list.updated_at.isoformat()
	event = Event(
		scope=EventScope.USER,
		scope_id=principal.user_id,
		type=EventType.REMINDER_LIST_UPDATED,
		data=event_data,
		user_id=principal.user_id,
	)
	await event_service.publish_event(
		session, event=event, origin_session_id=origin_session_id
	)

	# re-index child reminders when list name/description changes
	_list_search_fields = {"name", "description"}
	if _list_search_fields & update_data.keys():
		await vectorize_reminders_for_list(list_id, session)

	return reminder_list


async def delete_reminder_list(
	list_id: TypeID,
	session: AsyncSession,
	*,
	principal: Principal,
	origin_session_id: str | None = None,
) -> None:
	"""delete a reminder list and all its reminders."""
	reminder_list = await get_reminder_list(list_id, session, principal=principal)
	list_id_str = str(reminder_list.id)
	await session.delete(reminder_list)
	await session.flush()

	# emit reminder_list.deleted event
	event = Event(
		scope=EventScope.USER,
		scope_id=principal.user_id,
		type=EventType.REMINDER_LIST_DELETED,
		data={"id": list_id_str},
		user_id=principal.user_id,
	)
	await event_service.publish_event(
		session, event=event, origin_session_id=origin_session_id
	)


# --- Reminder service ---


async def create_reminder(
	data: ReminderCreate,
	session: AsyncSession,
	*,
	principal: Principal,
	origin_session_id: str | None = None,
) -> Reminder:
	"""create a new reminder."""
	if data.list_id:
		await get_reminder_list(data.list_id, session, principal=principal)
	if data.parent_id:
		parent = await get_reminder(data.parent_id, session, principal=principal)
		if data.list_id and data.list_id != parent.list_id:
			raise HTTPException(
				status_code=status.HTTP_400_BAD_REQUEST,
				detail="subtask must belong to same list as parent",
			)
	reminder = Reminder(
		owner_id=principal.user_id,
		**data.model_dump(exclude_unset=True),
	)
	session.add(reminder)
	await session.flush()
	await session.refresh(reminder)

	# emit reminder.created event
	event = Event(
		scope=EventScope.USER,
		scope_id=principal.user_id,
		type=EventType.REMINDER_CREATED,
		data=ReminderOut.model_validate(reminder).model_dump(mode="json"),
		user_id=principal.user_id,
	)
	await event_service.publish_event(
		session, event=event, origin_session_id=origin_session_id
	)

	# index for search
	await vectorize_resource(spec=REMINDER_SPEC, resource=reminder, session=session)

	return reminder


async def list_reminders(
	session: AsyncSession,
	*,
	principal: Principal,
	list_id: TypeID | None = None,
	status_filter: ReminderStatus | None = None,
	include_subtasks: bool = False,
	skip: int = 0,
	limit: int = 100,
	sort_by: str = "position",
	sort_dir: SortDir = "asc",
) -> list[ReminderWithSubtasks]:
	"""list top-level reminders, optionally with subtasks eagerly loaded."""
	stmt = select(Reminder).where(Reminder.parent_id.is_(None))

	if include_subtasks:
		stmt = stmt.options(selectinload(Reminder.subtasks))

	if list_id is None:
		# default list - owner-only (no list to share)
		stmt = stmt.where(
			Reminder.list_id.is_(None),
			Reminder.owner_id == principal.user_id,
		)
	else:
		# verify the caller can access this list
		await get_reminder_list(list_id, session, principal=principal)
		stmt = stmt.where(Reminder.list_id == list_id)

	if status_filter is not None:
		stmt = stmt.where(Reminder.status == status_filter)

	stmt = apply_sort(
		stmt, sort_by=sort_by, sort_dir=sort_dir, columns=_REMINDER_SORT_COLUMNS
	)
	stmt = stmt.offset(skip).limit(limit)

	result = await session.execute(stmt)
	return [ReminderWithSubtasks.model_validate(r) for r in result.scalars().all()]


async def get_reminder(
	reminder_id: TypeID,
	session: AsyncSession,
	*,
	principal: Principal,
	with_subtasks: bool = False,
) -> Reminder:
	"""get a reminder by id."""
	if with_subtasks:
		stmt = (
			select(Reminder)
			.options(selectinload(Reminder.subtasks))
			.where(Reminder.id == reminder_id)
		)
		result = await session.execute(stmt)
		reminder = result.scalars().first()
	else:
		reminder = await session.get(Reminder, reminder_id)

	if not reminder:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="reminder not found",
		)
	# access check: owner always has access; otherwise check list access
	if reminder.owner_id != principal.user_id and not principal.is_admin:
		if reminder.list_id:
			# delegate to list access check - raises 403 if denied
			await require_resource_access(
				str(reminder.list_id),
				session,
				principal,
				ResourceType.REMINDER_LIST,
				owner_id=reminder.owner_id,
			)
		else:
			# no list = owner-only
			raise HTTPException(
				status_code=status.HTTP_404_NOT_FOUND,
				detail="reminder not found",
			)
	return reminder


async def update_reminder(
	reminder_id: TypeID,
	data: ReminderUpdate,
	session: AsyncSession,
	*,
	principal: Principal,
	origin_session_id: str | None = None,
) -> Reminder:
	"""update a reminder."""
	reminder = await get_reminder(reminder_id, session, principal=principal)
	update_data = data.model_dump(exclude_unset=True)
	previous_list_id = reminder.list_id

	# handle status changes
	if "status" in update_data:
		if (
			update_data["status"] == ReminderStatus.COMPLETED
			and reminder.status != ReminderStatus.COMPLETED
		):
			update_data["completed_at"] = datetime.now(UTC)
		elif update_data["status"] == ReminderStatus.PENDING:
			update_data["completed_at"] = None

	if "list_id" in update_data and update_data["list_id"] is not None:
		await get_reminder_list(update_data["list_id"], session, principal=principal)

	for key, value in update_data.items():
		setattr(reminder, key, value)

	await session.flush()
	await session.refresh(reminder)

	# partial event: only changed fields + id + updated_at
	event_data = data.model_dump(mode="json", exclude_unset=True)
	event_data["id"] = str(reminder.id)
	event_data["updated_at"] = reminder.updated_at.isoformat()
	# include server-computed status fields
	if "status" in update_data:
		event_data["status"] = reminder.status.value
		event_data["completed_at"] = (
			reminder.completed_at.isoformat() if reminder.completed_at else None
		)
	event_data["previous_list_id"] = str(previous_list_id) if previous_list_id else None
	event = Event(
		scope=EventScope.USER,
		scope_id=principal.user_id,
		type=EventType.REMINDER_UPDATED,
		data=event_data,
		user_id=principal.user_id,
	)
	await event_service.publish_event(
		session, event=event, origin_session_id=origin_session_id
	)

	# re-index if searchable fields changed
	if await REMINDER_SPEC.should_revectorize(reminder, data, session):
		await vectorize_resource(spec=REMINDER_SPEC, resource=reminder, session=session)

	return reminder


async def complete_reminder(
	reminder_id: TypeID,
	session: AsyncSession,
	*,
	principal: Principal,
	cascade: bool = False,
	origin_session_id: str | None = None,
) -> Reminder:
	"""mark a reminder as completed, optionally cascading to subtasks."""
	reminder = await get_reminder(
		reminder_id, session, principal=principal, with_subtasks=cascade
	)
	now = datetime.now(UTC)

	reminder.status = ReminderStatus.COMPLETED
	reminder.completed_at = now

	if cascade and reminder.subtasks:
		for subtask in reminder.subtasks:
			if subtask.status != ReminderStatus.COMPLETED:
				subtask.status = ReminderStatus.COMPLETED
				subtask.completed_at = now

	await session.flush()
	await session.refresh(reminder)

	# partial event: completion fields + id
	completed_at_const = reminder.completed_at
	if completed_at_const is not None:
		completed_at = completed_at_const.isoformat()
	event_data = {
		"id": str(reminder.id),
		"status": reminder.status.value,
		"completed_at": completed_at,
		"updated_at": reminder.updated_at.isoformat(),
		"cascade": cascade,
	}
	event = Event(
		scope=EventScope.USER,
		scope_id=principal.user_id,
		type=EventType.REMINDER_COMPLETED,
		data=event_data,
		user_id=principal.user_id,
	)
	await event_service.publish_event(
		session, event=event, origin_session_id=origin_session_id
	)

	return reminder


async def delete_reminder(
	reminder_id: TypeID,
	session: AsyncSession,
	*,
	principal: Principal,
	origin_session_id: str | None = None,
) -> None:
	"""delete a reminder and its subtasks."""
	reminder = await get_reminder(reminder_id, session, principal=principal)
	reminder_id_str = str(reminder.id)
	list_id_str = str(reminder.list_id) if reminder.list_id else None
	await session.delete(reminder)
	await session.flush()

	# emit reminder.deleted event
	event = Event(
		scope=EventScope.USER,
		scope_id=principal.user_id,
		type=EventType.REMINDER_DELETED,
		data={"id": reminder_id_str, "list_id": list_id_str},
		user_id=principal.user_id,
	)
	await event_service.publish_event(
		session, event=event, origin_session_id=origin_session_id
	)

	# remove from search index
	await remove_vectorized_resource(
		REMINDER_SPEC, resource_id=reminder_id_str, session=session
	)


async def move_reminder(
	reminder_id: TypeID,
	target_list_id: TypeID | None,
	session: AsyncSession,
	*,
	principal: Principal,
	position: float | None = None,
	origin_session_id: str | None = None,
) -> Reminder:
	"""move a reminder to a different list (or default list if null)."""
	reminder = await get_reminder(reminder_id, session, principal=principal)
	previous_list_id = reminder.list_id

	if target_list_id is not None:
		await get_reminder_list(target_list_id, session, principal=principal)

	reminder.list_id = target_list_id
	if position is not None:
		reminder.position = position

	await session.flush()
	await session.refresh(reminder)

	# partial event: move fields + id
	event_data: dict[str, object] = {
		"id": str(reminder.id),
		"list_id": str(target_list_id) if target_list_id else None,
		"updated_at": reminder.updated_at.isoformat(),
		"previous_list_id": str(previous_list_id) if previous_list_id else None,
	}
	if position is not None:
		event_data["position"] = position
	event = Event(
		scope=EventScope.USER,
		scope_id=principal.user_id,
		type=EventType.REMINDER_UPDATED,
		data=event_data,
		user_id=principal.user_id,
	)
	await event_service.publish_event(
		session, event=event, origin_session_id=origin_session_id
	)

	return reminder


def _reminder_dense_text(reminder: Reminder) -> str:
	parts = [reminder.title or ""]
	if reminder.description:
		parts.append(reminder.description)
	return " ".join(p for p in parts if p).strip()


def _reminder_metadata(reminder: Reminder) -> JSONObject:
	return {
		"resource_type": "reminder",
		"owner_id": str(reminder.owner_id),
		"title": reminder.title or "",
		"status": (reminder.status.value if reminder.status else ""),
		"list_id": (str(reminder.list_id) if reminder.list_id else None),
	}


async def _reminder_should_revectorize(
	reminder: Reminder,
	data: ReminderUpdate,
	session: AsyncSession,
) -> bool:
	_fields = {"title", "description", "list_id"}
	update_data = data.model_dump(exclude_unset=True, mode="python")
	return bool(_fields & update_data.keys())


REMINDER_SPEC: VectorSpec[Reminder] = VectorSpec(
	resource_type="reminder",
	resource_id=lambda r: str(r.id),
	dense_text=_reminder_dense_text,
	bm25_text=_reminder_dense_text,
	metadata=_reminder_metadata,
	should_revectorize=_reminder_should_revectorize,
	sort_key="updated_at",
)


async def vectorize_reminders_for_list(
	list_id: str | TypeID, session: AsyncSession
) -> None:
	"""re-vectorize all reminders in a list (e.g. when list is renamed)."""
	stmt = select(Reminder).where(Reminder.list_id == str(list_id))
	result = await session.execute(stmt)
	valid: list[tuple[Reminder, str]] = []
	for r in result.scalars().all():
		text = _reminder_dense_text(r)
		if text.strip():
			valid.append((r, text))
	if not valid:
		return
	embeddings = await embed_texts([text for _, text in valid], session)
	chunks = []
	for (reminder, _), emb in zip(valid, embeddings):
		await remove_vectorized_resource(
			spec=REMINDER_SPEC, resource_id=str(reminder.id), session=session
		)
		chunks.append(build_chunk(REMINDER_SPEC, reminder, emb))
	await vectorstore_service.upsert_chunks(chunks=chunks, session=session)


async def vectorize_all_reminders(session: AsyncSession) -> int:
	"""vectorize all reminders in bulk. returns count."""
	stmt = select(Reminder)
	result = await session.execute(stmt)
	valid: list[tuple[Reminder, str]] = []
	for r in result.scalars().all():
		text = _reminder_dense_text(r)
		if text.strip():
			valid.append((r, text))
	if not valid:
		return 0
	embeddings = await embed_texts([text for _, text in valid], session)
	chunks = []
	for (reminder, _), emb in zip(valid, embeddings):
		await remove_vectorized_resource(
			spec=REMINDER_SPEC, resource_id=str(reminder.id), session=session
		)
		chunks.append(build_chunk(REMINDER_SPEC, reminder, emb))
	await vectorstore_service.upsert_chunks(chunks=chunks, session=session)
	return len(valid)


async def _autocomplete_reminders(
	q: str,
	db: AsyncSession,
	*,
	principal: Principal,
	limit: int = 5,
) -> list[SearchResultItem]:
	"""pg_trgm autocomplete for reminders on title/description/list."""
	stmt = (
		select(Reminder)
		.outerjoin(ReminderList, Reminder.list_id == ReminderList.id)
		.where(
			or_(
				func.similarity(Reminder.title, q) > 0.1,
				Reminder.title.ilike(f"%{q}%"),
				Reminder.description.ilike(f"%{q}%"),
				ReminderList.name.ilike(f"%{q}%"),
			),
		)
		.order_by(func.similarity(Reminder.title, q).desc())
		.limit(limit)
	)
	if not principal.is_admin:
		list_access = resource_access_predicate(principal, ResourceType.REMINDER_LIST)
		stmt = stmt.where(
			or_(
				Reminder.owner_id == principal.user.id,
				and_(Reminder.list_id.is_not(None), list_access),
			)
		)
	result = await db.execute(stmt)
	return [
		SearchResultItem(
			type=SearchResultType.REMINDER,
			id=TypeID(rem.id),
			title=rem.title or "",
			subtitle=(rem.description[:100] if rem.description else None),
			created_at=rem.created_at,
			updated_at=rem.updated_at,
		)
		for rem in result.scalars().all()
	]


async def _hybrid_search_reminders(
	query: str | list[float],
	db: AsyncSession,
	*,
	principal: Principal,
	limit: int = 10,
	search_params: SearchParams | None = None,
) -> list[SearchResultItem]:
	"""qdrant hybrid search for reminders (dense + BM25)."""
	params = search_params or SearchParams()
	need_dense = params.mode in (SearchMode.DENSE, SearchMode.HYBRID, SearchMode.FULL)
	need_sparse = params.mode in (SearchMode.SPARSE, SearchMode.HYBRID, SearchMode.FULL)
	query_text = query if isinstance(query, str) else None
	query_emb = (
		query
		if isinstance(query, list)
		else (await embed_text(text=query, session=db) if need_dense else None)
	)
	text_query = query_text if need_sparse else None
	# reminders inherit ACL from their parent list; fetch broad candidates and
	# let postgres enforce owner-or-list-access.
	query_filter = vectorstore_service.resource_filter("reminder")
	results = await vectorstore_service.search(
		session=db,
		query=query_emb,
		text_query=text_query,
		limit=settings.assets.vector.prefetch_limit,
		query_filter=query_filter,
		normalize=params.normalize,
	)
	if not results:
		return []
	resource_ids = [str(r.metadata["resource_id"]) for r in results]
	stmt = (
		select(Reminder)
		.outerjoin(ReminderList, Reminder.list_id == ReminderList.id)
		.where(Reminder.id.in_(resource_ids))
	)
	if not principal.is_admin:
		list_access = resource_access_predicate(principal, ResourceType.REMINDER_LIST)
		stmt = stmt.where(
			or_(
				Reminder.owner_id == principal.user.id,
				and_(Reminder.list_id.is_not(None), list_access),
			)
		)
	db_result = await db.execute(stmt)
	by_id = {str(r.id): r for r in db_result.scalars().all()}
	score_by_rid = {str(r.metadata["resource_id"]): r.score for r in results}
	items: list[SearchResultItem] = []
	for r in results:
		rid = str(r.metadata["resource_id"])
		rem = by_id.get(rid)
		if not rem:
			continue
		items.append(
			SearchResultItem(
				type=SearchResultType.REMINDER,
				id=TypeID(rem.id),
				title=rem.title or "",
				subtitle=(rem.description[:100] if rem.description else None),
				score=score_by_rid.get(rid),
				created_at=rem.created_at,
				updated_at=rem.updated_at,
			)
		)
	return items


async def search_reminders(
	query: str | list[float],
	db: AsyncSession,
	*,
	principal: Principal,
	limit: int = 10,
	cursor: str | None = None,
	search_params: SearchParams | None = None,
) -> CursorPage[SearchResultItem]:
	"""parallel pg_trgm + qdrant hybrid search with cursor pagination."""
	params = search_params or SearchParams()
	query_text = query if isinstance(query, str) else None
	coros: list[Coroutine[None, None, list[SearchResultItem]]] = []
	run_autocomplete = query_text is not None and params.mode in (
		SearchMode.AUTOCOMPLETE,
		SearchMode.FULL,
	)
	run_hybrid = params.mode in (
		SearchMode.HYBRID,
		SearchMode.DENSE,
		SearchMode.SPARSE,
		SearchMode.FULL,
	)
	# hybrid first - wins on deduplication (higher quality than autocomplete)
	if run_hybrid:
		coros.append(
			_hybrid_search_reminders(
				query,
				db,
				principal=principal,
				limit=limit + 1,
				search_params=params,
			)
		)
	if run_autocomplete and query_text is not None:
		coros.append(
			_autocomplete_reminders(
				query_text, db, principal=principal, limit=limit + 1
			)
		)
	results = await asyncio.gather(*coros, return_exceptions=True)
	items = vectorstore_service.merge_deduplicate(
		results, limit + 1, resource_name="reminders"
	)
	if cursor:
		ts, cid = decode_cursor(cursor)
		_sk = REMINDER_SPEC.sort_key
		items = [i for i in items if (getattr(i, _sk), str(i.id)) < (ts, cid)]
	_sk = REMINDER_SPEC.sort_key
	items.sort(key=lambda r: (getattr(r, _sk), str(r.id)), reverse=True)
	return build_cursor_page(items, limit, sort_key=REMINDER_SPEC.sort_key)
