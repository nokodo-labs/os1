"""service helpers for group operations."""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql import Select

from api.models.access_rule import AccessLevel
from api.models.event import Event, EventScope
from api.models.event_types import EventType
from api.models.group import GROUP_TYPEID_PREFIX, Group, GroupMembership
from api.permissions import ResourceType
from api.schemas.group import (
	GroupCreate,
	GroupListFilters,
	GroupMembershipCreate,
	GroupUpdate,
)
from api.v1.service import events as event_service
from api.v1.service.auth import Principal
from api.v1.service.authorization import (
	invalidate_accessible_users_for_subject,
	require_permission,
	require_resource_access,
	resource_access_predicate,
)
from api.v1.service.listing import SortDir, apply_sort, exact_typeid_filter
from nokodo_ai.utils.search import contains_pattern
from nokodo_ai.utils.typeid import TypeID


def _apply_group_filters(stmt: Select, group_filters: GroupListFilters) -> Select:
	"""apply group list/count filters."""
	if group_filters.user_id is not None:
		stmt = stmt.join(
			GroupMembership,
			GroupMembership.group_id == Group.id,
		).where(GroupMembership.user_id == group_filters.user_id)
	if group_filters.q and group_filters.q.strip():
		pattern = contains_pattern(group_filters.q.strip())
		stmt = stmt.where(
			or_(
				Group.name.ilike(pattern, escape="\\"),
				Group.description.ilike(pattern, escape="\\"),
				exact_typeid_filter(Group.id, group_filters.q, GROUP_TYPEID_PREFIX),
			)
		)
	return stmt


async def list_groups(
	session: AsyncSession,
	principal: Principal,
	filters: GroupListFilters | None = None,
	skip: int = 0,
	limit: int = 100,
	sort_by: str = "updated_at",
	sort_dir: SortDir = "desc",
) -> list[Group]:
	"""list groups accessible by the principal."""
	group_filters = filters or GroupListFilters()
	stmt = select(Group).where(
		resource_access_predicate(
			principal,
			ResourceType.GROUP,
			required_level=AccessLevel.READER,
		)
	)
	stmt = _apply_group_filters(stmt, group_filters)
	stmt = apply_sort(
		stmt,
		sort_by=sort_by,
		sort_dir=sort_dir,
		columns={
			"created_at": Group.created_at,
			"updated_at": Group.updated_at,
			"name": Group.name,
		},
		tie_breaker=Group.id,
	)
	result = await session.execute(
		stmt.offset(skip).limit(limit).options(selectinload(Group.memberships))
	)
	return list(result.scalars().all())


async def count_groups(
	session: AsyncSession,
	principal: Principal,
	filters: GroupListFilters | None = None,
) -> int:
	"""count groups accessible by the principal."""
	group_filters = filters or GroupListFilters()
	stmt = (
		select(func.count())
		.select_from(Group)
		.where(
			resource_access_predicate(
				principal,
				ResourceType.GROUP,
				required_level=AccessLevel.READER,
			)
		)
	)
	stmt = _apply_group_filters(stmt, group_filters)
	return await session.scalar(stmt) or 0


async def get_group(
	group_id: TypeID,
	session: AsyncSession,
	principal: Principal,
) -> Group:
	"""get a group by id (requires reader access)."""
	await require_resource_access(
		group_id,
		session,
		principal,
		ResourceType.GROUP,
		required_level=AccessLevel.READER,
	)
	result = await session.execute(
		select(Group)
		.where(Group.id == group_id)
		.options(selectinload(Group.memberships))
	)
	group = result.scalar_one_or_none()
	if not group:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="group not found",
		)
	return group


async def create_group(
	group_in: GroupCreate,
	session: AsyncSession,
	principal: Principal,
	origin_session_id: str | None = None,
) -> Group:
	"""create a new group. the creator becomes the owner."""
	require_permission(principal, "groups:create")
	group = Group(
		name=group_in.name,
		description=group_in.description,
		metadata_=group_in.metadata,
		owner_id=str(principal.user.id),
	)
	session.add(group)
	await session.flush()

	# add creator as owner member
	membership = GroupMembership(
		group_id=str(group.id),
		user_id=str(principal.user.id),
		role="owner",
	)
	session.add(membership)
	await session.flush()
	await session.refresh(group)
	group_id = str(group.id)
	event = Event(
		scope=EventScope.USER,
		scope_id=principal.user_id,
		type=EventType.GROUP_CREATED,
		data={"id": group_id, "name": group.name},
		user_id=principal.user_id,
	)
	await event_service.publish_event(
		session,
		event=event,
		origin_session_id=origin_session_id,
	)
	return group


