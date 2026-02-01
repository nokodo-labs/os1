"""task routers."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.database import get_db
from api.models.task import Task, TaskStatus
from api.schemas.sorting import CommonSortBy, SortDir
from api.schemas.task import Task as TaskSchema
from api.schemas.task import TaskCreate, TaskUpdate
from api.v1.service import tasks as task_service
from api.v1.service.auth import Principal, get_current_principal
from nokodo_ai.utils.typeid import TypeID


router = APIRouter(prefix="/tasks", tags=["tasks"])


TaskSortBy = Literal[
	"status",
	"task_type",
	"stage",
	"last_event_at",
]


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
	user_id: TypeID | None = None,
	status_filter: TaskStatus | None = None,
	skip: int = 0,
	limit: int = 50,
	sort_by: CommonSortBy | TaskSortBy = "created_at",
	sort_dir: SortDir = "desc",
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[Task]:
	"""list tasks with optional filters."""
	return await task_service.list_tasks(
		db,
		principal=principal,
		user_id=user_id,
		status_filter=status_filter,
		skip=skip,
		limit=limit,
		sort_by=sort_by,
		sort_dir=sort_dir,
	)


@router.patch("/{task_id}", response_model=TaskSchema)
async def update_task(
	task_id: TypeID,
	task_in: TaskUpdate,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> Task:
	"""update mutable task fields."""
	return await task_service.update_task(task_id, task_in, db, principal=principal)
