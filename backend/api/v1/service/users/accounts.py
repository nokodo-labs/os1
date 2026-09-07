"""service helpers for user operations."""

from typing import NoReturn

from fastapi import HTTPException, status
from sqlalchemy import delete, func, insert, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql import Select

from api.database.post_commit import run_post_commit_actions_safely
from api.models.block import Block
from api.models.calendar import Calendar
from api.models.event import Event, EventScope
from api.models.event_types import EventType
from api.models.file import File
from api.models.friendship import Friendship, FriendshipStatus
from api.models.group import Group
from api.models.many_to_many import user_role_association
from api.models.memory import Memory
from api.models.note import Note
from api.models.notification import Notification
from api.models.project import Project
from api.models.reminder import Reminder, ReminderList
from api.models.task import Task
from api.models.thread import Thread
from api.models.user import USER_TYPEID_PREFIX, User
from api.models.user_client import UserClient
from api.permissions import (
	ActionPermission,
	ResourceType,
)
from api.schemas.user import (
	UserCreate,
	UserEmailChange,
	UserPasswordChange,
	UserSortBy,
	UserSummary,
	UserUpdate,
)
from api.settings import settings
from api.v1.service.authentication import Principal, build_principal
from api.v1.service.authentication.cache import (
	invalidate_principals,
	mark_sessions_revoked,
)
from api.v1.service.authentication.sessions import revoke_all_sessions
from api.v1.service.authorization import (
	build_access_change_events,
	capture_access_change,
	enqueue_accessible_users_invalidation_for_subject,
	invalidate_accessible_users_for_resource_types,
	invalidate_accessible_users_for_role_defaults,
	require_permission,
	require_self_or_permission,
	resource_refs_for_subject,
)
from api.v1.service.events import (
	fanout_event,
	persist_and_fanout_event,
	request_socket_kill,
)
from api.v1.service.listing import SortDir, apply_sort, exact_typeid_filter
from api.v1.service.social.privacy import RedactedUser, redact_users
from api.v1.service.social.visibility import user_visibility_predicate
from nokodo_ai.utils.search import contains_pattern
from nokodo_ai.utils.security import hash_password, verify_password
from nokodo_ai.utils.typeid import TypeID


def _apply_admin_user_filters(stmt: Select, q: str | None) -> Select:
	"""apply admin-only user list filters."""
	if not q or not q.strip():
		return stmt
	pattern = contains_pattern(q.strip())
	return stmt.where(
		or_(
			User.email.ilike(pattern, escape="\\"),
			User.username.ilike(pattern, escape="\\"),
			User.display_name.ilike(pattern, escape="\\"),
			exact_typeid_filter(User.id, q, USER_TYPEID_PREFIX),
		)
	)


def _raise_user_integrity_error(exc: IntegrityError) -> NoReturn:
	"""
	inspect IntegrityError for common user creation/update issues
	and raise appropriate HTTP errors.
	"""
	msg = str(exc.orig).lower()
	if "email" in msg and "unique" in msg:
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="email already registered",
		) from None
	if "username" in msg and "unique" in msg:
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="username already taken",
		) from None
	if "foreign key" in msg and "user_roles" in msg:
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail="invalid role reference in auto_signup_role_ids",
		) from None
	raise exc


def _build_user_summary(
	redacted: RedactedUser,
) -> UserSummary:
	"""build a user summary without leaking hidden profile fields."""
	return UserSummary(
		id=redacted.id,
		username=redacted.username,
		display_name=redacted.display_name,
		avatar_url=redacted.avatar_url,
	)


async def list_users(
	session: AsyncSession,
	principal: Principal,
	skip: int = 0,
	limit: int = 100,
	sort_by: UserSortBy = "updated_at",
	sort_dir: SortDir = "desc",
	q: str | None = None,
) -> list[User]:
	require_permission(principal, ActionPermission.USERS_READ)
	stmt = _apply_admin_user_filters(select(User), q)
	stmt = apply_sort(
		stmt,
		sort_by=sort_by,
		sort_dir=sort_dir,
		columns={
			"created_at": User.created_at,
			"updated_at": User.updated_at,
			"email": User.email,
			"display_name": User.display_name,
			"is_active": User.is_active,
			"is_superuser": User.is_superuser,
		},
		tie_breaker=User.id,
	)
	result = await session.execute(stmt.offset(skip).limit(limit))
	return list(result.scalars().all())


