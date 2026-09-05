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

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.access_rule import AccessLevel, AccessRule
from api.models.agent import Agent
from api.models.calendar import Calendar, CalendarEvent
from api.models.file import File
from api.models.group import Group
from api.models.many_to_many import thread_project_association, user_role_association
from api.models.message import AssistantMessage, UserMessage
from api.models.message_attachment import MessageAttachment, resource_fk_name
from api.models.note import Note
from api.models.project import Project
from api.models.reminder import Reminder, ReminderList
from api.models.role import Role
from api.models.thread import Thread
from api.models.thread_participant import ThreadParticipant
from api.models.user import User
from api.permissions import (
	ATTACHABLE_RESOURCE_TYPES,
	ActionPermission,
	DefaultPermissions,
	DefaultResourceAccess,
	PermissionGrant,
	PermissionWildcard,
	ResourceType,
)
from api.schemas.role import RoleCreate, RoleUpdate
from api.tests.factories import make_principal
from api.v1.service import roles as roles_service
from api.v1.service.authentication import Principal, build_principal
from api.v1.service.authorization import (
	RESOURCE_CONFIG,
	allowed_levels,
	get_effective_access_level,
	level_satisfies,
	list_accessible_user_ids_for_resources,
	require_permission,
	require_resource_access,
	resource_access_predicate,
)
from api.v1.service.authorization.predicates import resource_operator_predicate
from nokodo_ai.utils.typeid import TypeID, new_typeid


