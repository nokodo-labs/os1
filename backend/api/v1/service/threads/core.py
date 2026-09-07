"""thread listing + lifecycle: read, update, soft-delete and restore."""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.database.advisory_locks import acquire_resource_write_lock
from api.models.access_rule import AccessLevel
from api.models.event import Event, EventScope
from api.models.event_types import EventType
from api.models.project import Project
from api.models.thread import Thread
from api.models.user import User
from api.permissions import ResourceType
from api.schemas.thread import Thread as ThreadOut
from api.schemas.thread import (
	ThreadListFilters,
	ThreadUpdate,
)
from api.settings import settings
from api.v1.service.authentication import Principal
from api.v1.service.authorization import (
	PreparedAccessChange,
	apply_metadata_write,
	build_access_change_events,
	capture_access_change,
	enqueue_accessible_users_version_drop,
	fetch_bulk_acl_metadata,
	invalidate_accessible_users_for_resource,
	list_accessible_user_ids_for_resources,
	project_private,
	public_payload,
	require_private_write,
	require_thread_access,
	resource_access_predicate,
)
from api.v1.service.events import (
	fanout_event,
	persist_and_fanout_event,
)
from api.v1.service.listing import SortDir
from api.v1.service.projects import load_projects
from api.v1.service.resource_payload_cache import (
	get_or_set_resource_payload_cache,
	invalidate_resource_payload_cache,
)
from api.v1.service.threads.common import (
	apply_thread_filters,
	apply_thread_sort,
	base_thread_list_stmt,
	ensure_admin_for_hidden_or_deleted,
	load_thread,
	load_thread_payload_source,
)
from api.v1.service.threads.content_vectors import (
	purge_thread_content_vectors,
	reconcile_thread_content_vectors,
)
from api.v1.service.threads.members import build_thread_payload
from api.v1.service.threads.search import THREAD_SPEC
from api.v1.service.threads.user_state import apply_participant_state_filters
from api.v1.service.vectorize import (
	remove_vectorized_resource,
	sync_resource_refs_vector_acl,
	vectorize_resource,
)
from nokodo_ai.utils.typeid import TypeID


logger = logging.getLogger(__name__)


async def filter_active_thread_ids(
	session: AsyncSession,
	thread_ids: set[TypeID],
) -> set[TypeID]:
	"""return IDs belonging to existing non-deleted threads."""
	if not thread_ids:
		return set()
	return set(
		await session.scalars(
			select(Thread.id).where(
				Thread.id.in_(thread_ids),
				Thread.deleted_at.is_(None),
			)
		)
	)


@dataclass(slots=True)
class PreparedThreadDeletion:
	"""authorized state required to delete a thread."""

	thread: Thread
	permanent: bool
	owner_id: str
	project_ids: set[TypeID]


async def _invalidate_project_payload_caches(project_ids: set[TypeID]) -> None:
	for project_id in project_ids:
		await invalidate_resource_payload_cache(ResourceType.PROJECT, project_id)


async def list_threads(
	session: AsyncSession,
	principal: Principal,
	filters: ThreadListFilters | None = None,
	skip: int = 0,
	limit: int = 20,
	sort_by: str = "updated_at",
	sort_dir: SortDir = "desc",
) -> list[Thread]:
	"""list accessible threads matching the filters.

	the result depends on the principal only through ACCESS; per-user views
	(archived, pinned, muted, pending invites) are requested through the
	explicit user-addressed filters.
	"""
	thread_filters = filters or ThreadListFilters()
	stmt = base_thread_list_stmt(principal)
	stmt = apply_thread_filters(stmt, thread_filters, principal)
	stmt = apply_participant_state_filters(stmt, thread_filters, principal)
	stmt = apply_thread_sort(stmt, sort_by, sort_dir)
	result = await session.execute(stmt.offset(skip).limit(limit))
	return list(result.scalars().unique().all())