async def count_users(
	session: AsyncSession,
	principal: Principal,
	q: str | None = None,
) -> int:
	require_permission(principal, ActionPermission.USERS_READ)
	stmt = _apply_admin_user_filters(select(func.count()).select_from(User), q)
	return await session.scalar(stmt) or 0


async def get_user(
	user_id: TypeID,
	session: AsyncSession,
	principal: Principal,
) -> User:
	require_self_or_permission(user_id, principal, ActionPermission.USERS_READ)

	result = await session.execute(select(User).where(User.id == user_id))
	user = result.scalar_one_or_none()

	if not user:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="user not found",
		)

	return user


async def get_accessible_user_summaries(
	user_ids: list[TypeID],
	session: AsyncSession,
	principal: Principal,
) -> list[UserSummary]:
	"""return requested users the principal is allowed to identify."""
	requested: list[TypeID] = []
	seen: set[str] = set()
	for user_id in user_ids:
		key = str(user_id)
		if key in seen:
			continue
		seen.add(key)
		requested.append(user_id)

	if not requested:
		return []

	result = await session.execute(
		select(User).where(
			User.id.in_(requested),
			user_visibility_predicate(
				principal,
				include_inactive=principal.has_permission(ActionPermission.USERS_READ),
			),
		)
	)
	users = list(result.scalars().all())
	users_by_id = {str(user.id): user for user in users}
	redacted = await redact_users(users, session, principal)
	summaries: list[UserSummary] = []
	for user_id in requested:
		user = users_by_id.get(str(user_id))
		if user is not None:
			summaries.append(_build_user_summary(redacted[user.id]))
	return summaries


async def get_user_counts(
	user_id: TypeID,
	session: AsyncSession,
	principal: Principal,
) -> dict[str, int]:
	# ensure actor has permission
	await get_user(user_id, session, principal=principal)

	# only resources that have a real user-ownership column
	queries = {
		"threads": select(func.count())
		.select_from(Thread)
		.where(Thread.owner_id == user_id),
		"memories": select(func.count())
		.select_from(Memory)
		.where(Memory.user_id == user_id),
		"notes": select(func.count()).select_from(Note).where(Note.user_id == user_id),
		"files": select(func.count()).select_from(File).where(File.owner_id == user_id),
		"groups": select(func.count())
		.select_from(Group)
		.where(Group.owner_id == user_id),
		"projects": select(func.count())
		.select_from(Project)
		.where(Project.owner_id == user_id),
		"calendars": select(func.count())
		.select_from(Calendar)
		.where(Calendar.owner_id == user_id),
		"reminders": (
			select(func.count())
			.select_from(Reminder)
			.where(Reminder.owner_id == user_id)
		),
		"reminder_lists": (
			select(func.count())
			.select_from(ReminderList)
			.where(ReminderList.owner_id == user_id)
		),
		"tasks": select(func.count()).select_from(Task).where(Task.user_id == user_id),
		"notifications": select(func.count())
		.select_from(Notification)
		.where(Notification.user_id == user_id),
		"clients": select(func.count())
		.select_from(UserClient)
		.where(UserClient.user_id == user_id),
		"friends": select(func.count())
		.select_from(Friendship)
		.where(
			Friendship.status == FriendshipStatus.ACCEPTED,
			or_(
				Friendship.requester_id == user_id,
				Friendship.addressee_id == user_id,
			),
		),
		"friend_requests_incoming": select(func.count())
		.select_from(Friendship)
		.where(
			Friendship.status == FriendshipStatus.PENDING,
			Friendship.addressee_id == user_id,
		),
		"friend_requests_outgoing": select(func.count())
		.select_from(Friendship)
		.where(
			Friendship.status == FriendshipStatus.PENDING,
			Friendship.requester_id == user_id,
		),
		"blocks": select(func.count())
		.select_from(Block)
		.where(Block.blocker_id == user_id),
	}
	counts: dict[str, int] = {}
	for key, stmt in queries.items():
		result = await session.execute(stmt)
		counts[key] = result.scalar() or 0
	return counts