_CONFIGURED_ATTACHABLE_RESOURCE_TYPES = [
	resource_type
	for resource_type, config in RESOURCE_CONFIG.items()
	if config.attachment_fk is not None
]


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

	def test_rejects_unknown_action_permission(self) -> None:
		"""an unknown name is an error: renames ship with a data migration."""
		with pytest.raises(ValidationError):
			DefaultPermissions.model_validate(
				{"action_permissions": ["agents:create", "old:removed"]}
			)

	def test_accepts_wildcard_grants(self) -> None:
		"""the two wildcard forms the resolvers honour survive validation."""
		dp = DefaultPermissions.model_validate(
			{"action_permissions": ["*", "agents:*", "agents:create"]}
		)
		assert dp.action_permissions == {
			"*",
			"agents:*",
			ActionPermission.AGENTS_CREATE,
		}

	def test_rejects_wildcard_for_unknown_domain(self) -> None:
		"""a domain no permission uses would be a silently dead grant."""
		with pytest.raises(ValidationError):
			DefaultPermissions.model_validate({"action_permissions": ["nosuch:*"]})


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
		assert ActionPermission.USER_FRIENDSHIPS_CREATE == "user.friendships:create"
		assert ActionPermission.USER_FRIENDSHIPS_MANAGE == "user.friendships:manage"
		assert ActionPermission.USER_BLOCKS_CREATE == "user.blocks:create"
		assert ActionPermission.USER_BLOCKS_MANAGE == "user.blocks:manage"

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
			"user.friendships",
			"user.blocks",
			"settings",
			"events",
			"notifications",
			"threads",
			"projects",
			"notes",
			"groups",
			"reminders",
			"memories",
			"tasks",
			"calendar",
			"agents",
			"models",
			"providers",
			"plugins",
			"prompts",
			"files",
			"mcp",
			"user.mcp",
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
			assert rt in RESOURCE_CONFIG, f"{rt} missing from RESOURCE_CONFIG"

	def test_string_values(self) -> None:
		assert ResourceType.THREAD == "thread"
		assert ResourceType.PROJECT == "project"
		assert ResourceType.FILE == "file"

	def test_attachable_resource_config_matches_registry(self) -> None:
		assert set(_CONFIGURED_ATTACHABLE_RESOURCE_TYPES) == ATTACHABLE_RESOURCE_TYPES


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
		permissions: frozenset[PermissionGrant] = frozenset(),
		global_action_permissions: frozenset[PermissionGrant] = frozenset(),
		is_superuser: bool = False,
	) -> Principal:
		return make_principal(
			is_superuser=is_superuser,
			permissions=permissions,
			global_action_permissions=global_action_permissions,
		)

	def test_no_permissions(self) -> None:
		p = self._make_principal()
		assert not p.has_permission(ActionPermission.AGENTS_CREATE)

	def test_role_permission_exact(self) -> None:
		p = self._make_principal(
			permissions=frozenset({ActionPermission.AGENTS_CREATE})
		)
		assert p.has_permission(ActionPermission.AGENTS_CREATE)
		assert not p.has_permission(ActionPermission.AGENTS_MANAGE)

	def test_role_permission_wildcard(self) -> None:
		p = self._make_principal(
			permissions=frozenset({PermissionWildcard("agents:*")})
		)
		assert p.has_permission(ActionPermission.AGENTS_CREATE)
		assert p.has_permission(ActionPermission.AGENTS_MANAGE)
		assert not p.has_permission(ActionPermission.MODELS_READ)

	def test_star_permission(self) -> None:
		p = self._make_principal(permissions=frozenset({PermissionWildcard("*")}))
		assert p.has_permission(ActionPermission.PLUGINS_MANAGE)

	@pytest.mark.asyncio
	@pytest.mark.parametrize("permission", ["*", "threads:*"])
	async def test_column_subject_wildcards_match_principal_semantics(
		self,
		db_session: AsyncSession,
		permission: str,
	) -> None:
		user = User(
			email=f"wildcard-{permission.replace(':', '-')}@example.com",
			username=f"wildcard_{permission.replace(':', '_')}",
			hashed_password="pw",
			is_active=True,
		)
		role = Role(
			name=f"wildcard {permission}",
			default_permissions={"action_permissions": [permission]},
		)
		db_session.add_all([user, role])
		await db_session.flush()
		await db_session.execute(
			insert(user_role_association).values(user_id=user.id, role_id=role.id)
		)
		matched = await db_session.scalar(
			select(User.id).where(
				User.id == user.id,
				resource_operator_predicate(User.id, ResourceType.THREAD),
			)
		)
		assert matched == user.id

	def test_superuser_bypass(self) -> None:
		p = self._make_principal(is_superuser=True)
		assert p.has_permission(ActionPermission.SETTINGS_MANAGE)

	def test_global_action_permissions(self) -> None:
		"""global defaults should grant permissions even without role perms."""
		p = self._make_principal(
			global_action_permissions=frozenset(
				{ActionPermission.AGENTS_CREATE, ActionPermission.PROMPTS_READ}
			)
		)
		assert p.has_permission(ActionPermission.AGENTS_CREATE)
		assert p.has_permission(ActionPermission.PROMPTS_READ)
		assert not p.has_permission(ActionPermission.AGENTS_MANAGE)

	def test_role_perms_take_priority_over_global(self) -> None:
		"""role perms and global perms combine (union)."""
		p = self._make_principal(
			permissions=frozenset({ActionPermission.MODELS_MANAGE}),
			global_action_permissions=frozenset({ActionPermission.AGENTS_CREATE}),
		)
		assert p.has_permission(ActionPermission.MODELS_MANAGE)
		assert p.has_permission(ActionPermission.AGENTS_CREATE)
		assert not p.has_permission(ActionPermission.SETTINGS_MANAGE)


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

		principal = await build_principal(user, db_session)
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

		principal = await build_principal(user, db_session)
		assert ActionPermission.AGENTS_CREATE in principal.permissions
		assert ActionPermission.MODELS_READ in principal.permissions
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

		principal = await build_principal(user, db_session)
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

		principal = await build_principal(user, db_session)
		# thread: admin wins over reader
		assert principal.role_resource_defaults.thread == AccessLevel.ADMIN
		# file: only role2 has it
		assert principal.role_resource_defaults.file == AccessLevel.EDITOR
		# action perms: union of both
		assert ActionPermission.AGENTS_CREATE in principal.permissions
		assert ActionPermission.MODELS_MANAGE in principal.permissions


# authorization predicate tests with role resource defaults