async def count_threads(
	session: AsyncSession,
	principal: Principal,
	filters: ThreadListFilters | None = None,
) -> int:
	"""count threads matching the list filters (see ``list_threads``)."""
	thread_filters = filters or ThreadListFilters()
	stmt = (
		select(func.count())
		.select_from(Thread)
		.where(
			resource_access_predicate(
				principal,
				ResourceType.THREAD,
				required_level=AccessLevel.READER,
			)
		)
	)
	stmt = apply_thread_filters(stmt, thread_filters, principal)
	stmt = apply_participant_state_filters(stmt, thread_filters, principal)
	return await session.scalar(stmt) or 0


async def get_thread(
	thread_id: TypeID,
	session: AsyncSession,
	principal: Principal,
	include_hidden: bool = False,
	include_deleted: bool = False,
) -> Thread:
	ensure_admin_for_hidden_or_deleted(include_hidden, include_deleted, principal)
	return await load_thread(
		thread_id,
		session,
		principal,
		required_level=AccessLevel.READER,
		include_hidden=include_hidden,
		include_deleted=include_deleted,
	)


async def get_thread_payload(
	thread_id: TypeID,
	session: AsyncSession,
	principal: Principal,
	include_hidden: bool = False,
	include_deleted: bool = False,
	use_cache: bool = True,
) -> ThreadOut:
	"""get a thread API payload after access is validated."""
	ensure_admin_for_hidden_or_deleted(include_hidden, include_deleted, principal)
	await require_thread_access(
		thread_id,
		session,
		principal,
		required_level=AccessLevel.READER,
		include_hidden=include_hidden,
		include_deleted=include_deleted,
	)

	async def load_payload() -> ThreadOut:
		return await build_thread_payload(
			session,
			await load_thread_payload_source(
				thread_id,
				session,
				include_hidden,
				include_deleted,
			),
		)

	# the payload cache is not principal-keyed, so it holds the full payload
	# and projection happens per request on the way out.
	if not use_cache:
		payload = await load_payload()
	else:
		payload = await get_or_set_resource_payload_cache(
			ResourceType.THREAD,
			thread_id,
			ThreadOut,
			load_payload,
			variant=(
				"hidden_deleted"
				if include_hidden and include_deleted
				else "hidden"
				if include_hidden
				else "deleted"
				if include_deleted
				else "default"
			),
		)
	return project_private(principal, ResourceType.THREAD, [payload])[0]


