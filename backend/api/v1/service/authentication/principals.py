"""authenticated principal construction and resolution."""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Annotated

from fastapi import Depends, HTTPException, status
from joserfc.errors import JoseError
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.database import get_db
from api.models.access_rule import AccessLevel
from api.models.group import GroupMembership
from api.models.user import User
from api.models.user_session import SESSION_TYPEID_PREFIX
from api.permissions import (
	RESOURCE_MANAGE_PERMISSION,
	DefaultResourceAccess,
	PermissionGrant,
	ResourceType,
	level_satisfies,
	permission_grant,
	permission_satisfied_by,
)
from api.settings import settings
from api.v1.schemas.auth import UserSubject
from api.v1.service.authentication.cache import (
	get_principal_snapshot,
	store_principal_snapshot,
)
from api.v1.service.authentication.identity import (
	oauth2_scheme,
	oauth2_scheme_optional,
)
from api.v1.service.authentication.sessions import session_alive
from nokodo_ai.utils.security import decode_jwt_token
from nokodo_ai.utils.typeid import TypeID, assert_typeid, typeid_tuple


logger = logging.getLogger(__name__)


class PrincipalKindError(TypeError):
	"""a principal's subject was narrowed to a kind it is not."""

	def __init__(self, expected: str, actual: str) -> None:
		super().__init__(f"principal subject is {actual!r}, expected {expected!r}")


@dataclass(frozen=True, slots=True)
class Principal:
	"""authenticated principal for authorization decisions."""

	subject: UserSubject
	group_ids: tuple[TypeID, ...]
	permissions: frozenset[PermissionGrant]
	role_ids: tuple[TypeID, ...] = ()
	role_resource_defaults: DefaultResourceAccess = field(
		default_factory=DefaultResourceAccess,
	)
	global_action_permissions: frozenset[PermissionGrant] = field(
		default_factory=frozenset
	)

	@classmethod
	def for_user(
		cls,
		user: User,
		group_ids: tuple[TypeID, ...] = (),
		permissions: frozenset[PermissionGrant] = frozenset(),
		role_ids: tuple[TypeID, ...] = (),
		role_resource_defaults: DefaultResourceAccess | None = None,
		global_action_permissions: frozenset[PermissionGrant] | None = None,
	) -> Principal:
		"""build a principal whose subject is the given user row.

		the process-global defaults are merged in unless the caller passes its
		own, exactly as ``_assemble_principal`` does for every principal the
		running system builds. that matters because this constructor's only
		callers are tests: left un-merged it hands them a principal shape
		production never produces - one carrying none of the global grants a
		real principal always carries - and every assertion made against it is
		then made against a fiction.
		"""
		global_defaults = settings.default_permissions
		return cls(
			subject=UserSubject.from_user(user),
			group_ids=group_ids,
			permissions=permissions,
			role_ids=role_ids,
			role_resource_defaults=(
				role_resource_defaults or DefaultResourceAccess()
			).merge(global_defaults.resource_access),
			global_action_permissions=(
				frozenset(global_defaults.action_permissions)
				if global_action_permissions is None
				else global_action_permissions
			),
		)

	@property
	def user(self) -> UserSubject:
		"""narrow the subject to a user, raising for another kind."""
		if self.subject.kind != "user":
			raise PrincipalKindError(expected="user", actual=self.subject.kind)
		return self.subject

	def has_default_access(
		self,
		resource_type: ResourceType,
		required_level: AccessLevel = AccessLevel.READER,
	) -> bool:
		"""whether merged defaults grant a resource access level."""
		level = self.role_resource_defaults.get(resource_type)
		if level is None:
			return False
		return level_satisfies(level, required_level)

	def is_resource_operator(self, resource_type: ResourceType) -> bool:
		"""whether the principal holds the resource operator permission."""
		return self.has_permission(RESOURCE_MANAGE_PERMISSION[resource_type])

	def has_permission(self, permission: PermissionGrant) -> bool:
		"""whether the principal holds an action permission.

		wildcard semantics come from `permission_satisfied_by`, the same helper
		the SQL operator arms build from, so the two engines cannot drift.
		"""
		if self.user.is_superuser:
			return True
		return permission_satisfied_by(
			permission,
			(*self.permissions, *self.global_action_permissions),
		)