class TestResourceAccessPredicateWithDefaults:
	"""tests for resource_access_predicate using role_resource_defaults."""

	def _make_principal(
		self,
		user: User,
		resource_defaults: DefaultResourceAccess | None = None,
		group_ids: tuple[TypeID, ...] = (),
		role_ids: tuple[TypeID, ...] = (),
	) -> Principal:
		return Principal.for_user(
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
		pred = resource_access_predicate(principal_no_defaults, ResourceType.THREAD)
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
		pred = resource_access_predicate(principal_with_defaults, ResourceType.THREAD)
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
		pred = resource_access_predicate(
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

		principal = Principal.for_user(
			user=user,
			group_ids=(),
			role_ids=(),
			permissions=frozenset(),
			global_action_permissions=frozenset(),
		)
		level = await get_effective_access_level(
			db_session, principal, ResourceType.THREAD, thread.id
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

		principal = Principal.for_user(
			user=user,
			group_ids=(),
			role_ids=(),
			permissions=frozenset(),
			global_action_permissions=frozenset(),
		)
		level = await get_effective_access_level(
			db_session,
			principal,
			ResourceType.THREAD,
			thread.id,
			owner_id=user.id,
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

		principal = Principal.for_user(
			user=user,
			group_ids=(),
			role_ids=(),
			permissions=frozenset(),
			role_resource_defaults=DefaultResourceAccess(
				thread=AccessLevel.READER,
			),
			global_action_permissions=frozenset(),
		)
		level = await get_effective_access_level(
			db_session, principal, ResourceType.THREAD, thread.id
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

		principal = Principal.for_user(
			user=user,
			group_ids=(),
			role_ids=(),
			permissions=frozenset(),
			role_resource_defaults=DefaultResourceAccess(
				thread=AccessLevel.EDITOR,
			),
			global_action_permissions=frozenset(),
		)
		level = await get_effective_access_level(
			db_session, principal, ResourceType.THREAD, thread.id
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

		principal = Principal.for_user(
			user=admin,
			group_ids=(),
			role_ids=(),
			permissions=frozenset(),
			global_action_permissions=frozenset(),
		)
		level = await get_effective_access_level(
			db_session, principal, ResourceType.THREAD, thread.id
		)
		assert level == AccessLevel.ADMIN

	@pytest.mark.asyncio
	async def test_subjectless_rule_grants_direct_access(
		self, db_session: AsyncSession
	) -> None:
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

		principal = Principal.for_user(
			user=user,
			group_ids=(),
			role_ids=(),
			permissions=frozenset(),
			global_action_permissions=frozenset(),
		)
		level = await get_effective_access_level(
			db_session,
			principal,
			ResourceType.THREAD,
			thread.id,
			include_link_access=True,
		)
		assert level == AccessLevel.READER
		assert (
			await get_effective_access_level(
				db_session, principal, ResourceType.THREAD, thread.id
			)
			is None
		)

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

		principal = Principal.for_user(
			user=user,
			group_ids=(group.id,),
			role_ids=(),
			permissions=frozenset(),
			global_action_permissions=frozenset(),
		)
		level = await get_effective_access_level(
			db_session, principal, ResourceType.THREAD, thread.id
		)
		assert level == AccessLevel.EDITOR

	@pytest.mark.asyncio
	async def test_project_rule_inherits_to_child_thread(
		self, db_session: AsyncSession
	) -> None:
		owner = User(
			email="proj-thread-owner@example.com",
			username="proj_thread_owner",
			hashed_password="pw",
		)
		viewer = User(
			email="proj-thread-viewer@example.com",
			username="proj_thread_viewer",
			hashed_password="pw",
		)
		db_session.add_all([owner, viewer])
		await db_session.flush()

		project = Project(name="inherited project", owner_id=owner.id)
		thread = Thread(
			title="project child thread",
			owner_id=owner.id,
			is_temporary=False,
		)
		db_session.add_all([project, thread])
		await db_session.flush()
		await db_session.execute(
			insert(thread_project_association).values(
				thread_id=thread.id,
				project_id=project.id,
			)
		)
		db_session.add(
			AccessRule(
				project_id=project.id,
				subject_user_id=viewer.id,
				level=AccessLevel.READER,
			)
		)
		await db_session.commit()

		principal = Principal.for_user(
			user=viewer,
			group_ids=(),
			role_ids=(),
			permissions=frozenset(),
			global_action_permissions=frozenset(),
		)
		level = await get_effective_access_level(
			db_session,
			principal,
			ResourceType.THREAD,
			thread.id,
		)
		assert level == AccessLevel.READER
		await require_resource_access(
			thread.id,
			db_session,
			principal,
			ResourceType.THREAD,
			required_level=AccessLevel.READER,
		)
		result = await db_session.execute(
			select(Thread.id).where(
				Thread.id == thread.id,
				resource_access_predicate(
					principal,
					ResourceType.THREAD,
				),
			)
		)
		assert result.scalar_one_or_none() == thread.id
		accessible_user_ids = await list_accessible_user_ids_for_resources(
			[(ResourceType.THREAD, thread.id)], db_session
		)
		assert viewer.id in accessible_user_ids

	@pytest.mark.asyncio
	async def test_project_access_reaches_chat_attachment_as_reader_only(
		self, db_session: AsyncSession
	) -> None:
		"""reaching a chat attachment through a thread tops out at READER.

		the viewer is a project EDITOR and the thread lives in that project, so
		they can edit the thread - but a file merely attached to a message is a
		chat attachment owned by someone else. thread-reached file access is
		capped at READER, so the viewer can view it but not edit or delete it.
		project *documents* (project -> file association) are a separate uncapped
		link and are unaffected.
		"""
		owner = User(
			email="proj-file-owner@example.com",
			username="proj_file_owner",
			hashed_password="pw",
		)
		viewer = User(
			email="proj-file-viewer@example.com",
			username="proj_file_viewer",
			hashed_password="pw",
		)
		db_session.add_all([owner, viewer])
		await db_session.flush()

		project = Project(name="file inherited project", owner_id=owner.id)
		thread = Thread(
			title="file parent thread",
			owner_id=owner.id,
			is_temporary=False,
		)
		db_session.add_all([project, thread])
		await db_session.flush()
		message = UserMessage(thread_id=thread.id)
		db_session.add(message)
		await db_session.flush()
		file = File(
			owner_id=owner.id,
			storage_backend="local",
			storage_key="acl-inherited-file.txt",
			filename="acl-inherited-file.txt",
		)
		db_session.add(file)
		await db_session.flush()
		db_session.add(
			MessageAttachment(
				message_id=message.id,
				position=0,
				file_id=file.id,
			)
		)
		await db_session.execute(
			insert(thread_project_association).values(
				thread_id=thread.id,
				project_id=project.id,
			)
		)
		db_session.add(
			AccessRule(
				project_id=project.id,
				subject_user_id=viewer.id,
				level=AccessLevel.EDITOR,
			)
		)
		await db_session.commit()

		principal = Principal.for_user(
			user=viewer,
			group_ids=(),
			role_ids=(),
			permissions=frozenset(),
			global_action_permissions=frozenset(),
		)
		# capped at READER even though the viewer is a project (and thus thread)
		# EDITOR.
		level = await get_effective_access_level(
			db_session,
			principal,
			ResourceType.FILE,
			file.id,
		)
		assert level == AccessLevel.READER
		await require_resource_access(
			file.id,
			db_session,
			principal,
			ResourceType.FILE,
			required_level=AccessLevel.READER,
		)
		result = await db_session.execute(
			select(File.id).where(
				File.id == file.id,
				resource_access_predicate(
					principal,
					ResourceType.FILE,
					required_level=AccessLevel.READER,
				),
			)
		)
		assert result.scalar_one_or_none() == file.id
		accessible_user_ids = await list_accessible_user_ids_for_resources(
			[(ResourceType.FILE, file.id)],
			db_session,
			required_level=AccessLevel.READER,
		)
		assert viewer.id in accessible_user_ids
		# but editing the chat attachment is denied - the cap blocks it.
		with pytest.raises(HTTPException) as exc:
			await require_resource_access(
				file.id,
				db_session,
				principal,
				ResourceType.FILE,
				required_level=AccessLevel.EDITOR,
			)
		assert exc.value.status_code == 404
		editor_user_ids = await list_accessible_user_ids_for_resources(
			[(ResourceType.FILE, file.id)],
			db_session,
			required_level=AccessLevel.EDITOR,
		)
		assert viewer.id not in editor_user_ids

	@pytest.mark.asyncio
	@pytest.mark.parametrize(
		"resource_type",
		_CONFIGURED_ATTACHABLE_RESOURCE_TYPES,
	)
	async def test_thread_admin_reaches_every_attachment_as_reader_only(
		self,
		db_session: AsyncSession,
		resource_type: ResourceType,
	) -> None:
		thread_owner = User(
			email=f"attachment-admin-{resource_type.value}@example.com",
			username=f"attachment_admin_{resource_type.value}",
			hashed_password="pw",
		)
		resource_owner = User(
			email=f"attachment-owner-{resource_type.value}@example.com",
			username=f"attachment_owner_{resource_type.value}",
			hashed_password="pw",
		)
		db_session.add_all([thread_owner, resource_owner])
		await db_session.flush()
		thread = Thread(
			title=f"{resource_type.value} attachment parent",
			owner_id=thread_owner.id,
			is_temporary=False,
		)
		db_session.add(thread)
		await db_session.flush()
		message = UserMessage(thread_id=thread.id, sender_user_id=thread_owner.id)
		db_session.add(message)
		await db_session.flush()

		match resource_type:
			case ResourceType.FILE:
				resource = File(
					owner_id=resource_owner.id,
					storage_backend="local",
					storage_key="all-attachment-types.txt",
					filename="all-attachment-types.txt",
				)
			case ResourceType.NOTE:
				resource = Note(
					user_id=resource_owner.id,
					title="attachment note",
					content="private",
				)
			case ResourceType.THREAD:
				resource = Thread(
					owner_id=resource_owner.id,
					title="attached thread",
					is_temporary=False,
				)
			case ResourceType.PROJECT:
				resource = Project(
					owner_id=resource_owner.id,
					name="attached project",
				)
			case ResourceType.REMINDER_LIST:
				resource = ReminderList(
					owner_id=resource_owner.id,
					name="attached reminder list",
				)
			case ResourceType.REMINDER:
				parent = ReminderList(
					owner_id=resource_owner.id,
					name="private reminder list",
				)
				db_session.add(parent)
				await db_session.flush()
				resource = Reminder(
					owner_id=resource_owner.id,
					list_id=parent.id,
					title="attached reminder",
				)
			case ResourceType.CALENDAR:
				resource = Calendar(
					owner_id=resource_owner.id,
					name="attached calendar",
				)
			case ResourceType.CALENDAR_EVENT:
				parent = Calendar(
					owner_id=resource_owner.id,
					name="private calendar",
				)
				db_session.add(parent)
				await db_session.flush()
				start_at = datetime(2026, 8, 10, 9, tzinfo=UTC)
				resource = CalendarEvent(
					owner_id=resource_owner.id,
					calendar_id=parent.id,
					title="attached event",
					start_at=start_at,
					end_at=start_at + timedelta(hours=1),
				)
			case _:
				raise AssertionError(f"unsupported attachment type {resource_type}")
		db_session.add(resource)
		await db_session.flush()
		db_session.add(
			MessageAttachment(
				message_id=message.id,
				position=0,
				**{resource_fk_name(resource_type): resource.id},
			)
		)
		await db_session.flush()
		principal = Principal.for_user(
			user=thread_owner,
			group_ids=(),
			role_ids=(),
			permissions=frozenset(),
			global_action_permissions=frozenset(),
		)

		assert (
			await get_effective_access_level(
				db_session,
				principal,
				resource_type,
				resource.id,
			)
			== AccessLevel.READER
		)
		with pytest.raises(HTTPException) as exc:
			await require_resource_access(
				resource.id,
				db_session,
				principal,
				resource_type,
				required_level=AccessLevel.EDITOR,
			)
		assert exc.value.status_code == 404

	@pytest.mark.asyncio
	async def test_thread_participant_reads_attached_file_but_not_admin(
		self, db_session: AsyncSession
	) -> None:
		"""a co-participant inherits read access to attachments but never ADMIN.

		sharing a conversation lets you view its attachments (inherited through
		the thread), but it must NOT make you owner/admin of someone else's
		file - you cannot delete the original or change its sharing.
		"""
		owner = User(
			email="tp-file-owner@example.com",
			username="tp_file_owner",
			hashed_password="pw",
		)
		participant = User(
			email="tp-file-participant@example.com",
			username="tp_file_participant",
			hashed_password="pw",
		)
		db_session.add_all([owner, participant])
		await db_session.flush()

		thread = Thread(
			title="attachment thread",
			owner_id=owner.id,
			is_temporary=False,
		)
		db_session.add(thread)
		await db_session.flush()
		message = UserMessage(thread_id=thread.id)
		db_session.add(message)
		await db_session.flush()
		file = File(
			owner_id=owner.id,
			storage_backend="local",
			storage_key="tp-attached-file.txt",
			filename="tp-attached-file.txt",
		)
		db_session.add(file)
		await db_session.flush()
		db_session.add(
			MessageAttachment(
				message_id=message.id,
				position=0,
				file_id=file.id,
			)
		)
		# a participant is granted access on the THREAD (what ensure_participant
		# does on join); access to the attached file is derived from this.
		db_session.add(
			AccessRule(
				thread_id=thread.id,
				subject_user_id=participant.id,
				level=AccessLevel.EDITOR,
			)
		)
		await db_session.commit()

		principal = Principal.for_user(
			user=participant,
			group_ids=(),
			role_ids=(),
			permissions=frozenset(),
			global_action_permissions=frozenset(),
		)
		# can view the attachment (read access inherited through the thread)
		await require_resource_access(
			file.id,
			db_session,
			principal,
			ResourceType.FILE,
			required_level=AccessLevel.READER,
		)
		with pytest.raises(HTTPException) as exc:
			await require_resource_access(
				file.id,
				db_session,
				principal,
				ResourceType.FILE,
				required_level=AccessLevel.EDITOR,
			)
		assert exc.value.status_code == 404
		# but never ADMIN on a file they do not own - no delete / resharing.
		with pytest.raises(HTTPException) as exc:
			await require_resource_access(
				file.id,
				db_session,
				principal,
				ResourceType.FILE,
				required_level=AccessLevel.ADMIN,
			)
		assert exc.value.status_code == 404

	@pytest.mark.asyncio
	async def test_thread_participant_loses_attached_file_access_on_leave(
		self, db_session: AsyncSession
	) -> None:
		"""leaving a thread revokes access to its attachments automatically.

		file access is derived through the thread link, not copied onto the
		file, so dropping the thread access rule (what removal/decline does)
		removes attachment access with no per-file cleanup.
		"""
		owner = User(
			email="leave-file-owner@example.com",
			username="leave_file_owner",
			hashed_password="pw",
		)
		participant = User(
			email="leave-file-participant@example.com",
			username="leave_file_participant",
			hashed_password="pw",
		)
		db_session.add_all([owner, participant])
		await db_session.flush()

		thread = Thread(
			title="leave attachment thread",
			owner_id=owner.id,
			is_temporary=False,
		)
		db_session.add(thread)
		await db_session.flush()
		message = UserMessage(thread_id=thread.id)
		db_session.add(message)
		await db_session.flush()
		file = File(
			owner_id=owner.id,
			storage_backend="local",
			storage_key="leave-attached-file.txt",
			filename="leave-attached-file.txt",
		)
		db_session.add(file)
		await db_session.flush()
		db_session.add(
			MessageAttachment(
				message_id=message.id,
				position=0,
				file_id=file.id,
			)
		)
		rule = AccessRule(
			thread_id=thread.id,
			subject_user_id=participant.id,
			level=AccessLevel.EDITOR,
		)
		db_session.add(rule)
		await db_session.commit()

		principal = Principal.for_user(
			user=participant,
			group_ids=(),
			role_ids=(),
			permissions=frozenset(),
			global_action_permissions=frozenset(),
		)
		# while participating, the attachment is readable.
		await require_resource_access(
			file.id,
			db_session,
			principal,
			ResourceType.FILE,
			required_level=AccessLevel.READER,
		)

		# leave the thread: drop the thread access rule.
		await db_session.delete(rule)
		await db_session.commit()

		# attachment access is gone - it was derived, never copied onto the file.
		assert (
			await get_effective_access_level(
				db_session,
				principal,
				ResourceType.FILE,
				file.id,
			)
			is None
		)
		with pytest.raises(HTTPException) as exc:
			await require_resource_access(
				file.id,
				db_session,
				principal,
				ResourceType.FILE,
				required_level=AccessLevel.READER,
			)
		assert exc.value.status_code == 404

	@pytest.mark.asyncio
	async def test_thread_reader_inherits_reader_on_thread_agents_capped(
		self, db_session: AsyncSession
	) -> None:
		"""reading a thread grants READER on its agents - never more.

		an agent that is a thread participant, or that authored any message in
		the thread, is readable by anyone who can read the thread (so they can
		see who is in the conversation). but thread access is capped at READER:
		even a thread EDITOR must not be able to edit or delete the agent.
		"""
		owner = User(
			email="agent-inherit-owner@example.com",
			username="agent_inherit_owner",
			hashed_password="pw",
		)
		viewer = User(
			email="agent-inherit-viewer@example.com",
			username="agent_inherit_viewer",
			hashed_password="pw",
		)
		outsider = User(
			email="agent-inherit-outsider@example.com",
			username="agent_inherit_outsider",
			hashed_password="pw",
		)
		db_session.add_all([owner, viewer, outsider])
		await db_session.flush()

		participant_agent = Agent(name="participant agent")
		author_agent = Agent(name="author agent")
		db_session.add_all([participant_agent, author_agent])
		await db_session.flush()

		thread = Thread(
			title="agent inheritance thread",
			owner_id=owner.id,
			is_temporary=False,
		)
		db_session.add(thread)
		await db_session.flush()
		# one agent is a participant, the other only authored a message.
		db_session.add(
			ThreadParticipant(thread_id=thread.id, agent_id=participant_agent.id)
		)
		db_session.add(
			AssistantMessage(thread_id=thread.id, sender_agent_id=author_agent.id)
		)
		# the viewer is a thread EDITOR - strong enough to expose any cap bug.
		db_session.add(
			AccessRule(
				thread_id=thread.id,
				subject_user_id=viewer.id,
				level=AccessLevel.EDITOR,
			)
		)
		await db_session.commit()

		viewer_principal = Principal.for_user(
			user=viewer,
			group_ids=(),
			role_ids=(),
			permissions=frozenset(),
			global_action_permissions=frozenset(),
		)
		for agent in (participant_agent, author_agent):
			# inherits READER through the thread...
			assert (
				await get_effective_access_level(
					db_session,
					viewer_principal,
					ResourceType.AGENT,
					agent.id,
				)
				== AccessLevel.READER
			)
			# ...but the EDITOR thread level is clamped: no edit on the agent.
			result = await db_session.execute(
				select(Agent.id).where(
					Agent.id == agent.id,
					resource_access_predicate(
						viewer_principal,
						ResourceType.AGENT,
						required_level=AccessLevel.EDITOR,
					),
				)
			)
			assert result.scalar_one_or_none() is None

		# someone with no thread access sees neither agent.
		outsider_principal = Principal.for_user(
			user=outsider,
			group_ids=(),
			role_ids=(),
			permissions=frozenset(),
			global_action_permissions=frozenset(),
		)
		assert (
			await get_effective_access_level(
				db_session,
				outsider_principal,
				ResourceType.AGENT,
				participant_agent.id,
			)
			is None
		)


# require_permission tests


class TestRequirePermission:
	"""tests for require_permission with typed ActionPermission."""

	def test_denies_without_permission(self) -> None:
		principal = make_principal(slug="deny_perm")
		with pytest.raises(HTTPException) as exc:
			require_permission(principal, ActionPermission.AGENTS_MANAGE)
		assert exc.value.status_code == 403

	def test_allows_with_exact_permission(self) -> None:
		principal = make_principal(
			slug="allow_perm",
			permissions=frozenset({ActionPermission.AGENTS_MANAGE}),
		)
		require_permission(principal, ActionPermission.AGENTS_MANAGE)

	def test_allows_with_global_defaults(self) -> None:
		"""global default action perms should satisfy require_permission."""
		principal = make_principal(
			slug="global_allow",
			global_action_permissions=frozenset({ActionPermission.AGENTS_CREATE}),
		)
		require_permission(principal, ActionPermission.AGENTS_CREATE)

	def test_superuser_bypass(self) -> None:
		principal = make_principal(slug="su_perm_test", is_superuser=True)
		require_permission(principal, ActionPermission.SETTINGS_MANAGE)


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

		principal = Principal.for_user(
			user=user,
			group_ids=(),
			role_ids=(),
			permissions=frozenset(),
			global_action_permissions=frozenset(),
		)
		with pytest.raises(HTTPException) as exc:
			await require_resource_access(
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

		principal = Principal.for_user(
			user=user,
			group_ids=(),
			role_ids=(),
			permissions=frozenset(),
			global_action_permissions=frozenset(),
		)
		with pytest.raises(HTTPException) as exc:
			await require_resource_access(
				thread.id,
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

		principal = Principal.for_user(
			user=user,
			group_ids=(),
			role_ids=(),
			permissions=frozenset(),
			global_action_permissions=frozenset(),
		)
		await require_resource_access(
			thread.id,
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

		principal = Principal.for_user(
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

		principal = Principal.for_user(
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
			role.id,
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

		principal = Principal.for_user(
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

		await roles_service.delete_role(role.id, db_session, principal=principal)
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

		principal = Principal.for_user(
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

		principal = Principal.for_user(
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
		principal_no_role = Principal.for_user(
			user=user,
			group_ids=(),
			role_ids=(),
			permissions=frozenset(),
			global_action_permissions=frozenset(),
		)
		level = await get_effective_access_level(
			db_session, principal_no_role, ResourceType.THREAD, thread.id
		)
		assert level is None

		# user WITH the role
		principal_with_role = Principal.for_user(
			user=user,
			group_ids=(),
			role_ids=(role.id,),
			permissions=frozenset(),
			global_action_permissions=frozenset(),
		)
		level = await get_effective_access_level(
			db_session, principal_with_role, ResourceType.THREAD, thread.id
		)
		assert level == AccessLevel.EDITOR


# edge case tests


class TestEdgeCases:
	"""edge cases and boundary conditions."""

	def test_level_satisfies(self) -> None:
		assert level_satisfies(AccessLevel.ADMIN, AccessLevel.READER)
		assert level_satisfies(AccessLevel.ADMIN, AccessLevel.EDITOR)
		assert level_satisfies(AccessLevel.ADMIN, AccessLevel.ADMIN)
		assert level_satisfies(AccessLevel.EDITOR, AccessLevel.READER)
		assert not level_satisfies(AccessLevel.READER, AccessLevel.EDITOR)
		assert not level_satisfies(AccessLevel.READER, AccessLevel.ADMIN)

	def test_allowed_levels(self) -> None:
		assert allowed_levels(AccessLevel.READER) == (
			AccessLevel.READER,
			AccessLevel.EDITOR,
			AccessLevel.ADMIN,
		)
		assert allowed_levels(AccessLevel.EDITOR) == (
			AccessLevel.EDITOR,
			AccessLevel.ADMIN,
		)
		assert allowed_levels(AccessLevel.ADMIN) == (AccessLevel.ADMIN,)

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
	async def test_highest_matching_rule_wins(self, db_session: AsyncSession) -> None:
		"""the highest matching explicit rule wins regardless of display order."""
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
		group = Group(name="order-group", owner_id=owner.id)
		db_session.add_all([thread, group])
		await db_session.flush()

		# Both subjects match; the later reader cannot demote the earlier admin.
		rule1 = AccessRule(
			subject_user_id=str(user.id),
			thread_id=str(thread.id),
			level=AccessLevel.ADMIN,
			order_index=0,
		)
		rule2 = AccessRule(
			subject_group_id=group.id,
			thread_id=str(thread.id),
			level=AccessLevel.READER,
			order_index=1,
		)
		db_session.add_all([rule1, rule2])
		await db_session.commit()

		principal = Principal.for_user(
			user=user,
			group_ids=(group.id,),
			role_ids=(),
			permissions=frozenset(),
			global_action_permissions=frozenset(),
		)
		level = await get_effective_access_level(
			db_session, principal, ResourceType.THREAD, thread.id
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

		principal = Principal.for_user(
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
		assert level_satisfies(
			principal.role_resource_defaults.thread,  # type: ignore[arg-type]
			AccessLevel.EDITOR,
		)
		# project default is reader (not editor)
		assert not level_satisfies(
			principal.role_resource_defaults.project,  # type: ignore[arg-type]
			AccessLevel.EDITOR,
		)
