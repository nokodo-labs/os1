"""service layer for note operations."""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.access_rule import AccessLevel
from api.models.event import Event, EventScope
from api.models.event_types import EventType
from api.models.note import Note
from api.schemas.note import Note as NoteOut
from api.schemas.note import NoteCreate, NoteUpdate
from api.settings.settings import settings
from api.v1.service import events as event_service
from api.v1.service.auth import Principal
from api.v1.service.authorization import require_permission, require_project_access
from api.v1.service.sorting import SortDir, apply_sort
from nokodo_ai.utils.typeid import TypeID


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
