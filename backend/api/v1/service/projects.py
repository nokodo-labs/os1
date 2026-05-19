"""service layer for project operations."""

from __future__ import annotations

from typing import TypedDict

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql import Select

from api.database import build_cursor_page, decode_cursor
from api.models.access_rule import AccessLevel
from api.models.calendar import Calendar
from api.models.event import Event, EventScope
from api.models.event_types import EventType
from api.models.file import File
from api.models.many_to_many import (
	calendar_project_association,
	file_project_association,
	note_project_association,
	reminder_list_project_association,
	thread_project_association,
)
from api.models.note import Note
from api.models.project import Project
from api.models.thread import Thread
from api.permissions import ResourceType
from api.schemas.project import Project as ProjectSchema
from api.schemas.project import (
	ProjectCreate,
	ProjectListFilters,
	ProjectResourceCounts,
	ProjectUpdate,
)
from api.schemas.search import (
	CursorPage,
	SearchParams,
	SearchResultItem,
	SearchResultType,
)
from api.v1.service import events as event_service
from api.v1.service.auth import Principal
from api.v1.service.authorization import (
	invalidate_accessible_users_for_resource,
	list_accessible_user_ids,
	require_permission,
	require_resource_access,
	resource_access_predicate,
)
from api.v1.service.listing import SortDir, apply_sort
from api.v1.service.resource_payload_cache import (
	get_or_set_resource_payload_cache,
	invalidate_resource_payload_cache,
)
from nokodo_ai.types.json import JSONObject
from nokodo_ai.utils.search import contains_pattern
from nokodo_ai.utils.typeid import TypeID


class _ProjectResourceCountData(TypedDict):
	thread_count: int
	note_count: int
	file_count: int
	reminder_list_count: int
	calendar_count: int
	resource_count: int


def _empty_project_resource_counts() -> _ProjectResourceCountData:
	return {
		"thread_count": 0,
		"note_count": 0,
		"file_count": 0,
		"reminder_list_count": 0,
		"calendar_count": 0,
		"resource_count": 0,
	}


async def invalidate_project_payload_caches(project_ids: set[TypeID]) -> None:
	for project_id in project_ids:
		await invalidate_resource_payload_cache(ResourceType.PROJECT, project_id)


async def _load_project_resource_counts(
	project_ids: set[TypeID],
	session: AsyncSession,
) -> dict[TypeID, _ProjectResourceCountData]:
	counts = {
		project_id: _empty_project_resource_counts() for project_id in project_ids
	}
	if not project_ids:
		return counts

	thread_rows = await session.execute(
		select(
			thread_project_association.c.project_id,
			func.count(thread_project_association.c.thread_id),
		)
		.join(Thread, Thread.id == thread_project_association.c.thread_id)
		.where(
			thread_project_association.c.project_id.in_(project_ids),
			Thread.deleted_at.is_(None),
		)
		.group_by(thread_project_association.c.project_id)
	)
	for project_id, count in thread_rows.all():
		counts[TypeID(str(project_id))]["thread_count"] = int(count)

	note_rows = await session.execute(
		select(
			note_project_association.c.project_id,
			func.count(note_project_association.c.note_id),
		)
		.join(Note, Note.id == note_project_association.c.note_id)
		.where(
			note_project_association.c.project_id.in_(project_ids),
			Note.deleted_at.is_(None),
		)
		.group_by(note_project_association.c.project_id)
	)
	for project_id, count in note_rows.all():
		counts[TypeID(str(project_id))]["note_count"] = int(count)

	file_rows = await session.execute(
		select(
			file_project_association.c.project_id,
			func.count(file_project_association.c.file_id),
		)
		.join(File, File.id == file_project_association.c.file_id)
		.where(
			file_project_association.c.project_id.in_(project_ids),
			File.deleted_at.is_(None),
		)
		.group_by(file_project_association.c.project_id)
	)
	for project_id, count in file_rows.all():
		counts[TypeID(str(project_id))]["file_count"] = int(count)

	reminder_list_rows = await session.execute(
		select(
			reminder_list_project_association.c.project_id,
			func.count(reminder_list_project_association.c.reminder_list_id),
		)
		.where(reminder_list_project_association.c.project_id.in_(project_ids))
		.group_by(reminder_list_project_association.c.project_id)
	)
	for project_id, count in reminder_list_rows.all():
		counts[TypeID(str(project_id))]["reminder_list_count"] = int(count)

	calendar_rows = await session.execute(
		select(
			calendar_project_association.c.project_id,
			func.count(calendar_project_association.c.calendar_id),
		)
		.join(Calendar, Calendar.id == calendar_project_association.c.calendar_id)
		.where(calendar_project_association.c.project_id.in_(project_ids))
		.group_by(calendar_project_association.c.project_id)
	)
	for project_id, count in calendar_rows.all():
		counts[TypeID(str(project_id))]["calendar_count"] = int(count)

	for count_set in counts.values():
		count_set["resource_count"] = (
			count_set["thread_count"]
			+ count_set["note_count"]
			+ count_set["file_count"]
			+ count_set["reminder_list_count"]
			+ count_set["calendar_count"]
		)
	return counts


def _project_payload(project: Project) -> ProjectSchema:
	return ProjectSchema.model_validate(project)


def _project_payloads(projects: list[Project]) -> list[ProjectSchema]:
	return [ProjectSchema.model_validate(project) for project in projects]


