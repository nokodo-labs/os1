"""service layer for project operations."""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.models.access_rule import AccessLevel
from api.models.event import Event, EventScope
from api.models.event_types import EventType
from api.models.many_to_many import (
	calendar_project_association,
	file_project_association,
	note_project_association,
	reminder_list_project_association,
	thread_project_association,
)
from api.models.project import Project
from api.permissions import ResourceType
from api.schemas.project import Project as ProjectSchema
from api.schemas.project import ProjectCreate, ProjectUpdate
from api.v1.service import events as event_service
from api.v1.service.auth import Principal
from api.v1.service.authorization import (
	require_permission,
	require_resource_access,
	resource_access_predicate,
)
from api.v1.service.resource_payload_cache import (
	get_or_set_resource_payload_cache,
	invalidate_resource_payload_cache,
)
from api.v1.service.sorting import SortDir, apply_sort
from nokodo_ai.utils.typeid import TypeID


async def _get_project(project_id: TypeID, session: AsyncSession) -> Project:
	"""fetch a project by id (no access check)."""
	result = await session.execute(
		select(Project)
		.where(Project.id == project_id)
		.options(selectinload(Project.threads))
	)
	project = result.scalars().one_or_none()
	if not project:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="project not found",
		)
	return project


async def _invalidate_thread_payload_caches(thread_ids: set[TypeID]) -> None:
	for thread_id in thread_ids:
		await invalidate_resource_payload_cache(ResourceType.THREAD, thread_id)


async def _load_project_dependent_resource_ids(
	project_id: TypeID,
	session: AsyncSession,
) -> dict[ResourceType, set[TypeID]]:
	thread_ids = {
		TypeID(str(thread_id))
		for thread_id in (
			await session.scalars(
				select(thread_project_association.c.thread_id).where(
					thread_project_association.c.project_id == project_id
				)
			)
		).all()
	}
	file_ids = {
		TypeID(str(file_id))
		for file_id in (
			await session.scalars(
				select(file_project_association.c.file_id).where(
					file_project_association.c.project_id == project_id
				)
			)
		).all()
	}
	note_ids = {
		TypeID(str(note_id))
		for note_id in (
			await session.scalars(
				select(note_project_association.c.note_id).where(
					note_project_association.c.project_id == project_id
				)
			)
		).all()
	}
	reminder_list_ids = {
		TypeID(str(reminder_list_id))
		for reminder_list_id in (
			await session.scalars(
				select(reminder_list_project_association.c.reminder_list_id).where(
					reminder_list_project_association.c.project_id == project_id
				)
			)
		).all()
	}
	calendar_ids = {
		TypeID(str(calendar_id))
		for calendar_id in (
			await session.scalars(
				select(calendar_project_association.c.calendar_id).where(
					calendar_project_association.c.project_id == project_id
				)
			)
		).all()
	}
	return {
		ResourceType.THREAD: thread_ids,
		ResourceType.FILE: file_ids,
		ResourceType.NOTE: note_ids,
		ResourceType.REMINDER_LIST: reminder_list_ids,
		ResourceType.CALENDAR: calendar_ids,
	}


async def _invalidate_resource_payload_caches(
	resource_ids: dict[ResourceType, set[TypeID]],
) -> None:
	for resource_type, ids in resource_ids.items():
		for resource_id in ids:
			await invalidate_resource_payload_cache(resource_type, resource_id)


async def resolve_thread_project_id(
	thread_id: TypeID,
	session: AsyncSession,
) -> TypeID | None:
	"""resolve the project_id associated with a thread, if any."""
	row = (
		await session.execute(
			select(thread_project_association.c.project_id)
			.where(thread_project_association.c.thread_id == thread_id)
			.limit(1)
		)
	).first()
	return row[0] if row else None


async def load_projects(
	project_ids: list[TypeID],
	session: AsyncSession,
	principal: Principal,
	required_level: AccessLevel = AccessLevel.EDITOR,
) -> list[Project]:
	"""load projects with access control; raise 404 for any missing ids."""
	if not project_ids:
		return []

	predicate = resource_access_predicate(
		principal,
		ResourceType.PROJECT,
		required_level=required_level,
	)
	stmt = select(Project).where(Project.id.in_(project_ids), predicate)
	result = await session.scalars(stmt)
	projects = list(result.all())
	found = {project.id for project in projects}
	missing = [pid for pid in project_ids if pid not in found]
	if missing:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail=f"projects not found: {missing}",
		)
	return projects


