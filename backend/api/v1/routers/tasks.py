"""Task routers."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.database import get_db
from api.models.task import Task, TaskStatus
from api.schemas.task import Task as TaskSchema
from api.schemas.task import TaskCreate, TaskUpdate
from api.v1.service import tasks as task_service
from api.v1.service.auth import Principal, get_current_principal
from nokodo_ai.utils.typeid import TypeID


router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.post("", response_model=TaskSchema, status_code=status.HTTP_201_CREATED)
async def create_task(
	task_in: TaskCreate,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> Task:
	"""Create a new task."""
	return await task_service.create_task(task_in, db, principal=principal)


@router.get("", response_model=list[TaskSchema])
async def list_tasks(
	user_id: TypeID | None = None,
	status_filter: TaskStatus | None = None,
	skip: int = 0,
	limit: int = 50,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[Task]:
	"""List tasks with optional filters."""
	return await task_service.list_tasks(
		db,
		principal=principal,
		user_id=user_id,
		status_filter=status_filter,
		skip=skip,
		limit=limit,
	)


@router.patch("/{task_id}", response_model=TaskSchema)
async def update_task(
	task_id: TypeID,
	task_in: TaskUpdate,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> Task:
	"""Update mutable task fields."""
	return await task_service.update_task(task_id, task_in, db, principal=principal)
