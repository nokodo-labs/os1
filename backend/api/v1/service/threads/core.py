"""service helpers for threads and messages."""

from __future__ import annotations

import logging
from typing import overload

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.models.access_rule import AccessLevel
from api.models.event import Event, EventScope
from api.models.event_types import EventType
from api.models.message import Message
from api.models.thread import Thread
from api.models.user import User
from api.permissions import ResourceType
from api.schemas.message import Message as MessageOut
from api.schemas.thread import Thread as ThreadOut
from api.schemas.thread import ThreadCreate, ThreadListFilters, ThreadUpdate
from api.settings import settings
from api.v1.service import events as event_service
from api.v1.service import projects as project_service
from api.v1.service.auth import Principal
from api.v1.service.authorization import (
	require_permission,
	require_thread_access,
	thread_access_predicate,
)
from api.v1.service.resource_payload_cache import (
	get_or_set_resource_payload_cache,
	invalidate_resource_payload_cache,
)
from api.v1.service.sorting import SortDir, apply_sort
from api.v1.service.threads.participants import ensure_participant
from api.v1.service.threads.search import THREAD_SPEC
from api.v1.service.vectorize import (
	fetch_acl_metadata,
	remove_vectorized_resource,
	vectorize_resource,
)
from nokodo_ai.utils.typeid import TypeID


logger = logging.getLogger(__name__)


async def _invalidate_project_payload_caches(project_ids: set[TypeID]) -> None:
	for project_id in project_ids:
		await invalidate_resource_payload_cache(ResourceType.PROJECT, project_id)


def _message_event_data(message: Message) -> dict[str, object]:
	"""serialize a message event payload using the public API field names."""
	return MessageOut.model_validate(message).model_dump(mode="json", by_alias=True)


def _ensure_admin_for_hidden(include_hidden: bool, principal: Principal) -> None:
	if include_hidden and not principal.is_admin:
		raise HTTPException(
			status_code=status.HTTP_403_FORBIDDEN,
			detail="forbidden",
		)


@overload
async def _load_thread(
	thread_id: TypeID,
	session: AsyncSession,
	principal: Principal,
	required_level: AccessLevel = AccessLevel.READER,
	include_hidden: bool = False,
) -> Thread: ...


@overload
async def _load_thread(
	thread_id: TypeID,
	session: AsyncSession,
	principal: None = None,
	required_level: AccessLevel = AccessLevel.READER,
	include_hidden: bool = False,
) -> Thread: ...


async def _load_thread(
	thread_id: TypeID,
	session: AsyncSession,
	principal: Principal | None = None,
	required_level: AccessLevel = AccessLevel.READER,
	include_hidden: bool = False,
) -> Thread:
	options = [
		selectinload(Thread.projects),
	]
	stmt = select(Thread).options(*options).where(Thread.id == thread_id)

	if principal is not None:
		stmt = stmt.where(
			thread_access_predicate(
				principal,
				required_level=required_level,
				include_hidden=include_hidden,
			)
		)
		if include_hidden:
			stmt = stmt.execution_options(include_deleted=True)
	else:
		if include_hidden:
			stmt = stmt.execution_options(include_deleted=True)
		else:
			stmt = stmt.where(
				Thread.deleted_at.is_(None), Thread.is_temporary.is_(False)
			)
	result = await session.execute(stmt)
	thread = result.scalars().unique().one_or_none()

	if not thread:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Thread not found",
		)

	return thread


async def _load_thread_payload_source(
	thread_id: TypeID,
	session: AsyncSession,
	include_hidden: bool = False,
) -> Thread:
	stmt = (
		select(Thread)
		.options(selectinload(Thread.projects))
		.where(Thread.id == thread_id)
	)
	if include_hidden:
		stmt = stmt.execution_options(include_deleted=True)
	else:
		stmt = stmt.where(Thread.deleted_at.is_(None))
	result = await session.execute(stmt)
	thread = result.scalars().unique().one_or_none()
	if not thread:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Thread not found",
		)
	return thread