async def create_user(
	user_in: UserCreate,
	session: AsyncSession,
	principal: Principal | None = None,
) -> User:
	user_count = await session.scalar(select(func.count()).select_from(User))
	is_bootstrap = (user_count or 0) == 0
	actor = principal.subject if principal else None

	if is_bootstrap:
		if user_in.is_superuser is not True:
			console_origin_value = settings.branding.public_console_origin
			console_origin = (
				str(console_origin_value) if console_origin_value is not None else None
			)
			detail: dict[str, str | None] = {
				"code": "bootstrap_required",
				"message": "this instance needs an admin created in the console first",
				"console_origin": console_origin,
			}
			raise HTTPException(
				status_code=status.HTTP_400_BAD_REQUEST,
				detail=detail,
			)

		# first user requested to be superuser
		is_active = True
		is_superuser = True
	elif actor is not None:
		if not actor.is_active:
			raise HTTPException(
				status_code=status.HTTP_403_FORBIDDEN,
				detail="inactive user",
			)

		if principal is None:
			raise HTTPException(
				status_code=status.HTTP_403_FORBIDDEN,
				detail="forbidden",
			)

		if not principal.has_permission(ActionPermission.USERS_MANAGE):
			raise HTTPException(
				status_code=status.HTTP_403_FORBIDDEN,
				detail="forbidden",
			)

		# allow signups toggle does not block admin/authorized creation
		if principal.user.is_superuser:
			is_active = user_in.is_active if user_in.is_active is not None else True
			is_superuser = (
				user_in.is_superuser if user_in.is_superuser is not None else False
			)
		else:
			is_active = True
			is_superuser = False
	else:
		if not settings.security.allow_signups:
			raise HTTPException(
				status_code=status.HTTP_403_FORBIDDEN,
				detail="signups are disabled",
			)
		# unauthenticated: regular user only
		is_active = True
		is_superuser = False

	result = await session.execute(select(User).where(User.email == user_in.email))
	if result.scalar_one_or_none():
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="email already registered",
		)
	result = await session.execute(
		select(User).where(User.username == user_in.username)
	)
	if result.scalar_one_or_none():
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="username already taken",
		)

	user = User(
		email=user_in.email,
		hashed_password=hash_password(user_in.password),
		username=user_in.username,
		display_name=user_in.display_name,
		is_active=is_active,
		is_superuser=is_superuser,
	)
	session.add(user)
	role_ids: list[str] = []
	try:
		await session.flush()

		if actor is None:
			role_ids = settings.security.auto_signup_role_ids or []
			if role_ids:
				await session.execute(
					insert(user_role_association),
					[
						{"user_id": str(user.id), "role_id": str(rid)}
						for rid in role_ids
					],
				)
			for role_id in role_ids:
				await enqueue_accessible_users_invalidation_for_subject(
					"role", TypeID(role_id), session
				)

		await session.commit()
		await run_post_commit_actions_safely(session)
	except IntegrityError as exc:
		# rollback-and-raise: no explicit discard needed, the session closes on
		# the way out and drops its uncommitted actions there.
		await session.rollback()
		_raise_user_integrity_error(exc)
	await session.refresh(user)
	# auto-signup roles can grant access via AccessRule.subject_role_id, so
	# bust those caches rather than waiting out the TTL.
	if role_ids:
		await invalidate_accessible_users_for_role_defaults(
			[TypeID(rid) for rid in role_ids], session
		)
	if user.is_active:
		await invalidate_accessible_users_for_resource_types(list(ResourceType))
	return user


