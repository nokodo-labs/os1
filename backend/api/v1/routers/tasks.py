"""task routers."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import StreamingResponse

from api.database import get_db
from api.models.task import Task
from api.schemas.sorting import SortDir
from api.schemas.task import Task as TaskSchema
from api.schemas.task import (
	TaskCancelRequest,
	TaskCreate,
	TaskListFilters,
	TaskSortBy,
	TaskUpdate,
)
from api.v1.service import tasks as task_service
from api.v1.service.auth import Principal, get_current_principal
from nokodo_ai.utils.sse import sse_response
from nokodo_ai.utils.typeid import TypeID


router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.post("", response_model=TaskSchema, status_code=status.HTTP_201_CREATED)
async def create_task(
	task_in: TaskCreate,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> Task:
	"""create a new task."""
	return await task_service.create_task(task_in, db, principal=principal)


@router.get("", response_model=list[TaskSchema])
async def list_tasks(
	filters: Annotated[TaskListFilters, Depends()],
	skip: int = 0,
	limit: int = 50,
	sort_by: TaskSortBy = "created_at",
	sort_dir: SortDir = "desc",
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[Task]:
	"""list tasks with optional filters."""
	return await task_service.list_tasks(
		db,
		principal=principal,
		filters=filters,
		skip=skip,
		limit=limit,
		sort_by=sort_by,
		sort_dir=sort_dir,
	)


@router.get("/count", response_model=int)
async def count_tasks(
	filters: Annotated[TaskListFilters, Depends()],
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> int:
	"""count tasks with optional filters."""
	return await task_service.count_tasks(db, principal=principal, filters=filters)


@router.get("/{task_id}", response_model=TaskSchema)
async def get_task(
	task_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> Task:
	"""get a task by id."""
	return await task_service.get_task(task_id, db, principal=principal)


@router.patch("/{task_id}", response_model=TaskSchema)
async def update_task(
	task_id: TypeID,
	task_in: TaskUpdate,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> Task:
	"""update mutable task fields."""
	return await task_service.update_task(task_id, task_in, db, principal=principal)


@router.get("/{task_id}/stream")
async def stream_task(
	task_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
	"""stream task lifecycle events with Redis-backed catchup."""
	await task_service.get_task(task_id, db, principal=principal)
	return sse_response(_stream_task(task_id))


async def _stream_task(task_id: TypeID) -> AsyncIterator[bytes]:
	try:
		async for chunk in task_service.subscribe_task_stream(task_id):
			yield chunk
	except task_service.UnknownTaskError as exc:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Task not found",
		) from exc


@router.post("/{task_id}/cancel", response_model=TaskSchema)
async def cancel_task(
	task_id: TypeID,
	body: TaskCancelRequest | None = None,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> Task:
	"""request cancellation for an active or queued task."""
	reason = body.reason if body is not None else None
	return await task_service.cancel_task(
		task_id,
		db,
		principal=principal,
		reason=reason,
	)
