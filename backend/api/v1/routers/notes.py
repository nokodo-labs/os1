"""Note routers."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.models.note import Note
from api.permissions import ActionPermission, ResourceType
from api.schemas.note import Note as NoteSchema
from api.schemas.note import (
	NoteCreate,
	NoteListFilters,
	NoteSearchFilters,
	NoteSortBy,
	NoteUpdate,
)
from api.schemas.search import Page, SearchMode, SearchParams
from api.schemas.sorting import SortDir
from api.v1.routers.resource_access import create_resource_access_router
from api.v1.service.authentication import Principal, get_current_principal
from api.v1.service.authorization import require_permission
from api.v1.service.events import SessionId
from api.v1.service.notes import (
	count_notes as count_notes_service,
)
from api.v1.service.notes import (
	create_note as create_note_service,
)
from api.v1.service.notes import (
	delete_note as delete_note_service,
)
from api.v1.service.notes import (
	get_note_payload,
	vectorize_notes,
)
from api.v1.service.notes import (
	list_notes as list_notes_service,
)
from api.v1.service.notes import (
	restore_note as restore_note_service,
)
from api.v1.service.notes import (
	search_notes as search_notes_service,
)
from api.v1.service.notes import (
	update_note as update_note_service,
)
from nokodo_ai.utils.typeid import TypeID


router = APIRouter(prefix="/notes", tags=["notes"])
router.include_router(create_resource_access_router(ResourceType.NOTE, "note_id"))


@router.post("", response_model=NoteSchema, status_code=status.HTTP_201_CREATED)
async def create_note(
	note_in: NoteCreate,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> Note:
	"""create a new note."""
	return await create_note_service(
		note_in,
		db,
		principal=principal,
		origin_session_id=x_session_id,
	)


@router.get("", response_model=list[NoteSchema])
async def list_notes(
	filters: Annotated[NoteListFilters, Depends()],
	skip: int = 0,
	limit: int = 50,
	sort_by: NoteSortBy = "updated_at",
	sort_dir: SortDir = "desc",
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[Note]:
	"""list notes for a user."""
	return await list_notes_service(
		db,
		principal=principal,
		filters=filters,
		skip=skip,
		limit=limit,
		sort_by=sort_by,
		sort_dir=sort_dir,
	)


@router.get("/count", response_model=int)
async def count_notes(
	filters: Annotated[NoteListFilters, Depends()],
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> int:
	"""count notes matching the list filters."""
	return await count_notes_service(db, principal=principal, filters=filters)


@router.get("/search", response_model=Page[NoteSchema])
async def search_notes(
	filters: Annotated[NoteSearchFilters, Depends()],
	q: str = Query(min_length=1, max_length=500),
	limit: int = Query(default=10, ge=1, le=50),
	offset: int = Query(default=0, ge=0),
	mode: SearchMode = Query(default=SearchMode.FULL),
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> Page[NoteSchema]:
	"""search notes returning ranked note objects."""
	scored = await search_notes_service(
		q,
		db,
		principal=principal,
		limit=limit + 1,
		offset=offset,
		search_params=SearchParams(mode=mode),
		filters=filters,
	)
	return Page(
		items=[NoteSchema.model_validate(hit.item) for hit in scored[:limit]],
		has_more=len(scored) > limit,
	)


@router.post("/revectorize")
async def revectorize_notes(
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> dict[str, int]:
	"""vectorize all notes into qdrant. notes operators only."""
	require_permission(principal, ActionPermission.NOTES_MANAGE)
	count = await vectorize_notes(db)
	return {"vectorized": count}


@router.get("/{note_id}", response_model=NoteSchema)
async def get_note(
	note_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> NoteSchema:
	"""fetch a single note."""
	return await get_note_payload(note_id, db, principal=principal)


@router.put("/{note_id}", response_model=NoteSchema)
async def update_note(
	note_id: TypeID,
	note_in: NoteUpdate,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> Note:
	"""update a note."""
	return await update_note_service(
		note_id,
		note_in,
		db,
		principal=principal,
		origin_session_id=x_session_id,
	)


@router.delete("/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_note(
	note_id: TypeID,
	permanent: bool = False,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> None:
	"""delete a note."""
	await delete_note_service(
		note_id,
		db,
		principal=principal,
		origin_session_id=x_session_id,
		permanent=permanent,
	)


@router.post("/{note_id}/restore", response_model=NoteSchema)
async def restore_note(
	note_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> Note:
	"""restore a soft-deleted note. admin only."""
	return await restore_note_service(
		note_id,
		db,
		principal=principal,
		origin_session_id=x_session_id,
	)


@router.post("/{note_id}/enhance", response_model=NoteSchema)
async def enhance_note(
	note_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> NoteSchema:
	"""enhance a note using AI. stub - returns the note unchanged until implemented."""
	return await get_note_payload(note_id, db, principal=principal)
