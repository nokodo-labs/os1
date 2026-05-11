"""service helpers for user operations."""

from __future__ import annotations

import asyncio

from fastapi import HTTPException, status
from sqlalchemy import delete, func, insert, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from api.models.event import Event, EventScope
from api.models.event_types import EventType
from api.models.file import File
from api.models.group import Group
from api.models.many_to_many import user_role_association
from api.models.memory import Memory
from api.models.note import Note
from api.models.reminder import Reminder, ReminderList
from api.models.thread import Thread
from api.models.user import USER_TYPEID_PREFIX, User
from api.permissions import (
	DEFAULT_ACCESS_RESOURCE_TYPES,
	ActionPermission,
	ResourceType,
)
from api.schemas.user import UserCreate, UserSummary, UserUpdate
from api.settings import settings
from api.v1.service import events as event_service
from api.v1.service.auth import Principal
from api.v1.service.authorization import (
	invalidate_accessible_users_for_resource_types,
	invalidate_accessible_users_for_role_defaults,
	invalidate_accessible_users_for_subject,
)
from api.v1.service.listing import SortDir, apply_sort, exact_typeid_filter
from api.v1.service.social import privacy as privacy_service
from api.v1.service.social.visibility import user_visibility_predicate
from nokodo_ai.utils.search import contains_pattern
from nokodo_ai.utils.security import hash_password
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


def _build_user_summary(
	redacted: privacy_service.RedactedUser,
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
	sort_by: str = "updated_at",
	sort_dir: SortDir = "desc",
	q: str | None = None,
) -> list[User]:
	if not principal.is_admin:
		raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
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
	if not principal.is_admin:
		raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
	stmt = _apply_admin_user_filters(select(func.count()).select_from(User), q)
	return await session.scalar(stmt) or 0


async def get_user(
	user_id: TypeID,
	session: AsyncSession,
	principal: Principal,
) -> User:
	if not principal.is_admin and user_id != principal.user.id:
		raise HTTPException(
			status_code=status.HTTP_403_FORBIDDEN,
			detail="forbidden",
		)

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
				include_inactive=principal.is_admin,
			),
		)
	)
	users = list(result.scalars().all())
	users_by_id = {str(user.id): user for user in users}
	redacted = await privacy_service.redact_users(users, session, principal)
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
	actor = principal.user if principal else None

	# determine what privilege level the new user can have:
	# - bootstrap (first user): must request superuser explicitly (console setup)
	# - unauthenticated: regular user only (is_active=True, is_superuser=False)
	# - authenticated superuser: can set any privileges
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

		if not principal.is_admin and not principal.has_permission(
			str(ActionPermission.USERS_MANAGE)
		):
			raise HTTPException(
				status_code=status.HTTP_403_FORBIDDEN,
				detail="forbidden",
			)

		# allow signups toggle does not block admin/authorized creation
		if principal.is_admin:
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

	user = User(
		email=user_in.email,
		hashed_password=hash_password(user_in.password),
		username=user_in.username,
		display_name=user_in.display_name,
		is_active=is_active,
		is_superuser=is_superuser,
	)
	session.add(user)
	await session.flush()

	if actor is None:
		role_ids = settings.security.auto_signup_role_ids or []
		if role_ids:
			await session.execute(
				insert(user_role_association),
				[{"user_id": str(user.id), "role_id": str(rid)} for rid in role_ids],
			)
	else:
		role_ids = []

	try:
		await session.commit()
	except IntegrityError as exc:
		await session.rollback()
		msg = str(exc.orig).lower()
		if "email" in msg and "unique" in msg:
			raise HTTPException(
				status_code=status.HTTP_400_BAD_REQUEST,
				detail="email already registered",
			) from None
		elif "username" in msg and "unique" in msg:
			raise HTTPException(
				status_code=status.HTTP_400_BAD_REQUEST,
				detail="username already taken",
			) from None
		elif "foreign key" in msg and "user_roles" in msg:
			raise HTTPException(
				status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
				detail="invalid role reference in auto_signup_role_ids",
			) from None
		else:
			raise exc
	await session.refresh(user)
	# auto-signup roles may grant access to existing resources via
	# AccessRule.subject_role_id; bust those caches so the new user
	# becomes visible to recipients without waiting for the TTL.
	# fan out concurrently - each subject invalidation is independent.
	if role_ids:
		await asyncio.gather(
			*(
				invalidate_accessible_users_for_subject("role", TypeID(rid), session)
				for rid in role_ids
			)
		)
		await invalidate_accessible_users_for_role_defaults(
			[TypeID(rid) for rid in role_ids], session
		)
	return user


async def update_user(
	user_id: TypeID,
	user_in: UserUpdate,
	session: AsyncSession,
	principal: Principal,
	origin_session_id: str | None = None,
) -> User:
	changed = user_in.model_fields_set
	if not principal.is_admin and user_id != principal.user.id:
		raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")

	if not principal.is_admin:
		admin_fields = {
			"email",
			"password",
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
	if principal.is_admin and "role_ids" in changed:
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

	update_data = user_in.model_dump(
		exclude_unset=True,
		exclude={"password", "preferences", "privacy", "role_ids"},
	)
	for key, value in update_data.items():
		setattr(user, key, value)

	if "preferences" in changed:
		preferences = user_in.model_dump(
			exclude_unset=True,
			exclude_none=True,
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

	if principal.is_admin:
		if "password" in changed:
			password = user_in.password
			if not isinstance(password, str):
				raise ValueError("invalid password")
			user.hashed_password = hash_password(password)
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

	session.add(user)
	try:
		await session.commit()
	except IntegrityError as exc:
		await session.rollback()
		msg = str(exc.orig).lower()
		if "username" in msg and "unique" in msg:
			raise HTTPException(
				status_code=status.HTTP_400_BAD_REQUEST,
				detail="username already taken",
			) from None
		if "email" in msg and "unique" in msg:
			raise HTTPException(
				status_code=status.HTTP_400_BAD_REQUEST,
				detail="email already registered",
			) from None
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail=f"invalid reference: {exc.orig}",
		) from None
	await session.refresh(user)

	# precise cache invalidation: only the subjects whose effective access
	# could have changed. avoids a coarse 'invalidate everything' tag.
	if principal.is_admin:
		if "is_superuser" in changed:
			# superuser recipients changed.
			await invalidate_accessible_users_for_resource_types(
				list(ResourceType), session
			)
		if "is_active" in changed:
			# direct user-rule grants for this user can flip in/out of the
			# accessible_users list. invalidate per-subject:user.
			await invalidate_accessible_users_for_subject(
				subject_kind="user", subject_id=user.id, session=session
			)
			# default recipients changed.
			default_resource_types = [
				resource_type
				for resource_type in DEFAULT_ACCESS_RESOURCE_TYPES
				if settings.default_permissions.resource_access.get(resource_type)
				is not None
			]
			if default_resource_types:
				await invalidate_accessible_users_for_resource_types(
					default_resource_types, session
				)
		if "role_ids" in changed:
			role_ids_changed = old_role_ids ^ new_role_ids
			if role_ids_changed:
				await asyncio.gather(
					*(
						invalidate_accessible_users_for_subject(
							subject_kind="role",
							subject_id=changed_role_id,
							session=session,
						)
						for changed_role_id in role_ids_changed
					)
				)
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
		await event_service.publish_event(
			session, event=event, origin_session_id=origin_session_id
		)

	return user