async def create_thread(
	thread_in: ThreadCreate,
	session: AsyncSession,
	principal: Principal,
	origin_session_id: str | None = None,
	override_id: TypeID | None = None,
) -> Thread:
	require_permission(principal, "threads:create")
	owner_id = thread_in.owner_id
	if not principal.is_admin:
		owner_id = TypeID(principal.user.id)
	else:
		owner = await session.get(User, owner_id)
		if not owner:
			raise HTTPException(
				status_code=status.HTTP_404_NOT_FOUND,
				detail="User not found",
			)

	projects = await project_service.load_projects(
		thread_in.project_ids, session, principal, required_level=AccessLevel.EDITOR
	)
	thread_data = thread_in.model_dump(by_alias=True, exclude={"project_ids"})
	thread_data["owner_id"] = owner_id
	if override_id is not None:
		thread_data["id"] = override_id
	thread = Thread(**thread_data)
	thread.projects = projects
	session.add(thread)
	await session.flush()

	# owner is automatically a participant
	await ensure_participant(thread.id, owner_id, session)

	await session.refresh(
		thread, attribute_names=["created_at", "updated_at", "last_activity_at"]
	)

	# emit thread.created event
	event = Event(
		scope=EventScope.THREAD,
		scope_id=thread.id,
		type=EventType.THREAD_CREATED,
		data=ThreadOut.model_validate(thread).model_dump(mode="json"),
		user_id=str(owner_id),
		thread_id=thread.id,
	)
	await event_service.publish_event(
		session, event=event, origin_session_id=origin_session_id
	)
	await _invalidate_project_payload_caches({project.id for project in projects})

	return thread


async def list_threads(
	session: AsyncSession,
	principal: Principal,
	filters: ThreadListFilters | None = None,
	skip: int = 0,
	limit: int = 20,
	sort_by: str = "updated_at",
	sort_dir: SortDir = "desc",
) -> list[Thread]:
	thread_filters = filters or ThreadListFilters()
	_ensure_admin_for_hidden(thread_filters.include_hidden, principal)
	stmt = (
		select(Thread)
		.options(
			selectinload(Thread.messages),
			selectinload(Thread.projects),
		)
		.where(
			thread_access_predicate(
				principal,
				required_level=AccessLevel.READER,
				include_hidden=thread_filters.include_hidden,
			)
		)
	)

	if thread_filters.owner_id is not None:
		stmt = stmt.where(Thread.owner_id == thread_filters.owner_id)

	# always exclude temporary threads from listings
	if not thread_filters.include_hidden:
		stmt = stmt.where(Thread.is_temporary.is_(False))

	if thread_filters.is_archived is not None:
		stmt = stmt.where(Thread.is_archived == thread_filters.is_archived)

	if thread_filters.include_hidden:
		stmt = stmt.execution_options(include_deleted=True)

	stmt = apply_sort(
		stmt,
		sort_by=sort_by,
		sort_dir=sort_dir,
		columns={
			"last_activity_at": Thread.last_activity_at,
			"created_at": Thread.created_at,
			"updated_at": Thread.updated_at,
			"title": Thread.title,
		},
		tie_breaker=Thread.id,
	)

	result = await session.execute(stmt.offset(skip).limit(limit))
	return list(result.scalars().unique().all())


async def get_thread(
	thread_id: TypeID,
	session: AsyncSession,
	principal: Principal,
	include_hidden: bool = False,
) -> Thread:
	_ensure_admin_for_hidden(include_hidden, principal)
	return await _load_thread(
		thread_id,
		session,
		principal,
		required_level=AccessLevel.READER,
		include_hidden=include_hidden,
	)


async def get_thread_payload(
	thread_id: TypeID,
	session: AsyncSession,
	principal: Principal,
	include_hidden: bool = False,
	use_cache: bool = True,
) -> ThreadOut:
	"""get a thread API payload after access is validated."""
	_ensure_admin_for_hidden(include_hidden, principal)
	await require_thread_access(
		thread_id,
		session,
		principal,
		required_level=AccessLevel.READER,
		include_hidden=include_hidden,
	)

	async def load_payload() -> ThreadOut:
		return ThreadOut.model_validate(
			await _load_thread_payload_source(thread_id, session, include_hidden)
		)

	if not use_cache:
		return await load_payload()
	return await get_or_set_resource_payload_cache(
		ResourceType.THREAD,
		thread_id,
		ThreadOut,
		load_payload,
		variant="hidden" if include_hidden else "default",
	)