async def update_thread(
	thread_id: TypeID,
	thread_in: ThreadUpdate,
	session: AsyncSession,
	principal: Principal,
	create_event: bool = True,
	origin_session_id: str | None = None,
	update_activity: bool = True,
) -> Thread:
	require_private_write(principal, ResourceType.THREAD, thread_in.private)
	thread = await load_thread(
		thread_id,
		session,
		principal,
		required_level=AccessLevel.EDITOR,
	)
	update_data = thread_in.model_dump(
		exclude_unset=True, exclude={"private", "metadata"}
	)
	new_owner_id = update_data.pop("owner_id", None)
	project_ids = update_data.pop("project_ids", None)
	old_project_ids = {project.id for project in thread.projects}
	new_projects: list[Project] | None = None
	new_project_ids: set[TypeID] | None = None
	if project_ids is not None:
		new_projects = await load_projects(
			project_ids, session, principal, required_level=AccessLevel.EDITOR
		)
		new_project_ids = {project.id for project in new_projects}
	owner_will_change = new_owner_id is not None and new_owner_id != thread.owner_id
	projects_will_change = (
		new_project_ids is not None and new_project_ids != old_project_ids
	)
	access_fields_changed = owner_will_change or projects_will_change
	prepared_access_events: list[PreparedAccessChange] = []
	if access_fields_changed:
		access_change = await capture_access_change(
			[(ResourceType.THREAD, thread_id)],
			session,
		)

	owner_changed = False
	if owner_will_change:
		if not principal.user.is_superuser and thread.owner_id != principal.user.id:
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

	changed_project_ids: set[TypeID] = set()
	for field, value in update_data.items():
		setattr(thread, field, value)
	apply_metadata_write(thread, thread_in.metadata, thread_in.private)

	if new_projects is not None:
		thread.projects = new_projects
		changed_project_ids = old_project_ids | {project.id for project in new_projects}

	if update_activity:
		thread.last_activity_at = datetime.now(tz=UTC)

	await session.flush()
	if access_fields_changed:
		prepared_access_events = await build_access_change_events(
			access_change,
			session,
			actor_user_id=principal.user.id,
		)

	# create thread.updated event
	if create_event:
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
			event_data["project_ids"] = [
				str(project_id) for project_id in new_project_ids or set()
			]
			event_data["affected_project_ids"] = [
				str(project_id) for project_id in changed_project_ids
			]
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
		event_recipients = (
			await list_accessible_user_ids_for_resources(
				[
					(ResourceType.THREAD, thread_id),
					*(
						(ResourceType.PROJECT, project_id)
						for project_id in changed_project_ids
					),
				],
				session,
			)
			if changed_project_ids
			else None
		)
		await persist_and_fanout_event(
			session,
			event=event,
			origin_session_id=origin_session_id,
			recipient_ids=event_recipients,
		)
	for prepared in prepared_access_events:
		await fanout_event(
			prepared.event,
			recipient_ids=prepared.recipient_ids,
		)
	await invalidate_resource_payload_cache(ResourceType.THREAD, thread_id)
	# both invalidations happen before the vector-store calls: those reach the
	# network and can raise, rolling back a change whose bust was skipped.
	if owner_changed or new_project_ids is not None:
		# owner recipients changed, or the project set the thread inherits from
		# did.
		await invalidate_accessible_users_for_resource(ResourceType.THREAD, thread_id)

	# re-index if searchable fields changed
	if await THREAD_SPEC.should_revectorize(thread, thread_in, session):
		# summaries is the only relationship the thread point reads (message
		# content lives in passages); unloaded, the dense text degrades to title.
		await session.refresh(thread, attribute_names=["summaries"])
		await vectorize_resource(
			spec=THREAD_SPEC,
			resource=thread,
			session=session,
			extra_metadata=(
				await fetch_bulk_acl_metadata(
					[str(thread.id)], ResourceType.THREAD, session
				)
			)[str(thread.id)],
		)

	if access_fields_changed:
		await sync_resource_refs_vector_acl([(ResourceType.THREAD, thread_id)], session)

	if new_project_ids is not None:
		await _invalidate_project_payload_caches(changed_project_ids)

	if (
		owner_changed
		and not principal.user.is_superuser
		and str(new_owner_id) != str(principal.user.id)
	):
		return await load_thread(thread_id, session, None)

	return await load_thread(
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
	prepared = await prepare_thread_deletion(
		thread_id,
		session,
		principal,
		permanent=permanent,
	)
	await execute_thread_deletion(
		prepared,
		session,
		origin_session_id=origin_session_id,
	)


async def prepare_thread_deletion(
	thread_id: TypeID,
	session: AsyncSession,
	principal: Principal,
	permanent: bool = False,
) -> PreparedThreadDeletion:
	"""authorize a thread deletion and capture its required state."""
	if permanent and not principal.user.is_superuser:
		raise HTTPException(
			status_code=status.HTTP_403_FORBIDDEN,
			detail="forbidden",
		)
	thread = await load_thread(
		thread_id,
		session,
		principal,
		required_level=AccessLevel.EDITOR,
		include_hidden=permanent,
		include_deleted=permanent,
	)

	if not principal.user.is_superuser and thread.owner_id != principal.user.id:
		raise HTTPException(
			status_code=status.HTTP_403_FORBIDDEN,
			detail="forbidden",
		)

	return PreparedThreadDeletion(
		thread=thread,
		permanent=permanent,
		owner_id=str(thread.owner_id),
		project_ids={project.id for project in thread.projects},
	)


async def execute_thread_deletion(
	prepared: PreparedThreadDeletion,
	session: AsyncSession,
	origin_session_id: str | None = None,
) -> None:
	"""execute an authorized thread deletion."""
	thread = prepared.thread
	thread_id = thread.id
	permanent = prepared.permanent
	owner_id = prepared.owner_id
	project_ids = prepared.project_ids
	await acquire_resource_write_lock(session, "thread", thread_id)

	hard_delete = permanent or not settings.soft_delete.threads
	# resolve recipients before the row is gone so hard-deletes still notify
	# everyone who had access. soft-deletes can resolve post-commit normally.
	delete_recipients: list[TypeID] | None = None
	if hard_delete:
		delete_recipients = await list_accessible_user_ids_for_resources(
			[
				(ResourceType.THREAD, thread_id),
				*((ResourceType.PROJECT, project_id) for project_id in project_ids),
			],
			session,
		)

	if hard_delete:
		# the row is gone for good, so reap the counter rather than bump a key
		# nothing will read again; a soft delete keeps the row and only invalidates.
		enqueue_accessible_users_version_drop(ResourceType.THREAD, thread_id, session)
		await session.delete(thread)
	else:
		await invalidate_accessible_users_for_resource(ResourceType.THREAD, thread_id)
		thread.soft_delete()
	await session.flush()

	# emit thread.deleted event
	event = Event(
		scope=EventScope.THREAD,
		scope_id=str(thread_id),
		type=EventType.THREAD_DELETED,
		data={
			"id": str(thread_id),
			"project_ids": [str(project_id) for project_id in project_ids],
			"affected_project_ids": [str(project_id) for project_id in project_ids],
		},
		user_id=owner_id,
		thread_id=str(thread_id),
	)
	await persist_and_fanout_event(
		session,
		event=event,
		origin_session_id=origin_session_id,
		recipient_ids=delete_recipients,
	)
	await invalidate_resource_payload_cache(ResourceType.THREAD, thread_id)

	await remove_vectorized_resource(
		THREAD_SPEC, resource_id=str(thread_id), session=session
	)
	# transcript passages are a second tier keyed by their own resource_id, so
	# the thread-point removal above never matches them.
	await purge_thread_content_vectors(session, thread_ids=[thread_id])
	await _invalidate_project_payload_caches(project_ids)


async def restore_thread(
	thread_id: TypeID,
	session: AsyncSession,
	principal: Principal,
	origin_session_id: str | None = None,
) -> Thread:
	if not principal.user.is_superuser:
		raise HTTPException(
			status_code=status.HTTP_403_FORBIDDEN,
			detail="forbidden",
		)
	thread = await load_thread(
		thread_id,
		session,
		principal,
		required_level=AccessLevel.EDITOR,
		include_deleted=True,
	)
	if thread.deleted_at is None:
		return thread
	project_ids = {project.id for project in thread.projects}
	thread.restore()
	await session.flush()
	# the flush expires server-side onupdate columns
	# summaries is loaded here too since the revectorize below reads it.
	await session.refresh(thread, attribute_names=["updated_at", "summaries"])
	event = Event(
		scope=EventScope.THREAD,
		scope_id=str(thread_id),
		type=EventType.THREAD_UPDATED,
		data=public_payload(ThreadOut.model_validate(thread)).model_dump(mode="json"),
		user_id=str(thread.owner_id),
		thread_id=str(thread_id),
	)
	await persist_and_fanout_event(
		session,
		event=event,
		origin_session_id=origin_session_id,
	)
	await invalidate_resource_payload_cache(ResourceType.THREAD, thread_id)
	await invalidate_accessible_users_for_resource(ResourceType.THREAD, thread_id)
	await vectorize_resource(
		spec=THREAD_SPEC,
		resource=thread,
		session=session,
		extra_metadata=(
			await fetch_bulk_acl_metadata(
				[str(thread.id)], ResourceType.THREAD, session
			)
		)[str(thread.id)],
	)
	# delete purged the passage tier, so restore has to rebuild it
	await reconcile_thread_content_vectors(session, thread_ids=[thread_id])
	await _invalidate_project_payload_caches(project_ids)
	return thread