async def update_group(
	group_id: TypeID,
	group_in: GroupUpdate,
	session: AsyncSession,
	principal: Principal,
	origin_session_id: str | None = None,
) -> Group:
	"""update group details (requires editor access)."""
	await require_resource_access(
		group_id,
		session,
		principal,
		ResourceType.GROUP,
		required_level=AccessLevel.EDITOR,
	)
	group = await _load_group(group_id, session)
	update_data = group_in.model_dump(exclude_unset=True, by_alias=True)
	for key, value in update_data.items():
		setattr(group, key, value)
	session.add(group)
	await session.flush()
	await session.refresh(group)
	event = Event(
		scope=EventScope.USER,
		scope_id=principal.user_id,
		type=EventType.GROUP_UPDATED,
		data={"id": str(group_id), "name": group.name},
		user_id=principal.user_id,
	)
	await event_service.publish_event(
		session,
		event=event,
		origin_session_id=origin_session_id,
	)
	return group


async def delete_group(
	group_id: TypeID,
	session: AsyncSession,
	principal: Principal,
	origin_session_id: str | None = None,
) -> None:
	"""delete a group (requires admin access)."""
	await require_resource_access(
		group_id,
		session,
		principal,
		ResourceType.GROUP,
		required_level=AccessLevel.ADMIN,
	)
	group = await _load_group(group_id, session)
	# invalidate BEFORE publish_event commits - the CASCADE delete of
	# access rules means the rows are gone after commit and the query
	# inside invalidate_accessible_users_for_subject would find nothing.
	await invalidate_accessible_users_for_subject("group", group_id, session)
	await session.delete(group)
	event = Event(
		scope=EventScope.USER,
		scope_id=principal.user_id,
		type=EventType.GROUP_DELETED,
		data={"id": str(group_id)},
		user_id=principal.user_id,
	)
	await event_service.publish_event(
		session,
		event=event,
		origin_session_id=origin_session_id,
	)


# membership management


async def add_member(
	group_id: TypeID,
	member_in: GroupMembershipCreate,
	session: AsyncSession,
	principal: Principal,
	origin_session_id: str | None = None,
) -> GroupMembership:
	"""add a user to a group (requires editor access on the group)."""
	await require_resource_access(
		group_id,
		session,
		principal,
		ResourceType.GROUP,
		required_level=AccessLevel.EDITOR,
	)
	existing = await session.execute(
		select(GroupMembership).where(
			GroupMembership.group_id == group_id,
			GroupMembership.user_id == str(member_in.user_id),
		)
	)
	if existing.scalar_one_or_none():
		raise HTTPException(
			status_code=status.HTTP_409_CONFLICT,
			detail="user is already a member",
		)
	membership = GroupMembership(
		group_id=group_id,
		user_id=str(member_in.user_id),
		role=member_in.role,
	)
	session.add(membership)
	await session.flush()
	await session.refresh(membership)
	event = Event(
		scope=EventScope.USER,
		scope_id=principal.user_id,
		type=EventType.GROUP_MEMBER_ADDED,
		data={
			"group_id": group_id,
			"user_id": str(member_in.user_id),
			"role": member_in.role,
		},
		user_id=principal.user_id,
	)
	await event_service.publish_event(
		session,
		event=event,
		origin_session_id=origin_session_id,
	)
	# group membership affects accessible_users for every resource that has
	# an access rule referencing this group. invalidate exactly those.
	await invalidate_accessible_users_for_subject(
		subject_kind="group", subject_id=group_id, session=session
	)
	return membership


async def remove_member(
	group_id: TypeID,
	user_id: TypeID,
	session: AsyncSession,
	principal: Principal,
	origin_session_id: str | None = None,
) -> None:
	"""remove a user from a group (requires editor access)."""
	await require_resource_access(
		group_id,
		session,
		principal,
		ResourceType.GROUP,
		required_level=AccessLevel.EDITOR,
	)
	result = await session.execute(
		select(GroupMembership).where(
			GroupMembership.group_id == group_id,
			GroupMembership.user_id == str(user_id),
		)
	)
	membership = result.scalar_one_or_none()
	if not membership:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="membership not found",
		)
	await session.delete(membership)
	event = Event(
		scope=EventScope.USER,
		scope_id=principal.user_id,
		type=EventType.GROUP_MEMBER_REMOVED,
		data={
			"group_id": group_id,
			"user_id": str(user_id),
		},
		user_id=principal.user_id,
	)
	await event_service.publish_event(
		session,
		event=event,
		origin_session_id=origin_session_id,
	)
	await invalidate_accessible_users_for_subject(
		subject_kind="group", subject_id=group_id, session=session
	)


# internal helpers


async def _load_group(group_id: TypeID, session: AsyncSession) -> Group:
	result = await session.execute(
		select(Group)
		.where(Group.id == group_id)
		.options(selectinload(Group.memberships))
	)
	group = result.scalar_one_or_none()
	if not group:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="group not found",
		)
	return group