async def update_thread(
	thread_id: TypeID,
	thread_in: ThreadUpdate,
	session: AsyncSession,
	principal: Principal,
	emit_event: bool = True,
	origin_session_id: str | None = None,
) -> Thread:
	thread = await _load_thread(
		thread_id,
		session,
		principal,
		required_level=AccessLevel.EDITOR,
	)
	update_data = thread_in.model_dump(exclude_unset=True, by_alias=True)
	new_owner_id = update_data.pop("owner_id", None)
	owner_changed = False
	if new_owner_id is not None and new_owner_id != thread.owner_id:
		if not principal.is_admin and thread.owner_id != principal.user.id:
			raise HTTPException(
				status_code=status.HTTP_403_FORBIDDEN,
				detail="forbidden",
			)
		new_owner = await session.get(User, new_owner_id)
		if not new_owner:
			raise HTTPException(
				status_code=status.HTTP_404_NOT_FOUND,
				detail="User not found",
			)
		thread.owner_id = TypeID(new_owner_id)
		thread.owner = new_owner
		owner_changed = True

	# validate current_message_id belongs to this thread
	# TODO: verify perf impact. disabled until then.
	""" new_current_message_id = update_data.pop("current_message_id", None)
	if new_current_message_id is not None:
		msg = await session.get(Message, new_current_message_id)
		if not msg or msg.thread_id != thread_id:
			raise HTTPException(
				status_code=status.HTTP_404_NOT_FOUND,
				detail="Message not found in thread",
			)
		thread.current_message_id = new_current_message_id """

	project_ids = update_data.pop("project_ids", None)
	old_project_ids = {project.id for project in thread.projects}
	for field, value in update_data.items():
		setattr(thread, field, value)

	new_project_ids: set[TypeID] | None = None
	if project_ids is not None:
		projects = await project_service.load_projects(
			project_ids, session, principal, required_level=AccessLevel.EDITOR
		)
		thread.projects = projects
		new_project_ids = {project.id for project in projects}

	await session.flush()

	# emit thread.updated event
	if emit_event:
		await session.refresh(
			thread, attribute_names=["updated_at", "last_activity_at"]
		)
		# partial event: only changed fields + id + timestamps
		event_data = thread_in.model_dump(
			mode="json", exclude_unset=True, by_alias=True
		)
		event_data.pop("project_ids", None)
		event_data["id"] = str(thread.id)
		event_data["updated_at"] = thread.updated_at.isoformat()
		event_data["last_activity_at"] = thread.last_activity_at.isoformat()
		if project_ids is not None:
			event_data["projects"] = [
				{"id": str(p.id), "name": p.name} for p in thread.projects
			]
		event = Event(
			scope=EventScope.THREAD,
			scope_id=thread.id,
			type=EventType.THREAD_UPDATED,
			data=event_data,
			user_id=str(thread.owner_id),
			thread_id=thread.id,
		)
		await event_service.publish_event(
			session, event=event, origin_session_id=origin_session_id
		)
	await invalidate_resource_payload_cache(ResourceType.THREAD, thread_id)

	# re-index if searchable fields changed
	if await THREAD_SPEC.should_revectorize(thread, thread_in, session):
		await session.refresh(thread, attribute_names=["messages"])
		await vectorize_resource(
			spec=THREAD_SPEC,
			resource=thread,
			session=session,
			extra_metadata=await fetch_acl_metadata(
				str(thread.id), ResourceType.THREAD, session
			),
		)

	if new_project_ids is not None:
		await _invalidate_project_payload_caches(old_project_ids | new_project_ids)

	if (
		owner_changed
		and not principal.is_admin
		and str(new_owner_id) != str(principal.user.id)
	):
		return await _load_thread(thread_id, session, None)

	return await _load_thread(
		thread_id,
		session,
		principal,
		required_level=AccessLevel.READER,
	)


async def delete_thread(
	thread_id: TypeID,
	session: AsyncSession,
	principal: Principal,
	origin_session_id: str | None = None,
	permanent: bool = False,
) -> None:
	thread = await _load_thread(
		thread_id,
		session,
		principal,
		required_level=AccessLevel.EDITOR,
	)

	if not principal.is_admin and thread.owner_id != principal.user.id:
		raise HTTPException(
			status_code=status.HTTP_403_FORBIDDEN,
			detail="forbidden",
		)

	if permanent and not principal.is_admin:
		raise HTTPException(
			status_code=status.HTTP_403_FORBIDDEN,
			detail="forbidden",
		)

	owner_id = str(thread.owner_id)
	project_ids = {project.id for project in thread.projects}

	if permanent or not settings.soft_delete.threads:
		await session.delete(thread)
	else:
		thread.soft_delete()
	await session.flush()

	# emit thread.deleted event
	event = Event(
		scope=EventScope.THREAD,
		scope_id=str(thread_id),
		type=EventType.THREAD_DELETED,
		data={"id": str(thread_id)},
		user_id=owner_id,
		thread_id=str(thread_id),
	)
	await event_service.publish_event(
		session, event=event, origin_session_id=origin_session_id
	)
	await invalidate_resource_payload_cache(ResourceType.THREAD, thread_id)

	await remove_vectorized_resource(
		THREAD_SPEC, resource_id=str(thread_id), session=session
	)
	await _invalidate_project_payload_caches(project_ids)