async def create_project(
	project_in: ProjectCreate,
	session: AsyncSession,
	principal: Principal,
	origin_session_id: str | None = None,
) -> Project:
	"""create a new project. the caller becomes the owner."""
	require_permission(principal, "projects:create")
	data = project_in.model_dump(by_alias=True)
	data["owner_id"] = principal.user_id
	project = Project(**data)
	session.add(project)
	await session.flush()
	await session.refresh(project)
	project_id = project.id
	event = Event(
		scope=EventScope.USER,
		scope_id=principal.user_id,
		type=EventType.PROJECT_CREATED,
		data={
			"id": str(project_id),
			"name": project.name,
		},
		user_id=principal.user_id,
		project_id=project_id,
	)
	await event_service.publish_event(
		session,
		event=event,
		origin_session_id=origin_session_id,
	)
	return await _get_project(project_id, session)


async def list_projects(
	session: AsyncSession,
	principal: Principal,
	skip: int = 0,
	limit: int = 50,
	sort_by: str = "updated_at",
	sort_dir: SortDir = "desc",
) -> list[Project]:
	"""list projects accessible by the principal."""
	predicate = resource_access_predicate(
		principal,
		ResourceType.PROJECT,
		required_level=AccessLevel.READER,
	)
	stmt = apply_sort(
		select(Project).where(predicate).options(selectinload(Project.threads)),
		sort_by=sort_by,
		sort_dir=sort_dir,
		columns={
			"created_at": Project.created_at,
			"updated_at": Project.updated_at,
			"name": Project.name,
		},
		tie_breaker=Project.id,
	)
	result = await session.execute(stmt.offset(skip).limit(limit))
	return list(result.scalars().unique().all())


async def get_project(
	project_id: TypeID,
	session: AsyncSession,
	principal: Principal,
) -> Project:
	"""get a project by id (requires reader access)."""
	await require_resource_access(
		project_id,
		session,
		principal,
		ResourceType.PROJECT,
		required_level=AccessLevel.READER,
	)
	return await _get_project(project_id, session)


async def get_project_payload(
	project_id: TypeID,
	session: AsyncSession,
	principal: Principal,
	use_cache: bool = True,
) -> ProjectSchema:
	"""get a project API payload after resource access is validated."""
	await require_resource_access(
		project_id,
		session,
		principal,
		ResourceType.PROJECT,
		required_level=AccessLevel.READER,
	)

	async def load_payload() -> ProjectSchema:
		return ProjectSchema.model_validate(await _get_project(project_id, session))

	if not use_cache:
		return await load_payload()
	return await get_or_set_resource_payload_cache(
		ResourceType.PROJECT,
		project_id,
		ProjectSchema,
		load_payload,
	)


async def update_project(
	project_id: TypeID,
	project_in: ProjectUpdate,
	session: AsyncSession,
	principal: Principal,
	origin_session_id: str | None = None,
) -> Project:
	"""update a project (requires editor access)."""
	await require_resource_access(
		project_id,
		session,
		principal,
		ResourceType.PROJECT,
		required_level=AccessLevel.EDITOR,
	)
	project = await _get_project(project_id, session)
	thread_ids = {thread.id for thread in project.threads}
	updates = project_in.model_dump(exclude_unset=True, by_alias=True)
	for field, value in updates.items():
		setattr(project, field, value)
	await session.flush()
	await session.refresh(project)
	event = Event(
		scope=EventScope.USER,
		scope_id=principal.user_id,
		type=EventType.PROJECT_UPDATED,
		data={
			"id": str(project_id),
			"name": project.name,
		},
		user_id=principal.user_id,
		project_id=str(project_id),
	)
	await event_service.publish_event(
		session,
		event=event,
		origin_session_id=origin_session_id,
	)
	await invalidate_resource_payload_cache(ResourceType.PROJECT, project_id)
	await _invalidate_thread_payload_caches(thread_ids)
	return await _get_project(project_id, session)


async def delete_project(
	project_id: TypeID,
	session: AsyncSession,
	principal: Principal,
	origin_session_id: str | None = None,
) -> None:
	"""delete a project (requires editor access + ownership or admin)."""
	await require_resource_access(
		project_id,
		session,
		principal,
		ResourceType.PROJECT,
		required_level=AccessLevel.EDITOR,
	)
	project = await _get_project(project_id, session)
	dependent_resource_ids = await _load_project_dependent_resource_ids(
		project_id,
		session,
	)
	if not principal.is_admin and project.owner_id != principal.user_id:
		raise HTTPException(
			status_code=status.HTTP_403_FORBIDDEN,
			detail="forbidden",
		)
	await session.delete(project)
	event = Event(
		scope=EventScope.USER,
		scope_id=principal.user_id,
		type=EventType.PROJECT_DELETED,
		data={"id": str(project_id)},
		user_id=principal.user_id,
		project_id=project_id,
	)
	await event_service.publish_event(
		session,
		event=event,
		origin_session_id=origin_session_id,
	)
	await invalidate_resource_payload_cache(ResourceType.PROJECT, project_id)
	await _invalidate_resource_payload_caches(dependent_resource_ids)
