"""Task endpoints."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.database import get_db
from api.models.task import Task, TaskStatus
from api.schemas.task import Task as TaskSchema
from api.schemas.task import TaskCreate, TaskUpdate


router = APIRouter(prefix="/tasks", tags=["tasks"])


def _apply_updates(task: Task, updates: dict[str, object]) -> None:
	for field, value in updates.items():
		setattr(task, field, value)


async def _get_task(task_id: str, db: AsyncSession) -> Task:
	task = await db.get(Task, task_id)
	if not task:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Task not found",
		)
	return task


@router.post("", response_model=TaskSchema, status_code=status.HTTP_201_CREATED)
async def create_task(
	task_in: TaskCreate,
	db: AsyncSession = Depends(get_db),
) -> Task:
	"""Create a new task."""
	task = Task(**task_in.model_dump(by_alias=True))
	db.add(task)
	await db.commit()
	await db.refresh(task)
	return task


@router.get("", response_model=list[TaskSchema])
async def list_tasks(
	user_id: int | None = None,
	status_filter: TaskStatus | None = None,
	skip: int = 0,
	limit: int = 50,
	db: AsyncSession = Depends(get_db),
) -> list[Task]:
	"""List tasks with optional filters."""
	stmt = select(Task).order_by(Task.created_at.desc())

	if user_id is not None:
		stmt = stmt.where(Task.user_id == user_id)

	if status_filter is not None:
		stmt = stmt.where(Task.status == status_filter)

	result = await db.execute(stmt.offset(skip).limit(limit))
	return list(result.scalars().all())


@router.patch("/{task_id}", response_model=TaskSchema)
async def update_task(
	task_id: str,
	task_in: TaskUpdate,
	db: AsyncSession = Depends(get_db),
) -> Task:
	"""Update mutable task fields."""
	task = await _get_task(task_id, db)
	updates = task_in.model_dump(exclude_unset=True, by_alias=True)

	if updates:
		updates["last_event_at"] = datetime.now(tz=UTC)
		_apply_updates(task, updates)
		await db.commit()
		await db.refresh(task)

	return task
