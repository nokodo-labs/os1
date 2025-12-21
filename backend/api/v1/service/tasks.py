"""Service helpers for tasks."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.task import Task, TaskStatus
from api.schemas.task import TaskCreate, TaskUpdate
from api.v1.service.auth import Principal


def _apply_updates(task: Task, updates: dict[str, object]) -> None:
	for field, value in updates.items():
		setattr(task, field, value)


async def _get_task(task_id: str, session: AsyncSession, principal: Principal) -> Task:
	stmt = select(Task).where(Task.id == task_id)
	if not principal.is_admin:
		stmt = stmt.where(Task.user_id == principal.user.id)
	task = (await session.execute(stmt)).scalar_one_or_none()
	if task is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Task not found",
		)
	return task


async def create_task(
	task_in: TaskCreate,
	session: AsyncSession,
	*,
	principal: Principal,
) -> Task:
	data = task_in.model_dump(by_alias=True)
	if not principal.is_admin:
		data["user_id"] = principal.user.id
	task = Task(**data)
	session.add(task)
	await session.commit()
	await session.refresh(task)
	return task


async def list_tasks(
	session: AsyncSession,
	*,
	principal: Principal,
	user_id: str | None = None,
	status_filter: TaskStatus | None = None,
	skip: int = 0,
	limit: int = 50,
) -> list[Task]:
	stmt = select(Task).order_by(Task.created_at.desc())

	if principal.is_admin:
		if user_id is not None:
			stmt = stmt.where(Task.user_id == user_id)
	else:
		stmt = stmt.where(Task.user_id == principal.user.id)

	if status_filter is not None:
		stmt = stmt.where(Task.status == status_filter)

	result = await session.execute(stmt.offset(skip).limit(limit))
	return list(result.scalars().all())


async def update_task(
	task_id: str,
	task_in: TaskUpdate,
	session: AsyncSession,
	*,
	principal: Principal,
) -> Task:
	task = await _get_task(task_id, session, principal)
	updates = task_in.model_dump(exclude_unset=True, by_alias=True)

	if updates:
		updates["last_event_at"] = datetime.now(tz=UTC)
		_apply_updates(task, updates)
		await session.commit()
		await session.refresh(task)

	return task