async def update_user(
	user_id: TypeID,
	user_in: UserUpdate,
	session: AsyncSession,
	principal: Principal,
	origin_session_id: str | None = None,
) -> User:
	changed = user_in.model_fields_set
	if not principal.user.is_superuser and user_id != principal.user.id:
		raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")

	if not principal.user.is_superuser:
		admin_fields = {
			"is_active",
			"is_superuser",
			"integration_tokens",
			"usage_quotas",
			"role_ids",
		}
		if admin_fields & changed:
			raise HTTPException(
				status_code=status.HTTP_400_BAD_REQUEST,
				detail="unsupported fields",
			)
		self_fields = {
			"preferences",
			"display_name",
			"avatar_url",
			"username",
			"bio",
			"find_by_email",
			"privacy",
		}
		if not self_fields & changed:
			raise HTTPException(
				status_code=status.HTTP_400_BAD_REQUEST,
				detail="no updatable fields provided",
			)

	user = await get_user(user_id, session, principal=principal)

	# capture pre-mutation role membership so we can compute the symmetric
	# difference and invalidate only the affected role subjects.
	old_role_ids: set[TypeID] = set()
	new_role_ids: set[TypeID] = set()
	if principal.user.is_superuser and "role_ids" in changed:
		old_role_ids = {
			TypeID(row[0])
			for row in (
				await session.execute(
					select(user_role_association.c.role_id).where(
						user_role_association.c.user_id == str(user.id)
					)
				)
			).all()
		}
	access_change = None
	if (
		principal.user.is_superuser
		and {
			"role_ids",
			"is_active",
			"is_superuser",
		}
		& changed
	):
		access_change = await capture_access_change(
			await resource_refs_for_subject("user", user.id, session),
			session,
		)

	update_data = user_in.model_dump(
		exclude_unset=True,
		exclude={"preferences", "privacy", "role_ids"},
	)
	for key, value in update_data.items():
		setattr(user, key, value)

	if "preferences" in changed:
		preferences = user_in.model_dump(
			exclude_unset=True,
			mode="json",
			by_alias=True,
			include={"preferences"},
		)["preferences"]
		user.preferences = preferences
	if "privacy" in changed:
		privacy = user_in.model_dump(
			exclude_unset=True,
			mode="json",
			include={"privacy"},
		)["privacy"]
		user.privacy = privacy

	if principal.user.is_superuser:
		if "role_ids" in changed:
			role_ids_data = user_in.model_dump(
				exclude_unset=True,
				include={"role_ids"},
			)["role_ids"]
			new_role_ids = {TypeID(str(role_id)) for role_id in role_ids_data}
			# clear existing roles and insert new ones via the secondary table.
			# FK constraints on user_roles will reject non-existent role IDs.
			await session.execute(
				delete(user_role_association).where(
					user_role_association.c.user_id == str(user.id)
				)
			)
			if new_role_ids:
				await session.execute(
					insert(user_role_association),
					[
						{"user_id": str(user.id), "role_id": str(rid)}
						for rid in new_role_ids
					],
				)
	role_ids_changed = old_role_ids ^ new_role_ids if "role_ids" in changed else set()
	for changed_role_id in role_ids_changed:
		await enqueue_accessible_users_invalidation_for_subject(
			subject_kind="role",
			subject_id=changed_role_id,
			session=session,
		)

	session.add(user)
	try:
		await session.flush()
		prepared_access_events = (
			await build_access_change_events(
				access_change,
				session,
				actor_user_id=principal.user.id,
			)
			if access_change is not None
			else []
		)
		await session.commit()
	except IntegrityError as exc:
		# rollback-and-raise: close-time discard drops the uncommitted actions.
		await session.rollback()
		msg = str(exc.orig).lower()
		if "username" in msg and "unique" in msg:
			raise HTTPException(
				status_code=status.HTTP_400_BAD_REQUEST,
				detail="username already taken",
			) from None
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail=f"invalid reference: {exc.orig}",
		) from None
	await session.refresh(user)
	for prepared in prepared_access_events:
		await fanout_event(
			prepared.event,
			recipient_ids=prepared.recipient_ids,
		)

	# any user-row change may be reflected in the cached principal snapshot.
	await invalidate_principals([user.id])

	# precise cache invalidation: only the subjects whose effective access
	# could have changed. avoids a coarse 'invalidate everything' tag.
	if principal.user.is_superuser:
		if "is_superuser" in changed:
			# superuser recipients changed.
			await invalidate_accessible_users_for_resource_types(list(ResourceType))
		if "is_active" in changed:
			await invalidate_accessible_users_for_resource_types(list(ResourceType))
		if "role_ids" in changed:
			if role_ids_changed:
				await invalidate_accessible_users_for_role_defaults(
					list(role_ids_changed), session
				)

	# emit user.preferences_updated event when preferences changed
	if "preferences" in changed:
		event = Event(
			scope=EventScope.USER,
			scope_id=user.id,
			type=EventType.USER_PREFERENCES_UPDATED,
			data={
				"user_id": user.id,
				"preferences": user.preferences,
			},
			user_id=user.id,
		)
		await persist_and_fanout_event(
			session, event=event, origin_session_id=origin_session_id
		)

	return user


def _verify_credential_change(
	user: User,
	principal: Principal,
	current_password: str | None,
) -> None:
	"""require current-password proof for self-changes; admins skip it for others."""
	if principal.user.is_superuser and user.id != principal.user.id:
		return
	if not current_password:
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="current password is required",
		)
	if not verify_password(current_password, user.hashed_password):
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="current password is incorrect",
		)


