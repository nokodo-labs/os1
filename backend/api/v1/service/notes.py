"""service layer for note operations."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import build_cursor_page, decode_cursor
from api.database.main import session_scope
from api.models.access_rule import AccessLevel
from api.models.event import Event, EventScope
from api.models.event_types import EventType
from api.models.note import Note
from api.permissions import ResourceType
from api.schemas.note import Note as NoteOut
from api.schemas.note import NoteCreate, NoteUpdate
from api.schemas.search import (
	CursorPage,
	SearchMode,
	SearchParams,
	SearchResultItem,
	SearchResultType,
)
from api.settings import settings
from api.v1.service import events as event_service
from api.v1.service import vectorstores as vectorstore_service
from api.v1.service.auth import Principal
from api.v1.service.authorization import (
	require_permission,
	require_project_access,
	resource_access_predicate,
)
from api.v1.service.embeddings import embed_text, embed_texts
from api.v1.service.sorting import SortDir, apply_sort
from api.v1.service.vectorize import (
	VectorSpec,
	build_chunk,
	fetch_acl_metadata,
	fetch_bulk_acl_metadata,
	remove_vectorized_resource,
	vectorize_resource,
)
from nokodo_ai.types.json import JSONObject
from nokodo_ai.utils.typeid import TypeID


logger = logging.getLogger(__name__)


async def _get_note(
	note_id: TypeID,
	session: AsyncSession,
	principal: Principal,
) -> Note:
	stmt = select(Note).where(Note.id == note_id, Note.deleted_at.is_(None))
	if not principal.is_admin:
		stmt = stmt.where(Note.user_id == principal.user.id)
	result = await session.execute(stmt)
	note = result.scalars().one_or_none()
	if not note:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="note not found",
		)
	return note


async def create_note(
	note_in: NoteCreate,
	session: AsyncSession,
	principal: Principal,
	*,
	origin_session_id: str | None = None,
) -> Note:
	require_permission(principal, "notes:create")
	if note_in.project_id is not None:
		await require_project_access(
			note_in.project_id,
			session,
			principal,
			required_level=AccessLevel.EDITOR,
		)
	data = note_in.model_dump(by_alias=True)
	data["user_id"] = data.get("user_id") or principal.user.id
	if not principal.is_admin:
		data["user_id"] = principal.user.id

	note = Note(**data)
	session.add(note)
	await session.flush()
	await session.refresh(note)
	note_id = TypeID(note.id)
	event = Event(
		scope=EventScope.USER,
		scope_id=principal.user_id,
		type=EventType.NOTE_CREATED,
		data=NoteOut.model_validate(note).model_dump(mode="json"),
		user_id=principal.user_id,
	)
	await event_service.publish_event(
		session,
		event=event,
		origin_session_id=origin_session_id,
	)

	# freshly created note has no acl rules yet, but include the placeholder fields
	await vectorize_resource(
		spec=NOTE_SPEC,
		resource=note,
		session=session,
		extra_metadata=await fetch_acl_metadata(
			str(note.id), ResourceType.NOTE, session
		),
	)

	return await _get_note(note_id, session, principal)


async def list_notes(
	session: AsyncSession,
	principal: Principal,
	user_id: TypeID | None = None,
	labels: list[str] | None = None,
	skip: int = 0,
	limit: int = 50,
	sort_by: str = "updated_at",
	sort_dir: SortDir = "desc",
) -> list[Note]:
	effective_user_id = user_id
	if not principal.is_admin:
		effective_user_id = TypeID(principal.user.id)

	stmt = (
		apply_sort(
			select(Note).where(Note.deleted_at.is_(None)),
			sort_by=sort_by,
			sort_dir=sort_dir,
			columns={
				"updated_at": Note.updated_at,
				"created_at": Note.created_at,
				"title": Note.title,
			},
			tie_breaker=Note.id,
		)
		.offset(skip)
		.limit(limit)
	)

	if effective_user_id:
		stmt = stmt.where(Note.user_id == effective_user_id)

	if labels:
		stmt = stmt.where(Note.labels.contains(labels))

	result = await session.execute(stmt)
	return list(result.scalars().all())


async def get_note(
	note_id: TypeID,
	session: AsyncSession,
	principal: Principal,
) -> Note:
	return await _get_note(note_id, session, principal)


async def update_note(
	note_id: TypeID,
	note_in: NoteUpdate,
	session: AsyncSession,
	principal: Principal,
	*,
	origin_session_id: str | None = None,
) -> Note:
	note = await _get_note(note_id, session, principal)

	update_data = note_in.model_dump(exclude_unset=True, by_alias=True)
	new_project_id = update_data.get("project_id")
	if new_project_id is not None and str(new_project_id) != str(note.project_id or ""):
		await require_project_access(
			new_project_id,
			session,
			principal,
			required_level=AccessLevel.EDITOR,
		)
	for key, value in update_data.items():
		setattr(note, key, value)

	await session.flush()
	await session.refresh(note)

	# partial event: only changed fields + id + updated_at
	event_data = note_in.model_dump(mode="json", exclude_unset=True, by_alias=True)
	event_data["id"] = str(note.id)
	event_data["updated_at"] = note.updated_at.isoformat()
	event = Event(
		scope=EventScope.USER,
		scope_id=principal.user_id,
		type=EventType.NOTE_UPDATED,
		data=event_data,
		user_id=principal.user_id,
	)
	await event_service.publish_event(
		session,
		event=event,
		origin_session_id=origin_session_id,
	)

	if await NOTE_SPEC.should_revectorize(note, note_in, session):
		await vectorize_resource(
			spec=NOTE_SPEC,
			resource=note,
			session=session,
			extra_metadata=await fetch_acl_metadata(
				str(note.id), ResourceType.NOTE, session
			),
		)

	return await _get_note(note_id, session, principal)


async def delete_note(
	note_id: TypeID,
	session: AsyncSession,
	principal: Principal,
	*,
	origin_session_id: str | None = None,
) -> None:
	note = await _get_note(note_id, session, principal)
	if settings.soft_delete.notes:
		note.soft_delete()
	else:
		await session.delete(note)
	event = Event(
		scope=EventScope.USER,
		scope_id=principal.user_id,
		type=EventType.NOTE_DELETED,
		data={"id": str(note_id)},
		user_id=principal.user_id,
	)
	await event_service.publish_event(
		session,
		event=event,
		origin_session_id=origin_session_id,
	)

	await remove_vectorized_resource(
		NOTE_SPEC, resource_id=str(note_id), session=session
	)


def _note_searchable_text(note: Note) -> str:
	"""build combined searchable text for a note (title + content)."""
	parts = [note.title or ""]
	if note.content:
		parts.append(note.content)
	return " ".join(p for p in parts if p).strip()


def _note_metadata(note: Note) -> JSONObject:
	return {
		"resource_type": "note",
		"owner_id": str(note.user_id),
		"title": note.title or "",
		"labels": list(note.labels or []),
		"project_id": (str(note.project_id) if note.project_id else None),
		# acl fields - populated at vectorize time from access_rules table
		"allowed_user_ids": [],
		"allowed_group_ids": [],
		"allowed_role_ids": [],
	}


async def _note_should_revectorize(
	note: Note,
	note_in: NoteUpdate,
	session: AsyncSession,
) -> bool:
	_fields = {"title", "content", "labels", "project_id"}
	update_data = note_in.model_dump(exclude_unset=True, mode="python")
	return bool(_fields & update_data.keys())


NOTE_SPEC: VectorSpec[Note] = VectorSpec(
	resource_type="note",
	resource_id=lambda n: str(n.id),
	dense_text=_note_searchable_text,
	bm25_text=_note_searchable_text,
	metadata=_note_metadata,
	should_revectorize=_note_should_revectorize,
	sort_key="updated_at",
)


async def vectorize_all_notes(session: AsyncSession) -> int:
	"""vectorize all non-deleted notes in bulk. returns count."""
	stmt = select(Note).where(Note.deleted_at.is_(None))
	result = await session.execute(stmt)
	valid: list[tuple[Note, str]] = []
	for n in result.scalars().all():
		text = _note_searchable_text(n)
		if text.strip():
			valid.append((n, text))
	if not valid:
		return 0
	# fetch all acl metadata in one query
	note_ids = [str(n.id) for n, _ in valid]
	acl_by_id = await fetch_bulk_acl_metadata(note_ids, ResourceType.NOTE, session)
	embeddings = await embed_texts([text for _, text in valid], session)
	chunks = []
	for (note, _), emb in zip(valid, embeddings):
		await remove_vectorized_resource(
			spec=NOTE_SPEC, resource_id=str(note.id), session=session
		)
		acl = acl_by_id.get(str(note.id))
		chunks.append(build_chunk(NOTE_SPEC, note, emb, extra_metadata=acl))
	await vectorstore_service.upsert_chunks(chunks=chunks, session=session)
	return len(valid)


async def _autocomplete_notes(
	q: str,
	db: AsyncSession,
	*,
	principal: Principal,
	limit: int = 5,
) -> list[SearchResultItem]:
	"""pg_trgm autocomplete for notes on title and content."""
	stmt = (
		select(Note)
		.where(
			Note.deleted_at.is_(None),
			or_(
				func.similarity(Note.title, q) > 0.1,
				Note.title.ilike(f"%{q}%"),
				Note.content.ilike(f"%{q}%"),
			),
		)
		.order_by(func.similarity(Note.title, q).desc())
		.limit(limit)
	)
	if not principal.is_admin:
		stmt = stmt.where(Note.user_id == principal.user.id)
	result = await db.execute(stmt)
	return [
		SearchResultItem(
			type=SearchResultType.NOTE,
			id=TypeID(note.id),
			title=note.title or "",
			subtitle=(note.content[:100] if note.content else None),
			created_at=note.created_at,
			updated_at=note.updated_at,
		)
		for note in result.scalars().all()
	]


async def _hybrid_search_notes(
	query: str | list[float],
	db: AsyncSession,
	*,
	principal: Principal,
	limit: int = 10,
	search_params: SearchParams | None = None,
) -> list[SearchResultItem]:
	"""qdrant hybrid search for notes (dense + BM25, RRF fusion)."""
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
	# acl-based qdrant filter: owner or explicit grant - solves broad-surface problem
	# principals with default access (role or global) bypass should-conditions:
	# they pass postgres but have no entries in allowed_* fields
	query_filter = vectorstore_service.acl_filter(
		"note",
		is_admin=principal.is_admin or principal.has_default_access(ResourceType.NOTE),
		user_id=str(principal.user.id),
		group_ids=principal.group_ids,
		role_ids=principal.role_ids,
	)
	results = await vectorstore_service.search(
		session=db,
		query=query_emb,
		text_query=text_query,
		limit=limit,
		query_filter=query_filter,
		normalize=params.normalize,
	)
	if not results:
		return []
	resource_ids = [r.metadata["resource_id"] for r in results]
	stmt = select(Note).where(
		Note.id.in_(resource_ids),
		Note.deleted_at.is_(None),
		resource_access_predicate(principal, ResourceType.NOTE),
	)
	db_result = await db.execute(stmt)
	by_id = {str(n.id): n for n in db_result.scalars().all()}
	score_by_rid = {str(r.metadata["resource_id"]): r.score for r in results}
	items: list[SearchResultItem] = []
	for r in results:
		rid = str(r.metadata["resource_id"])
		note = by_id.get(rid)
		if not note:
			continue
		items.append(
			SearchResultItem(
				type=SearchResultType.NOTE,
				id=TypeID(note.id),
				title=note.title or "",
				subtitle=(note.content[:100] if note.content else None),
				score=score_by_rid.get(rid),
				created_at=note.created_at,
				updated_at=note.updated_at,
			)
		)
	return items


async def search_notes(
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

	# each parallel coroutine gets its own session to avoid
	# "prepared state" errors from concurrent use of a single session
	async def _run_hybrid() -> list[SearchResultItem]:
		async with session_scope(None) as s:
			return await _hybrid_search_notes(
				query,
				s,
				principal=principal,
				limit=limit + 1,
				search_params=params,
			)

	async def _run_autocomplete() -> list[SearchResultItem]:
		assert query_text is not None
		async with session_scope(None) as s:
			return await _autocomplete_notes(
				query_text,
				s,
				principal=principal,
				limit=limit + 1,
			)

	# hybrid first - wins on deduplication (higher quality than autocomplete)
	if run_hybrid:
		coros.append(_run_hybrid())
	if run_autocomplete and query_text is not None:
		coros.append(_run_autocomplete())
	results = await asyncio.gather(*coros, return_exceptions=True)
	items = vectorstore_service.merge_deduplicate(
		results, limit + 1, resource_name="notes"
	)
	if cursor:
		ts, cid = decode_cursor(cursor)
		_sk = NOTE_SPEC.sort_key
		items = [i for i in items if (getattr(i, _sk), str(i.id)) < (ts, cid)]
	_sk = NOTE_SPEC.sort_key
	items.sort(key=lambda r: (getattr(r, _sk), str(r.id)), reverse=True)
	return build_cursor_page(items, limit, sort_key=NOTE_SPEC.sort_key)
