"""comprehensive tests for the permissions system.

covers:
- DefaultPermissions model serialization / validation
- ActionPermission enum usage
- ResourceType enum coverage
- Role model typed default_permissions
- Principal permission resolution (role + global)
- authorization predicates with role defaults and global defaults
- get_effective_access_level with defaults fallback
- require_permission with global action permissions
- roles CRUD via API with typed default_permissions
- edge cases: no roles, no defaults, superuser bypass, public rules, group rules
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.access_rule import AccessLevel, AccessRule
from api.models.group import Group
from api.models.many_to_many import user_role_association
from api.models.role import Role
from api.models.thread import Thread
from api.models.user import User
from api.permissions import (
	ActionPermission,
	DefaultPermissions,
	DefaultResourceAccess,
	ResourceType,
)
from api.schemas.role import RoleCreate, RoleUpdate
from api.v1.service import authorization
from api.v1.service import roles as roles_service
from api.v1.service.auth import Principal, get_current_principal
from nokodo_ai.utils.typeid import new_typeid


# DefaultPermissions model tests


class TestDefaultPermissions:
	"""tests for the DefaultPermissions pydantic model."""

	def test_empty_defaults(self) -> None:
		dp = DefaultPermissions()
		assert dp.resource_access == DefaultResourceAccess()
		assert dp.action_permissions == set()

	def test_with_resource_access(self) -> None:
		dp = DefaultPermissions(
			resource_access=DefaultResourceAccess(
				thread=AccessLevel.READER,
				project=AccessLevel.EDITOR,
			)
		)
		assert dp.resource_access.thread == AccessLevel.READER
		assert dp.resource_access.project == AccessLevel.EDITOR

	def test_with_action_permissions(self) -> None:
		dp = DefaultPermissions(
			action_permissions={
				ActionPermission.AGENTS_CREATE,
				ActionPermission.PROMPTS_READ,
			}
		)
		assert ActionPermission.AGENTS_CREATE in dp.action_permissions
		assert ActionPermission.PROMPTS_READ in dp.action_permissions
		assert len(dp.action_permissions) == 2

	def test_full_model(self) -> None:
		dp = DefaultPermissions(
			resource_access=DefaultResourceAccess(
				thread=AccessLevel.ADMIN,
			),
			action_permissions={ActionPermission.SETTINGS_MANAGE},
		)
		assert dp.resource_access.thread == AccessLevel.ADMIN
		assert ActionPermission.SETTINGS_MANAGE in dp.action_permissions

	def test_json_roundtrip(self) -> None:
		dp = DefaultPermissions(
			resource_access=DefaultResourceAccess(
				thread=AccessLevel.EDITOR,
				file=AccessLevel.READER,
			),
			action_permissions={
				ActionPermission.USERS_READ,
				ActionPermission.EVENTS_MANAGE,
			},
		)
		json_data = dp.model_dump(mode="json")
		restored = DefaultPermissions.model_validate(json_data)
		assert restored.resource_access == dp.resource_access
		assert restored.action_permissions == dp.action_permissions

	def test_json_string_keys(self) -> None:
		"""ensure JSON serialization uses string values."""
		dp = DefaultPermissions(
			resource_access=DefaultResourceAccess(
				thread=AccessLevel.READER,
			),
			action_permissions={ActionPermission.AGENTS_CREATE},
		)
		data = dp.model_dump(mode="json")
		assert isinstance(data["resource_access"]["thread"], str)
		assert isinstance(list(data["action_permissions"])[0], str)

	def test_validates_from_raw_strings(self) -> None:
		"""raw string dicts should validate into enum types."""
		dp = DefaultPermissions.model_validate(
			{
				"resource_access": {"thread": "editor"},
				"action_permissions": ["agents:create"],
			}
		)
		assert dp.resource_access.thread == AccessLevel.EDITOR
		assert ActionPermission.AGENTS_CREATE in dp.action_permissions

	def test_ignores_unknown_resource_type(self) -> None:
		"""unknown fields are silently ignored (supports DB migration)."""
		dp = DefaultPermissions.model_validate(
			{
				"resource_access": {"invalid_type": "reader", "thread": "editor"},
			}
		)
		assert dp.resource_access.thread == AccessLevel.EDITOR

	def test_rejects_invalid_access_level(self) -> None:
		with pytest.raises(Exception):
			DefaultPermissions.model_validate(
				{
					"resource_access": {"thread": "superuser"},
				}
			)

	def test_strips_unknown_action_permission(self) -> None:
		"""unknown action permissions are silently dropped (handles removed perms)."""
		dp = DefaultPermissions.model_validate(
			{
				"action_permissions": [
					"invalid:permission",
					"agents:create",
					"old:removed",
				],
			}
		)
		# only valid permission survives
		assert dp.action_permissions == {ActionPermission.AGENTS_CREATE}


# ActionPermission enum tests


class TestActionPermission:
	"""tests for the ActionPermission StrEnum."""

	def test_all_values_follow_convention(self) -> None:
		"""all permissions should follow {domain}:{action} naming."""
		for perm in ActionPermission:
			assert ":" in perm.value, f"{perm.name} doesn't follow naming convention"

	def test_string_equality(self) -> None:
		assert ActionPermission.ROLES_READ == "roles:read"
		assert ActionPermission.SETTINGS_MANAGE == "settings:manage"

	def test_membership_in_set(self) -> None:
		perms = {ActionPermission.AGENTS_CREATE, ActionPermission.AGENTS_MANAGE}
		assert "agents:create" in perms
		assert "agents:manage" in perms
		assert "agents:delete" not in perms

	def test_all_permissions_present(self) -> None:
		"""verify expected domains are covered."""
		domains = {p.value.split(":")[0] for p in ActionPermission}
		expected = {
			"roles",
			"users",
			"settings",
			"events",
			"threads",
			"projects",
			"notes",
			"groups",
			"reminders",
			"memories",
			"tasks",
			"agents",
			"models",
			"providers",
			"plugins",
			"prompts",
			"files",
			"console",
			"frontend",
		}
		assert expected == domains


# ResourceType enum tests


class TestResourceType:
	"""tests for the ResourceType StrEnum."""

	def test_all_resource_types_have_config(self) -> None:
		"""every ResourceType must be in RESOURCE_CONFIG."""
		for rt in ResourceType:
			assert rt in authorization.RESOURCE_CONFIG, (
				f"{rt} missing from RESOURCE_CONFIG"
			)

	def test_string_values(self) -> None:
		assert ResourceType.THREAD == "thread"
		assert ResourceType.PROJECT == "project"
		assert ResourceType.FILE == "file"


# Role model tests


class TestRoleModel:
	"""tests for the Role ORM model with typed default_permissions."""

	@pytest.mark.asyncio
	async def test_create_role_with_empty_defaults(
		self, db_session: AsyncSession
	) -> None:
		role = Role(name="empty-perms")
		db_session.add(role)
		await db_session.commit()
		await db_session.refresh(role)

		dp = role.get_default_permissions()
		assert dp.resource_access == DefaultResourceAccess()
		assert dp.action_permissions == set()

	@pytest.mark.asyncio
	async def test_create_role_with_typed_defaults(
		self, db_session: AsyncSession
	) -> None:
		dp = DefaultPermissions(
			resource_access=DefaultResourceAccess(
				thread=AccessLevel.EDITOR,
			),
			action_permissions={ActionPermission.AGENTS_CREATE},
		)
		role = Role(name="typed-perms")
		role.set_default_permissions(dp)
		db_session.add(role)
		await db_session.commit()
		await db_session.refresh(role)

		restored = role.get_default_permissions()
		assert restored.resource_access.thread == AccessLevel.EDITOR
		assert ActionPermission.AGENTS_CREATE in restored.action_permissions

	@pytest.mark.asyncio
	async def test_role_description_is_text(self, db_session: AsyncSession) -> None:
		"""description should accept long text (no 500-char limit)."""
		long_desc = "a" * 2000
		role = Role(name="long-desc", description=long_desc)
		db_session.add(role)
		await db_session.commit()
		await db_session.refresh(role)
		assert role.description == long_desc

	@pytest.mark.asyncio
	async def test_role_default_permissions_json_storage(
		self, db_session: AsyncSession
	) -> None:
		"""verify the raw JSON column stores serialized data correctly."""
		dp = DefaultPermissions(
			resource_access=DefaultResourceAccess(),
			action_permissions={
				ActionPermission.MODELS_READ,
				ActionPermission.PROVIDERS_MANAGE,
			},
		)
		role = Role(
			name="json-storage",
			default_permissions=dp.model_dump(
				mode="json",
				exclude_none=True,
			),
		)
		db_session.add(role)
		await db_session.commit()
		await db_session.refresh(role)

		raw = role.default_permissions
		assert isinstance(raw, dict)
		assert "resource_access" in raw
		assert "action_permissions" in raw


# Principal permission resolution tests


class TestPrincipalPermissions:
	"""tests for Principal.has_permission with role + global action perms."""

	def _make_principal(
		self,
		*,
		permissions: frozenset[str] = frozenset(),
		global_action_permissions: frozenset[str] = frozenset(),
		is_superuser: bool = False,
	) -> Principal:
		tid = new_typeid("user")
		user = User(
			email=f"test-{tid}@example.com",
			username=f"test_{tid}",
			hashed_password="x",
			is_superuser=is_superuser,
		)
		return Principal(
			user=user,
			group_ids=(),
			role_ids=(),
			permissions=permissions,
			global_action_permissions=global_action_permissions,
		)

	def test_no_permissions(self) -> None:
		p = self._make_principal()
		assert not p.has_permission("agents:create")

	def test_role_permission_exact(self) -> None:
		p = self._make_principal(permissions=frozenset({"agents:create"}))
		assert p.has_permission("agents:create")
		assert not p.has_permission("agents:manage")

	def test_role_permission_wildcard(self) -> None:
		p = self._make_principal(permissions=frozenset({"agents:*"}))
		assert p.has_permission("agents:create")
		assert p.has_permission("agents:manage")
		assert not p.has_permission("models:read")

	def test_star_permission(self) -> None:
		p = self._make_principal(permissions=frozenset({"*"}))
		assert p.has_permission("anything:here")

	def test_superuser_bypass(self) -> None:
		p = self._make_principal(is_superuser=True)
		assert p.has_permission("any:permission")

	def test_global_action_permissions(self) -> None:
		"""global defaults should grant permissions even without role perms."""
		p = self._make_principal(
			global_action_permissions=frozenset({"agents:create", "prompts:read"})
		)
		assert p.has_permission("agents:create")
		assert p.has_permission("prompts:read")
		assert not p.has_permission("agents:manage")

	def test_role_perms_take_priority_over_global(self) -> None:
		"""role perms and global perms combine (union)."""
		p = self._make_principal(
			permissions=frozenset({"models:manage"}),
			global_action_permissions=frozenset({"agents:create"}),
		)
		assert p.has_permission("models:manage")
		assert p.has_permission("agents:create")
		assert not p.has_permission("settings:manage")


# get_current_principal integration tests


class TestGetCurrentPrincipal:
	"""tests for get_current_principal merging roles and global defaults."""

	@pytest.mark.asyncio
	async def test_no_roles_no_defaults(self, db_session: AsyncSession) -> None:
		user = User(
			email="no-roles@example.com",
			username="no_roles",
			hashed_password="pw",
			is_active=True,
		)
		db_session.add(user)
		await db_session.commit()
		await db_session.refresh(user, attribute_names=["roles"])

		principal = await get_current_principal(user, db_session)
		assert principal.permissions == frozenset()
		assert principal.role_ids == ()

	@pytest.mark.asyncio
	async def test_single_role_action_permissions(
		self, db_session: AsyncSession
	) -> None:
		dp = DefaultPermissions(
			action_permissions={
				ActionPermission.AGENTS_CREATE,
				ActionPermission.MODELS_READ,
			},
		)
		role = Role(
			name="viewer",
			default_permissions=dp.model_dump(mode="json"),
		)
		user = User(
			email="viewer@example.com",
			username="viewer_perm",
			hashed_password="pw",
			is_active=True,
		)
		db_session.add_all([role, user])
		await db_session.flush()
		await db_session.execute(
			insert(user_role_association).values(user_id=user.id, role_id=role.id)
		)
		await db_session.commit()
		await db_session.refresh(user, attribute_names=["roles"])

		principal = await get_current_principal(user, db_session)
		assert "agents:create" in principal.permissions
		assert "models:read" in principal.permissions
		assert str(role.id) in principal.role_ids

	@pytest.mark.asyncio
	async def test_single_role_resource_defaults(
		self, db_session: AsyncSession
	) -> None:
		dp = DefaultPermissions(
			resource_access=DefaultResourceAccess(
				thread=AccessLevel.EDITOR,
				project=AccessLevel.READER,
			),
		)
		role = Role(
			name="editor-role",
			default_permissions=dp.model_dump(mode="json"),
		)
		user = User(
			email="editor@example.com",
			username="editor_perm",
			hashed_password="pw",
			is_active=True,
		)
		db_session.add_all([role, user])
		await db_session.flush()
		await db_session.execute(
			insert(user_role_association).values(user_id=user.id, role_id=role.id)
		)
		await db_session.commit()
		await db_session.refresh(user, attribute_names=["roles"])

		principal = await get_current_principal(user, db_session)
		assert principal.role_resource_defaults.thread == AccessLevel.EDITOR
		assert principal.role_resource_defaults.project == AccessLevel.READER

	@pytest.mark.asyncio
	async def test_multi_role_highest_wins(self, db_session: AsyncSession) -> None:
		"""when user has multiple roles, highest access level per resource wins."""
		dp1 = DefaultPermissions(
			resource_access=DefaultResourceAccess(
				thread=AccessLevel.READER,
			),
			action_permissions={ActionPermission.AGENTS_CREATE},
		)
		dp2 = DefaultPermissions(
			resource_access=DefaultResourceAccess(
				thread=AccessLevel.ADMIN,
				file=AccessLevel.EDITOR,
			),
			action_permissions={ActionPermission.MODELS_MANAGE},
		)
		role1 = Role(
			name="basic", default_permissions=dp1.model_dump(mode="json"), priority=0
		)
		role2 = Role(
			name="power", default_permissions=dp2.model_dump(mode="json"), priority=10
		)
		user = User(
			email="multirole@example.com",
			username="multirole_perm",
			hashed_password="pw",
			is_active=True,
		)
		db_session.add_all([role1, role2, user])
		await db_session.flush()
		await db_session.execute(
			insert(user_role_association).values(user_id=user.id, role_id=role1.id)
		)
		await db_session.execute(
			insert(user_role_association).values(user_id=user.id, role_id=role2.id)
		)
		await db_session.commit()
		await db_session.refresh(user, attribute_names=["roles"])

		principal = await get_current_principal(user, db_session)
		# thread: admin wins over reader
		assert principal.role_resource_defaults.thread == AccessLevel.ADMIN
		# file: only role2 has it
		assert principal.role_resource_defaults.file == AccessLevel.EDITOR
		# action perms: union of both
		assert "agents:create" in principal.permissions
		assert "models:manage" in principal.permissions


# authorization predicate tests with role resource defaults


class TestResourceAccessPredicateWithDefaults:
	"""tests for resource_access_predicate using role_resource_defaults."""

	def _make_principal(
		self,
		user: User,
		*,
		resource_defaults: DefaultResourceAccess | None = None,
		group_ids: tuple[str, ...] = (),
		role_ids: tuple[str, ...] = (),
	) -> Principal:
		return Principal(
			user=user,
			group_ids=group_ids,
			role_ids=role_ids,
			permissions=frozenset(),
			role_resource_defaults=(resource_defaults or DefaultResourceAccess()),
			global_action_permissions=frozenset(),
		)

	@pytest.mark.asyncio
	async def test_default_grants_access(self, db_session: AsyncSession) -> None:
		"""role default_permissions resource_access should grant access."""
		owner = User(
			email="other-owner@example.com",
			username="other_owner",
			hashed_password="pw",
		)
		user = User(
			email="default-user@example.com",
			username="default_user",
			hashed_password="pw",
		)
		db_session.add_all([owner, user])
		await db_session.flush()

		thread = Thread(
			title="test thread",
			owner_id=str(owner.id),
			is_temporary=False,
		)
		db_session.add(thread)
		await db_session.commit()

		# without defaults: no access
		principal_no_defaults = self._make_principal(user)
		pred = authorization.resource_access_predicate(
			principal_no_defaults, ResourceType.THREAD
		)
		result = await db_session.execute(
			select(Thread.id).where(Thread.id == thread.id, pred)
		)
		assert result.scalar_one_or_none() is None

		# with reader default: gets access
		principal_with_defaults = self._make_principal(
			user,
			resource_defaults=DefaultResourceAccess(
				thread=AccessLevel.READER,
			),
		)
		pred = authorization.resource_access_predicate(
			principal_with_defaults, ResourceType.THREAD
		)
		result = await db_session.execute(
			select(Thread.id).where(Thread.id == thread.id, pred)
		)
		assert result.scalar_one_or_none() is not None

	@pytest.mark.asyncio
	async def test_default_insufficient_level(self, db_session: AsyncSession) -> None:
		"""reader default should not satisfy editor requirement."""
		owner = User(
			email="owner-insuf@example.com",
			username="owner_insuf",
			hashed_password="pw",
		)
		user = User(
			email="insuf-user@example.com", username="insuf_user", hashed_password="pw"
		)
		db_session.add_all([owner, user])
		await db_session.flush()

		thread = Thread(
			title="insufficient test",
			owner_id=str(owner.id),
			is_temporary=False,
		)
		db_session.add(thread)
		await db_session.commit()

		principal = self._make_principal(
			user,
			resource_defaults=DefaultResourceAccess(
				thread=AccessLevel.READER,
			),
		)
		pred = authorization.resource_access_predicate(
			principal,
			ResourceType.THREAD,
			required_level=AccessLevel.EDITOR,
		)
		result = await db_session.execute(
			select(Thread.id).where(Thread.id == thread.id, pred)
		)
		assert result.scalar_one_or_none() is None


# get_effective_access_level tests


class TestGetEffectiveAccessLevel:
	"""tests for get_effective_access_level fallback chain."""

	@pytest.mark.asyncio
	async def test_no_access(self, db_session: AsyncSession) -> None:
		owner = User(
			email="no-access-owner@example.com",
			username="no_access_owner",
			hashed_password="pw",
		)
		user = User(
			email="no-access@example.com",
			username="no_access_test",
			hashed_password="pw",
		)
		db_session.add_all([owner, user])
		await db_session.flush()
		thread = Thread(
			title="no-access",
			owner_id=str(owner.id),
			is_temporary=False,
		)
		db_session.add(thread)
		await db_session.commit()

		principal = Principal(
			user=user,
			group_ids=(),
			role_ids=(),
			permissions=frozenset(),
			global_action_permissions=frozenset(),
		)
		level = await authorization.get_effective_access_level(
			db_session, principal, ResourceType.THREAD, str(thread.id)
		)
		assert level is None

	@pytest.mark.asyncio
	async def test_owner_gets_admin(self, db_session: AsyncSession) -> None:
		user = User(
			email="owner-admin@example.com",
			username="owner_admin",
			hashed_password="pw",
		)
		db_session.add(user)
		await db_session.flush()
		thread = Thread(
			title="owner-admin",
			owner_id=str(user.id),
			is_temporary=False,
		)
		db_session.add(thread)
		await db_session.commit()

		principal = Principal(
			user=user,
			group_ids=(),
			role_ids=(),
			permissions=frozenset(),
			global_action_permissions=frozenset(),
		)
		level = await authorization.get_effective_access_level(
			db_session,
			principal,
			ResourceType.THREAD,
			str(thread.id),
			owner_id=str(user.id),
		)
		assert level == AccessLevel.ADMIN

	@pytest.mark.asyncio
	async def test_explicit_rule_wins(self, db_session: AsyncSession) -> None:
		owner = User(
			email="rule-owner@example.com", username="rule_owner", hashed_password="pw"
		)
		user = User(
			email="rule-user@example.com", username="rule_user", hashed_password="pw"
		)
		db_session.add_all([owner, user])
		await db_session.flush()
		thread = Thread(
			title="rule-test",
			owner_id=str(owner.id),
			is_temporary=False,
		)
		db_session.add(thread)
		await db_session.flush()
		rule = AccessRule(
			subject_user_id=str(user.id),
			thread_id=str(thread.id),
			level=AccessLevel.EDITOR,
			order_index=0,
		)
		db_session.add(rule)
		await db_session.commit()

		principal = Principal(
			user=user,
			group_ids=(),
			role_ids=(),
			permissions=frozenset(),
			role_resource_defaults=DefaultResourceAccess(
				thread=AccessLevel.READER,
			),
			global_action_permissions=frozenset(),
		)
		level = await authorization.get_effective_access_level(
			db_session, principal, ResourceType.THREAD, str(thread.id)
		)
		# explicit rule (editor) wins over role default (reader)
		assert level == AccessLevel.EDITOR

	@pytest.mark.asyncio
	async def test_role_default_fallback(self, db_session: AsyncSession) -> None:
		"""when no explicit rule, role defaults should be used."""
		owner = User(
			email="default-owner@example.com",
			username="default_owner",
			hashed_password="pw",
		)
		user = User(
			email="default-fb@example.com",
			username="default_fb_test",
			hashed_password="pw",
		)
		db_session.add_all([owner, user])
		await db_session.flush()
		thread = Thread(
			title="default-fallback",
			owner_id=str(owner.id),
			is_temporary=False,
		)
		db_session.add(thread)
		await db_session.commit()

		principal = Principal(
			user=user,
			group_ids=(),
			role_ids=(),
			permissions=frozenset(),
			role_resource_defaults=DefaultResourceAccess(
				thread=AccessLevel.EDITOR,
			),
			global_action_permissions=frozenset(),
		)
		level = await authorization.get_effective_access_level(
			db_session, principal, ResourceType.THREAD, str(thread.id)
		)
		assert level == AccessLevel.EDITOR

	@pytest.mark.asyncio
	async def test_superuser_always_admin(self, db_session: AsyncSession) -> None:
		owner = User(
			email="su-owner@example.com", username="su_owner_test", hashed_password="pw"
		)
		admin = User(
			email="su@example.com",
			username="su_admin_test",
			hashed_password="pw",
			is_superuser=True,
		)
		db_session.add_all([owner, admin])
		await db_session.flush()
		thread = Thread(
			title="su-test",
			owner_id=str(owner.id),
			is_temporary=False,
		)
		db_session.add(thread)
		await db_session.commit()

		principal = Principal(
			user=admin,
			group_ids=(),
			role_ids=(),
			permissions=frozenset(),
			global_action_permissions=frozenset(),
		)
		level = await authorization.get_effective_access_level(
			db_session, principal, ResourceType.THREAD, str(thread.id)
		)
		assert level == AccessLevel.ADMIN

	@pytest.mark.asyncio
	async def test_public_rule_grants_access(self, db_session: AsyncSession) -> None:
		owner = User(
			email="pub-owner@example.com", username="pub_owner", hashed_password="pw"
		)
		user = User(
			email="pub-user@example.com", username="pub_user_test", hashed_password="pw"
		)
		db_session.add_all([owner, user])
		await db_session.flush()
		thread = Thread(
			title="public-thread",
			owner_id=str(owner.id),
			is_temporary=False,
		)
		db_session.add(thread)
		await db_session.flush()
		# public rule (no subject)
		rule = AccessRule(
			thread_id=str(thread.id),
			level=AccessLevel.READER,
			order_index=0,
		)
		db_session.add(rule)
		await db_session.commit()

		principal = Principal(
			user=user,
			group_ids=(),
			role_ids=(),
			permissions=frozenset(),
			global_action_permissions=frozenset(),
		)
		level = await authorization.get_effective_access_level(
			db_session, principal, ResourceType.THREAD, str(thread.id)
		)
		assert level == AccessLevel.READER

	@pytest.mark.asyncio
	async def test_group_rule_grants_access(self, db_session: AsyncSession) -> None:

		owner = User(
			email="grp-owner@example.com", username="grp_owner", hashed_password="pw"
		)
		user = User(
			email="grp-user@example.com", username="grp_user_test", hashed_password="pw"
		)
		db_session.add_all([owner, user])
		await db_session.flush()

		group = Group(name="test-group", owner_id=str(owner.id))
		db_session.add(group)
		await db_session.flush()

		thread = Thread(
			title="group-thread",
			owner_id=str(owner.id),
			is_temporary=False,
		)
		db_session.add(thread)
		await db_session.flush()
		rule = AccessRule(
			subject_group_id=str(group.id),
			thread_id=str(thread.id),
			level=AccessLevel.EDITOR,
			order_index=0,
		)
		db_session.add(rule)
		await db_session.commit()

		principal = Principal(
			user=user,
			group_ids=(str(group.id),),
			role_ids=(),
			permissions=frozenset(),
			global_action_permissions=frozenset(),
		)
		level = await authorization.get_effective_access_level(
			db_session, principal, ResourceType.THREAD, str(thread.id)
		)
		assert level == AccessLevel.EDITOR


# require_permission tests


class TestRequirePermission:
	"""tests for require_permission with typed ActionPermission."""

	def test_denies_without_permission(self) -> None:
		user = User(
			email="deny@example.com", username="deny_perm", hashed_password="pw"
		)
		principal = Principal(
			user=user,
			group_ids=(),
			role_ids=(),
			permissions=frozenset(),
			global_action_permissions=frozenset(),
		)
		with pytest.raises(HTTPException) as exc:
			authorization.require_permission(principal, ActionPermission.AGENTS_MANAGE)
		assert exc.value.status_code == 403

	def test_allows_with_exact_permission(self) -> None:
		user = User(
			email="allow@example.com", username="allow_perm", hashed_password="pw"
		)
		principal = Principal(
			user=user,
			group_ids=(),
			role_ids=(),
			permissions=frozenset({ActionPermission.AGENTS_MANAGE}),
			global_action_permissions=frozenset(),
		)
		authorization.require_permission(principal, ActionPermission.AGENTS_MANAGE)

	def test_allows_with_global_defaults(self) -> None:
		"""global default action perms should satisfy require_permission."""
		user = User(
			email="global-allow@example.com",
			username="global_allow",
			hashed_password="pw",
		)
		principal = Principal(
			user=user,
			group_ids=(),
			role_ids=(),
			permissions=frozenset(),
			global_action_permissions=frozenset({"agents:create"}),
		)
		authorization.require_permission(principal, ActionPermission.AGENTS_CREATE)

	def test_superuser_bypass(self) -> None:
		user = User(
			email="su-perm@example.com",
			username="su_perm_test",
			hashed_password="pw",
			is_superuser=True,
		)
		principal = Principal(
			user=user,
			group_ids=(),
			role_ids=(),
			permissions=frozenset(),
			global_action_permissions=frozenset(),
		)
		authorization.require_permission(principal, ActionPermission.SETTINGS_MANAGE)


# require_resource_access tests


class TestRequireResourceAccess:
	"""tests for require_resource_access end-to-end."""

	@pytest.mark.asyncio
	async def test_not_found(self, db_session: AsyncSession) -> None:
		user = User(
			email="notfound@example.com", username="notfound_perm", hashed_password="pw"
		)
		db_session.add(user)
		await db_session.commit()

		principal = Principal(
			user=user,
			group_ids=(),
			role_ids=(),
			permissions=frozenset(),
			global_action_permissions=frozenset(),
		)
		with pytest.raises(HTTPException) as exc:
			await authorization.require_resource_access(
				new_typeid("thread"),
				db_session,
				principal,
				ResourceType.THREAD,
			)
		assert exc.value.status_code == 404

	@pytest.mark.asyncio
	async def test_insufficient_access_returns_404(
		self, db_session: AsyncSession
	) -> None:
		"""insufficient access should return 404 to avoid leaking existence."""
		owner = User(
			email="rra-owner@example.com", username="rra_owner", hashed_password="pw"
		)
		user = User(
			email="rra-user@example.com", username="rra_user_test", hashed_password="pw"
		)
		db_session.add_all([owner, user])
		await db_session.flush()
		thread = Thread(
			title="insufficient",
			owner_id=str(owner.id),
			is_temporary=False,
		)
		db_session.add(thread)
		await db_session.flush()
		# give reader but require admin
		rule = AccessRule(
			subject_user_id=str(user.id),
			thread_id=str(thread.id),
			level=AccessLevel.READER,
			order_index=0,
		)
		db_session.add(rule)
		await db_session.commit()

		principal = Principal(
			user=user,
			group_ids=(),
			role_ids=(),
			permissions=frozenset(),
			global_action_permissions=frozenset(),
		)
		with pytest.raises(HTTPException) as exc:
			await authorization.require_resource_access(
				str(thread.id),
				db_session,
				principal,
				ResourceType.THREAD,
				required_level=AccessLevel.ADMIN,
			)
		assert exc.value.status_code == 404

	@pytest.mark.asyncio
	async def test_owner_passes(self, db_session: AsyncSession) -> None:
		user = User(
			email="rra-pass@example.com", username="rra_pass_test", hashed_password="pw"
		)
		db_session.add(user)
		await db_session.flush()
		thread = Thread(
			title="owner-pass",
			owner_id=str(user.id),
			is_temporary=False,
		)
		db_session.add(thread)
		await db_session.commit()

		principal = Principal(
			user=user,
			group_ids=(),
			role_ids=(),
			permissions=frozenset(),
			global_action_permissions=frozenset(),
		)
		await authorization.require_resource_access(
			str(thread.id),
			db_session,
			principal,
			ResourceType.THREAD,
			required_level=AccessLevel.ADMIN,
		)


# roles CRUD API tests


class TestRolesService:
	"""tests for roles service with typed DefaultPermissions."""

	@pytest.mark.asyncio
	async def test_create_role_with_typed_permissions(
		self, db_session: AsyncSession
	) -> None:

		admin_user = User(
			email="role-admin@example.com",
			username="role_admin",
			hashed_password="pw",
			is_superuser=True,
		)
		db_session.add(admin_user)
		await db_session.commit()

		principal = Principal(
			user=admin_user,
			group_ids=(),
			role_ids=(),
			permissions=frozenset(),
			global_action_permissions=frozenset(),
		)

		dp = DefaultPermissions(
			resource_access=DefaultResourceAccess(
				thread=AccessLevel.EDITOR,
			),
			action_permissions={ActionPermission.AGENTS_CREATE},
		)
		role_in = RoleCreate(
			name="service-test",
			description="test role",
			default_permissions=dp,
		)
		role = await roles_service.create_role(role_in, db_session, principal=principal)
		assert role.name == "service-test"

		restored = role.get_default_permissions()
		assert restored.resource_access.thread == AccessLevel.EDITOR
		assert ActionPermission.AGENTS_CREATE in restored.action_permissions

	@pytest.mark.asyncio
	async def test_update_role_default_permissions(
		self, db_session: AsyncSession
	) -> None:

		admin = User(
			email="update-admin@example.com",
			username="update_admin",
			hashed_password="pw",
			is_superuser=True,
		)
		db_session.add(admin)
		await db_session.commit()

		principal = Principal(
			user=admin,
			group_ids=(),
			role_ids=(),
			permissions=frozenset(),
			global_action_permissions=frozenset(),
		)

		# create
		role = await roles_service.create_role(
			RoleCreate(name="update-test"),
			db_session,
			principal=principal,
		)
		assert role.get_default_permissions().action_permissions == set()

		# update
		new_dp = DefaultPermissions(
			action_permissions={ActionPermission.SETTINGS_READ},
			resource_access=DefaultResourceAccess(
				file=AccessLevel.ADMIN,
			),
		)
		updated = await roles_service.update_role(
			str(role.id),
			RoleUpdate(default_permissions=new_dp),
			db_session,
			principal=principal,
		)
		restored = updated.get_default_permissions()
		assert ActionPermission.SETTINGS_READ in restored.action_permissions
		assert restored.resource_access.file == AccessLevel.ADMIN

	@pytest.mark.asyncio
	async def test_list_and_delete_roles(self, db_session: AsyncSession) -> None:

		admin = User(
			email="list-admin@example.com",
			username="list_admin",
			hashed_password="pw",
			is_superuser=True,
		)
		db_session.add(admin)
		await db_session.commit()

		principal = Principal(
			user=admin,
			group_ids=(),
			role_ids=(),
			permissions=frozenset(),
			global_action_permissions=frozenset(),
		)

		role = await roles_service.create_role(
			RoleCreate(name="deletable"),
			db_session,
			principal=principal,
		)
		roles = await roles_service.list_roles(db_session, principal=principal)
		assert any(r.name == "deletable" for r in roles)

		await roles_service.delete_role(str(role.id), db_session, principal=principal)
		roles = await roles_service.list_roles(db_session, principal=principal)
		assert all(r.name != "deletable" for r in roles)

	@pytest.mark.asyncio
	async def test_role_crud_requires_permission(
		self, db_session: AsyncSession
	) -> None:
		"""non-admin without roles:read should be denied."""
		user = User(
			email="no-perm@example.com",
			username="no_perm_test",
			hashed_password="pw",
			is_active=True,
		)
		db_session.add(user)
		await db_session.commit()

		principal = Principal(
			user=user,
			group_ids=(),
			role_ids=(),
			permissions=frozenset(),
			global_action_permissions=frozenset(),
		)
		with pytest.raises(HTTPException) as exc:
			await roles_service.list_roles(db_session, principal=principal)
		assert exc.value.status_code == 403

	@pytest.mark.asyncio
	async def test_get_nonexistent_role(self, db_session: AsyncSession) -> None:
		admin = User(
			email="get-ne-admin@example.com",
			username="get_ne_admin",
			hashed_password="pw",
			is_superuser=True,
		)
		db_session.add(admin)
		await db_session.commit()

		principal = Principal(
			user=admin,
			group_ids=(),
			role_ids=(),
			permissions=frozenset(),
			global_action_permissions=frozenset(),
		)
		with pytest.raises(HTTPException) as exc:
			await roles_service.get_role(
				new_typeid("role"), db_session, principal=principal
			)
		assert exc.value.status_code == 404


# access rules + role-scoped rule tests


class TestAccessRuleWithRole:
	"""tests for access rules that target a role as subject."""

	@pytest.mark.asyncio
	async def test_role_scoped_rule_grants_access(
		self, db_session: AsyncSession
	) -> None:
		owner = User(
			email="role-scope-owner@example.com",
			username="role_scope_owner",
			hashed_password="pw",
		)
		user = User(
			email="role-scope-user@example.com",
			username="role_scope_user",
			hashed_password="pw",
		)
		db_session.add_all([owner, user])
		await db_session.flush()

		role = Role(name="access-test-role")
		db_session.add(role)
		await db_session.flush()

		thread = Thread(
			title="role-scoped",
			owner_id=str(owner.id),
			is_temporary=False,
		)
		db_session.add(thread)
		await db_session.flush()

		# create role-scoped rule
		rule = AccessRule(
			subject_role_id=str(role.id),
			thread_id=str(thread.id),
			level=AccessLevel.EDITOR,
			order_index=0,
		)
		db_session.add(rule)
		await db_session.commit()

		# user WITHOUT the role
		principal_no_role = Principal(
			user=user,
			group_ids=(),
			role_ids=(),
			permissions=frozenset(),
			global_action_permissions=frozenset(),
		)
		level = await authorization.get_effective_access_level(
			db_session, principal_no_role, ResourceType.THREAD, str(thread.id)
		)
		assert level is None

		# user WITH the role
		principal_with_role = Principal(
			user=user,
			group_ids=(),
			role_ids=(str(role.id),),
			permissions=frozenset(),
			global_action_permissions=frozenset(),
		)
		level = await authorization.get_effective_access_level(
			db_session, principal_with_role, ResourceType.THREAD, str(thread.id)
		)
		assert level == AccessLevel.EDITOR


# edge case tests


class TestEdgeCases:
	"""edge cases and boundary conditions."""

	def test_level_satisfies(self) -> None:
		assert authorization._level_satisfies(AccessLevel.ADMIN, AccessLevel.READER)
		assert authorization._level_satisfies(AccessLevel.ADMIN, AccessLevel.EDITOR)
		assert authorization._level_satisfies(AccessLevel.ADMIN, AccessLevel.ADMIN)
		assert authorization._level_satisfies(AccessLevel.EDITOR, AccessLevel.READER)
		assert not authorization._level_satisfies(
			AccessLevel.READER, AccessLevel.EDITOR
		)
		assert not authorization._level_satisfies(AccessLevel.READER, AccessLevel.ADMIN)

	def test_allowed_levels(self) -> None:
		assert authorization._allowed_levels(AccessLevel.READER) == (
			AccessLevel.READER,
			AccessLevel.EDITOR,
			AccessLevel.ADMIN,
		)
		assert authorization._allowed_levels(AccessLevel.EDITOR) == (
			AccessLevel.EDITOR,
			AccessLevel.ADMIN,
		)
		assert authorization._allowed_levels(AccessLevel.ADMIN) == (AccessLevel.ADMIN,)

	@pytest.mark.asyncio
	async def test_user_no_longer_has_role_id_column(
		self, db_session: AsyncSession
	) -> None:
		"""user model should not have the old role_id column."""
		user = User(
			email="no-role-id@example.com", username="no_role_id", hashed_password="pw"
		)
		db_session.add(user)
		await db_session.commit()
		# role_id attribute should not exist on User
		assert not hasattr(User, "role_id") or "role_id" not in User.__table__.columns

	def test_empty_role_permissions_roundtrip(self) -> None:
		"""role with empty default_permissions should roundtrip cleanly."""
		role = Role(name="empty-dp", default_permissions={})
		dp = role.get_default_permissions()
		assert dp == DefaultPermissions()
		role.set_default_permissions(dp)
		assert role.default_permissions == {
			"resource_access": {},
			"action_permissions": [],
		}

	@pytest.mark.asyncio
	async def test_last_rule_wins_ordering(self, db_session: AsyncSession) -> None:
		"""explicit rules: last matching rule by order_index wins."""
		owner = User(
			email="order-owner@example.com",
			username="order_owner",
			hashed_password="pw",
		)
		user = User(
			email="order-user@example.com", username="order_user", hashed_password="pw"
		)
		db_session.add_all([owner, user])
		await db_session.flush()

		thread = Thread(
			title="order-test",
			owner_id=str(owner.id),
			is_temporary=False,
		)
		db_session.add(thread)
		await db_session.flush()

		# first rule: reader
		rule1 = AccessRule(
			subject_user_id=str(user.id),
			thread_id=str(thread.id),
			level=AccessLevel.READER,
			order_index=0,
		)
		# second rule: admin (should win)
		rule2 = AccessRule(
			subject_user_id=str(user.id),
			thread_id=str(thread.id),
			level=AccessLevel.ADMIN,
			order_index=1,
		)
		db_session.add_all([rule1, rule2])
		await db_session.commit()

		principal = Principal(
			user=user,
			group_ids=(),
			role_ids=(),
			permissions=frozenset(),
			global_action_permissions=frozenset(),
		)
		level = await authorization.get_effective_access_level(
			db_session, principal, ResourceType.THREAD, str(thread.id)
		)
		assert level == AccessLevel.ADMIN

	@pytest.mark.asyncio
	async def test_multiple_resource_types_independent(
		self, db_session: AsyncSession
	) -> None:
		"""resource defaults for different types should be independent."""
		user = User(
			email="multi-rt@example.com", username="multi_rt_test", hashed_password="pw"
		)
		db_session.add(user)
		await db_session.commit()

		principal = Principal(
			user=user,
			group_ids=(),
			role_ids=(),
			permissions=frozenset(),
			role_resource_defaults=DefaultResourceAccess(
				thread=AccessLevel.EDITOR,
				project=AccessLevel.READER,
			),
			global_action_permissions=frozenset(),
		)
		# thread default is editor
		assert authorization._level_satisfies(
			principal.role_resource_defaults.thread,  # type: ignore[arg-type]
			AccessLevel.EDITOR,
		)
		# project default is reader (not editor)
		assert not authorization._level_satisfies(
			principal.role_resource_defaults.project,  # type: ignore[arg-type]
			AccessLevel.EDITOR,
		)