async def _load_principal_parts(
	user: User,
	session: AsyncSession,
) -> tuple[
	tuple[TypeID, ...],
	tuple[TypeID, ...],
	frozenset[PermissionGrant],
	DefaultResourceAccess,
]:
	"""load role and group inputs used to construct a principal."""
	group_ids = tuple(
		TypeID(value)
		for value in await session.scalars(
			select(GroupMembership.group_id).where(GroupMembership.user_id == user.id)
		)
	)
	# grants stay typed all the way from the role row to the principal: a raw
	# str() here would put an unvalidated wildcard behind every access check.
	permissions: list[PermissionGrant] = []
	role_access = DefaultResourceAccess()
	role_ids: list[TypeID] = []
	for role in user.roles:
		role_ids.append(role.id)
		defaults = role.get_default_permissions()
		permissions.extend(defaults.action_permissions)
		role_access = role_access.merge(defaults.resource_access)
	return group_ids, tuple(role_ids), frozenset(permissions), role_access


def _assemble_principal(
	subject: UserSubject,
	group_ids: tuple[TypeID, ...],
	role_ids: tuple[TypeID, ...],
	role_permissions: frozenset[PermissionGrant],
	role_access: DefaultResourceAccess,
) -> Principal:
	"""compose role inputs with current process-global defaults."""
	global_defaults = settings.default_permissions
	return Principal(
		subject=subject,
		group_ids=group_ids,
		role_ids=role_ids,
		permissions=role_permissions,
		role_resource_defaults=role_access.merge(global_defaults.resource_access),
		global_action_permissions=frozenset(global_defaults.action_permissions),
	)


async def build_principal(user: User, session: AsyncSession) -> Principal:
	"""build a principal for an already-loaded user."""
	parts = await _load_principal_parts(user, session)
	return _assemble_principal(UserSubject.from_user(user), *parts)


async def build_principals(
	users: list[User],
	session: AsyncSession,
) -> dict[TypeID, Principal]:
	"""build principals for role-loaded users with one group-membership query."""
	if not users:
		return {}
	group_rows = (
		await session.execute(
			select(GroupMembership.user_id, GroupMembership.group_id).where(
				GroupMembership.user_id.in_([user.id for user in users])
			)
		)
	).all()
	group_ids_by_user: dict[TypeID, list[TypeID]] = {}
	for user_id, group_id in group_rows:
		group_ids_by_user.setdefault(TypeID(user_id), []).append(TypeID(group_id))
	result: dict[TypeID, Principal] = {}
	for user in users:
		permissions: list[PermissionGrant] = []
		role_access = DefaultResourceAccess()
		role_ids: list[TypeID] = []
		for role in user.roles:
			role_ids.append(role.id)
			defaults = role.get_default_permissions()
			permissions.extend(defaults.action_permissions)
			role_access = role_access.merge(defaults.resource_access)
		result[user.id] = _assemble_principal(
			UserSubject.from_user(user),
			tuple(group_ids_by_user.get(user.id, [])),
			tuple(role_ids),
			frozenset(permissions),
			role_access,
		)
	return result


def _principal_from_snapshot(snapshot: dict[str, object]) -> Principal | None:
	"""rebuild a principal from cached role-derived inputs."""
	try:
		subject = UserSubject.model_validate(snapshot["subject"])
		group_ids = typeid_tuple(snapshot["group_ids"])
		role_ids = typeid_tuple(snapshot["role_ids"])
		raw_permissions = snapshot["role_permissions"]
		if not isinstance(raw_permissions, list):
			return None
		# the snapshot is cache data: parse it back into grants rather than
		# trusting it, so a stale or tampered entry cannot inject a wildcard.
		permissions = frozenset(
			permission_grant(str(value)) for value in raw_permissions
		)
		role_access = DefaultResourceAccess.model_validate(
			snapshot["role_resource_access"]
		)
	except KeyError, TypeError, ValueError, ValidationError:
		return None
	return _assemble_principal(
		subject,
		group_ids,
		role_ids,
		permissions,
		role_access,
	)