def _project_search_metadata(project: Project) -> JSONObject:
	return {
		"resource_type": "project",
		"owner_id": str(project.owner_id),
	}


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
) -> ProjectSchema:
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
	await event_service.persist_and_fanout_event(
		session,
		event=event,
		origin_session_id=origin_session_id,
	)
	return _project_payload(await _get_project(project_id, session))


async def list_projects(
	session: AsyncSession,
	principal: Principal,
	filters: ProjectListFilters | None = None,
	skip: int = 0,
	limit: int = 50,
	sort_by: str = "updated_at",
	sort_dir: SortDir = "desc",
) -> list[ProjectSchema]:
	"""list projects accessible by the principal."""
	predicate = resource_access_predicate(
		principal,
		ResourceType.PROJECT,
		required_level=AccessLevel.READER,
	)
	project_filters = filters or ProjectListFilters()
	base_stmt = _apply_project_filters(
		select(Project).where(predicate), project_filters
	)
	stmt = apply_sort(
		base_stmt.options(selectinload(Project.threads)),
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
	projects = list(result.scalars().unique().all())
	return _project_payloads(projects)


async def count_projects(
	session: AsyncSession,
	principal: Principal,
	filters: ProjectListFilters | None = None,
) -> int:
	"""count projects accessible by the principal."""
	project_filters = filters or ProjectListFilters()
	stmt = (
		select(func.count())
		.select_from(Project)
		.where(
			resource_access_predicate(
				principal,
				ResourceType.PROJECT,
				required_level=AccessLevel.READER,
			)
		)
	)
	stmt = _apply_project_filters(stmt, project_filters)
	return await session.scalar(stmt) or 0


def _apply_project_filters(stmt: Select, filters: ProjectListFilters) -> Select:
	"""apply project list/count filters."""
	if filters.owner_id is not None:
		stmt = stmt.where(Project.owner_id == filters.owner_id)
	return stmt


async def search_projects(
	query_text: str,
	session: AsyncSession,
	principal: Principal,
	limit: int = 10,
	cursor: str | None = None,
	search_params: SearchParams | None = None,
) -> CursorPage[SearchResultItem]:
	"""search accessible projects by name and description with pg_trgm."""
	pattern = contains_pattern(query_text)
	description_text = func.coalesce(Project.description, "")
	search_score = func.greatest(
		func.similarity(Project.name, query_text),
		func.similarity(description_text, query_text),
	)
	predicate = resource_access_predicate(
		principal,
		ResourceType.PROJECT,
		required_level=AccessLevel.READER,
	)
	stmt = (
		select(Project, search_score.label("search_score"))
		.where(
			predicate,
			or_(
				search_score > 0.1,
				Project.name.ilike(pattern, escape="\\"),
				Project.description.ilike(pattern, escape="\\"),
			),
		)
		.order_by(search_score.desc(), Project.updated_at.desc(), Project.id.desc())
		.limit(limit + 1)
	)
	result = await session.execute(stmt)
	items: list[SearchResultItem] = []
	for project, score in result.all():
		items.append(
			SearchResultItem(
				type=SearchResultType.PROJECT,
				id=TypeID(project.id),
				title=project.name,
				preview=project.description[:100] if project.description else None,
				score=float(score) if score is not None else None,
				metadata=_project_search_metadata(project),
				created_at=project.created_at,
				updated_at=project.updated_at,
			)
		)
	if cursor:
		timestamp, cursor_id = decode_cursor(cursor)
		items = [
			item
			for item in items
			if (item.updated_at, str(item.id)) < (timestamp, cursor_id)
		]
	items.sort(key=lambda item: (item.updated_at, str(item.id)), reverse=True)
	return build_cursor_page(items, limit, sort_key="updated_at")


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
		return _project_payload(await _get_project(project_id, session))

	if not use_cache:
		return await load_payload()
	return await get_or_set_resource_payload_cache(
		ResourceType.PROJECT,
		project_id,
		ProjectSchema,
		load_payload,
	)


async def get_project_resource_counts(
	project_id: TypeID,
	session: AsyncSession,
	principal: Principal,
) -> ProjectResourceCounts:
	"""get resource counts for a project after access is validated."""
	await require_resource_access(
		project_id,
		session,
		principal,
		ResourceType.PROJECT,
		required_level=AccessLevel.READER,
	)
	counts = await _load_project_resource_counts({project_id}, session)
	return ProjectResourceCounts.model_validate(
		counts.get(project_id, _empty_project_resource_counts())
	)


async def update_project(
	project_id: TypeID,
	project_in: ProjectUpdate,
	session: AsyncSession,
	principal: Principal,
	origin_session_id: str | None = None,
) -> ProjectSchema:
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
	await event_service.persist_and_fanout_event(
		session,
		event=event,
		origin_session_id=origin_session_id,
	)
	await invalidate_resource_payload_cache(ResourceType.PROJECT, project_id)
	await _invalidate_thread_payload_caches(thread_ids)
	return _project_payload(await _get_project(project_id, session))


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
	delete_recipients = await list_accessible_user_ids(
		ResourceType.PROJECT,
		project_id,
		session,
	)
	await invalidate_accessible_users_for_resource(
		ResourceType.PROJECT, project_id, session
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
	await event_service.persist_and_fanout_event(
		session,
		event=event,
		origin_session_id=origin_session_id,
		recipient_ids=delete_recipients,
	)
	await invalidate_project_payload_caches({project_id})
	await _invalidate_resource_payload_caches(dependent_resource_ids)