async def change_password(
	user_id: TypeID,
	body: UserPasswordChange,
	session: AsyncSession,
	principal: Principal,
) -> None:
	"""set a new password for the user and revoke all their sessions."""
	user = await get_user(user_id, session, principal=principal)
	_verify_credential_change(user, principal, body.current_password)
	user.hashed_password = hash_password(body.new_password)
	session.add(user)
	revoked_ids = await revoke_all_sessions(session, user.id)
	event = Event(
		scope=EventScope.USER,
		scope_id=user.id,
		type=EventType.USER_PASSWORD_CHANGED,
		data={
			"user_id": user.id,
			"actor_id": principal.user.id,
			"self_service": str(user.id) == principal.user.id,
		},
		user_id=user.id,
	)
	await persist_and_fanout_event(session, event=event)
	await mark_sessions_revoked(revoked_ids)
	await request_socket_kill(user.id)


async def change_email(
	user_id: TypeID,
	body: UserEmailChange,
	session: AsyncSession,
	principal: Principal,
) -> User:
	"""set a new email address for the user."""
	# temporary gate until an email verification flow exists: without it,
	# self-set addresses are unverified (typo lockouts, squatting).
	if not principal.user.is_superuser:
		raise HTTPException(
			status_code=status.HTTP_403_FORBIDDEN,
			detail="email change is temporarily limited to administrators",
		)
	user = await get_user(user_id, session, principal=principal)
	_verify_credential_change(user, principal, body.current_password)
	old_email = user.email
	user.email = body.new_email
	session.add(user)
	try:
		await session.flush()
	except IntegrityError as exc:
		# rollback-and-raise: close-time discard drops the uncommitted actions.
		await session.rollback()
		_raise_user_integrity_error(exc)
	event = Event(
		scope=EventScope.USER,
		scope_id=user.id,
		type=EventType.USER_EMAIL_CHANGED,
		data={
			"user_id": user.id,
			"actor_id": principal.user.id,
			"self_service": str(user.id) == principal.user.id,
			"old_email": old_email,
			"new_email": user.email,
		},
		user_id=user.id,
	)
	await persist_and_fanout_event(session, event=event)
	await invalidate_principals([user.id])
	await session.refresh(user)
	return user


async def _operator_resource_types(
	user: User,
	session: AsyncSession,
) -> list[ResourceType]:
	"""resource types this user reaches through the operator arm, not by rule.

	an operator is folded into every resource of the type's accessible-user
	set without any access rule naming them, so a subject-scoped invalidation
	cannot find those entries. a superuser operates everything.
	"""
	if user.is_superuser:
		return list(ResourceType)
	principal = await build_principal(user, session)
	return [
		resource_type
		for resource_type in ResourceType
		if principal.is_resource_operator(resource_type)
	]


async def delete_user(
	user_id: TypeID,
	session: AsyncSession,
	principal: Principal,
) -> None:
	"""delete a user and all their resources."""
	if not principal.has_permission(ActionPermission.USERS_MANAGE):
		raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")

	if str(user_id) == principal.user.id:
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="cannot delete your own account",
		)

	result = await session.execute(
		# roles are eager-loaded because `_operator_resource_types` below reads
		# them to decide whether this user reaches resources as an operator.
		select(User).options(selectinload(User.roles)).where(User.id == user_id)
	)
	user = result.scalar_one_or_none()
	if user is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="user not found",
		)

	if user.is_active and user.is_superuser:
		active_superuser_count = await session.scalar(
			select(func.count())
			.select_from(User)
			.where(
				User.id != user.id,
				User.is_active.is_(True),
				User.is_superuser.is_(True),
			)
		)
		if (active_superuser_count or 0) == 0:
			raise HTTPException(
				status_code=status.HTTP_400_BAD_REQUEST,
				detail="cannot delete the last active superuser",
			)

	access_change = await capture_access_change(
		await resource_refs_for_subject("user", user.id, session),
		session,
	)
	await enqueue_accessible_users_invalidation_for_subject("user", user.id, session)
	if operator_resource_types := await _operator_resource_types(user, session):
		# no access rule names an operator, so the rule-derived invalidation
		# above misses every resource of the types they operate.
		await invalidate_accessible_users_for_resource_types(operator_resource_types)
	revoked_ids = await revoke_all_sessions(session, user.id)
	await session.delete(user)
	await session.flush()
	prepared_access_events = await build_access_change_events(
		access_change,
		session,
		actor_user_id=principal.user.id,
	)
	await session.commit()
	for prepared in prepared_access_events:
		await fanout_event(
			prepared.event,
			recipient_ids=prepared.recipient_ids,
		)
	await mark_sessions_revoked(revoked_ids)
	await invalidate_principals([user_id])
	await request_socket_kill(user_id)