async def _build_and_cache_principal(
	user_id: object,
	session: AsyncSession,
) -> Principal | None:
	"""build a principal from Postgres and write its role-derived snapshot."""
	user = await session.scalar(
		select(User).options(selectinload(User.roles)).where(User.id == user_id)
	)
	if user is None:
		return None
	group_ids, role_ids, permissions, role_access = await _load_principal_parts(
		user,
		session,
	)
	subject = UserSubject.from_user(user)
	principal = _assemble_principal(
		subject,
		group_ids,
		role_ids,
		permissions,
		role_access,
	)
	await store_principal_snapshot(
		str(user.id),
		{
			"subject": subject.model_dump(mode="json"),
			"group_ids": [str(value) for value in group_ids],
			"role_ids": [str(value) for value in role_ids],
			"role_permissions": sorted(permissions),
			"role_resource_access": role_access.model_dump(mode="json"),
		},
		role_ids=[str(value) for value in role_ids],
	)
	return principal


async def resolve_principal(token: str, session: AsyncSession) -> Principal:
	"""resolve an access token through session validity and principal cache."""
	credentials_exception = HTTPException(
		status_code=status.HTTP_401_UNAUTHORIZED,
		detail="could not validate credentials",
		headers={"WWW-Authenticate": "Bearer"},
	)
	try:
		payload = decode_jwt_token(
			token,
			secret_key=settings.security.secret_key,
			algorithms=[settings.security.jwt_algorithm],
		)
	except JoseError:
		raise credentials_exception
	user_id = payload.get("sub")
	if user_id is None:
		raise credentials_exception
	sid_raw = payload.get("sid")
	if isinstance(sid_raw, str) and sid_raw:
		try:
			session_id = TypeID(assert_typeid(sid_raw, prefix=SESSION_TYPEID_PREFIX))
		except ValueError:
			raise credentials_exception
		alive, snapshot = await asyncio.gather(
			session_alive(session, session_id),
			get_principal_snapshot(str(user_id)),
		)
		if not alive:
			raise credentials_exception
	else:
		logger.debug("accepted token without session claim for user %s", user_id)
		snapshot = await get_principal_snapshot(str(user_id))
	principal = _principal_from_snapshot(snapshot) if snapshot else None
	if principal is None:
		principal = await _build_and_cache_principal(user_id, session)
	if principal is None:
		raise credentials_exception
	if not principal.subject.is_active:
		raise HTTPException(
			status_code=status.HTTP_403_FORBIDDEN,
			detail="inactive user",
		)
	return principal


async def get_current_principal(
	token: Annotated[str, Depends(oauth2_scheme)],
	session: Annotated[AsyncSession, Depends(get_db)],
) -> Principal:
	"""request dependency for a cache-backed principal."""
	return await resolve_principal(token, session)


async def load_principal_for_user(
	user_id: TypeID,
	session: AsyncSession,
) -> Principal:
	"""load a principal outside FastAPI dependency injection."""
	user = await session.scalar(
		select(User).options(selectinload(User.roles)).where(User.id == user_id)
	)
	if user is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="user not found",
		)
	if not user.is_active:
		raise HTTPException(
			status_code=status.HTTP_403_FORBIDDEN,
			detail="inactive user",
		)
	return await build_principal(user, session)


async def get_optional_principal(
	token: Annotated[str | None, Depends(oauth2_scheme_optional)],
	session: Annotated[AsyncSession, Depends(get_db)],
) -> Principal | None:
	"""request dependency for a principal when a token is present."""
	if token is None:
		return None
	return await resolve_principal(token, session)
