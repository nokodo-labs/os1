"""Note routers."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.database import get_db
from api.models.note import Note
from api.schemas.note import Note as NoteSchema
from api.schemas.note import NoteCreate, NoteUpdate
from api.schemas.sorting import CommonSortBy, SortDir
from api.v1.service import notes as note_service
from api.v1.service.auth import Principal, get_current_principal
from api.v1.service.events import SessionId
from nokodo_ai.utils.typeid import TypeID


router = APIRouter(prefix="/notes", tags=["notes"])


NoteSortBy = Literal["title"]


@router.post("", response_model=NoteSchema, status_code=status.HTTP_201_CREATED)
async def create_note(
	note_in: NoteCreate,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> Note:
	"""create a new note."""
	return await note_service.create_note(
		note_in,
		db,
		principal=principal,
		origin_session_id=x_session_id,
	)


@router.get("", response_model=list[NoteSchema])
async def list_notes(
	user_id: TypeID | None = None,
	labels: list[str] | None = Query(default=None),
	skip: int = 0,
	limit: int = 50,
	sort_by: CommonSortBy | NoteSortBy = "updated_at",
	sort_dir: SortDir = "desc",
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[Note]:
	"""list notes for a user."""
	return await note_service.list_notes(
		db,
		principal=principal,
		user_id=user_id,
		labels=labels,
		skip=skip,
		limit=limit,
		sort_by=sort_by,
		sort_dir=sort_dir,
	)


@router.get("/{note_id}", response_model=NoteSchema)
async def get_note(
	note_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> Note:
	"""fetch a single note."""
	return await note_service.get_note(note_id, db, principal=principal)


@router.put("/{note_id}", response_model=NoteSchema)
async def update_note(
	note_id: TypeID,
	note_in: NoteUpdate,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> Note:
	"""update a note."""
	return await note_service.update_note(
		note_id,
		note_in,
		db,
		principal=principal,
		origin_session_id=x_session_id,
	)


@router.delete("/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_note(
	note_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> None:
	"""delete a note."""
	await note_service.delete_note(
		note_id,
		db,
		principal=principal,
		origin_session_id=x_session_id,
	)
