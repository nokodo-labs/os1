"""permission type definitions - canonical source of truth.

enums and the DefaultPermissions model live here so both
``api.models`` and ``api.settings`` can import them without
introducing a cross-layer dependency.

design rules:
- resources with an access-rule system do NOT get read action
  permissions. reading/managing existing objects is governed by
  access rules (READER / EDITOR / ADMIN levels).
- creating NEW objects of a resource type that has access rules
  requires a ``{domain}:create`` action permission, because no
  resource exists yet to attach rules to.
- ``{domain}:manage`` is an admin-override that bypasses access
  rules for update/delete of all instances.
- resources WITHOUT access rules only need ``{domain}:read`` and
  ``{domain}:manage``. manage includes creation, so no separate
  create permission is needed.
- user social resources (friendships, blocks) require a ``user.{type}:create``
	permission to create new entries. users can always manage their own
	existing social resources (accept/decline/cancel/remove). cross-user
	moderation requires the corresponding ``user.{type}:manage`` permission
	or superuser access.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from enum import StrEnum
from types import MappingProxyType
from typing import Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, GetCoreSchemaHandler
from pydantic_core import core_schema


class AccessLevel(StrEnum):
	"""level of access granted by an access rule or role default."""

	READER = "reader"
	EDITOR = "editor"
	ADMIN = "admin"


class ActionPermission(StrEnum):
	"""
	typed action permissions for role-based authorization.

	use require_permission() to enforce them in service/router code.

	naming convention: {domain}:{action}
	"""

	# role management
	ROLES_READ = "roles:read"
	ROLES_MANAGE = "roles:manage"

	# user management
	USERS_READ = "users:read"
	USERS_MANAGE = "users:manage"
	USER_FRIENDSHIPS_CREATE = "user.friendships:create"
	USER_FRIENDSHIPS_MANAGE = "user.friendships:manage"
	USER_BLOCKS_CREATE = "user.blocks:create"
	USER_BLOCKS_MANAGE = "user.blocks:manage"

	# settings
	# currently unenforced: the public settings dump is anonymous (login /
	# bootstrap need it) and the private dump is gated by settings:manage.
	SETTINGS_READ = "settings:read"
	SETTINGS_MANAGE = "settings:manage"

	# events
	EVENTS_READ = "events:read"
	EVENTS_MANAGE = "events:manage"

	# notifications
	NOTIFICATIONS_MANAGE = "notifications:manage"

	# resource creation (for types governed by access rules).
	# a domain permission covers every resource type in that domain, so
	# reminders also covers reminder lists and calendar also covers events.
	THREADS_CREATE = "threads:create"
	PROJECTS_CREATE = "projects:create"
	NOTES_CREATE = "notes:create"
	GROUPS_CREATE = "groups:create"
	REMINDERS_CREATE = "reminders:create"
	CALENDAR_CREATE = "calendar:create"
	MEMORIES_CREATE = "memories:create"
	TASKS_CREATE = "tasks:create"
	AGENTS_CREATE = "agents:create"
	FILES_CREATE = "files:create"

	# resource admin-override (bypass access rules)
	THREADS_MANAGE = "threads:manage"
	PROJECTS_MANAGE = "projects:manage"
	NOTES_MANAGE = "notes:manage"
	GROUPS_MANAGE = "groups:manage"
	REMINDERS_MANAGE = "reminders:manage"
	CALENDAR_MANAGE = "calendar:manage"
	FILES_MANAGE = "files:manage"
	AGENTS_MANAGE = "agents:manage"
	TASKS_MANAGE = "tasks:manage"
	MEMORIES_MANAGE = "memories:manage"

	# admin-managed resources (no access rules, manage includes create)
	PLUGINS_READ = "plugins:read"
	PLUGINS_MANAGE = "plugins:manage"
	PROMPTS_READ = "prompts:read"
	PROMPTS_MANAGE = "prompts:manage"

	# models / providers (admin-only, no access rules)
	MODELS_READ = "models:read"
	MODELS_MANAGE = "models:manage"
	PROVIDERS_READ = "providers:read"
	PROVIDERS_MANAGE = "providers:manage"
	MCP_MANAGE = "mcp:manage"
	USER_MCP_MANAGE = "user.mcp:manage"

	# app access
	FRONTEND_ACCESS = "frontend:access"
	CONSOLE_ACCESS = "console:access"


class ResourceType(StrEnum):
	"""supported resource types for access control."""

	THREAD = "thread"
	MESSAGE = "message"
	PROJECT = "project"
	AGENT = "agent"
	NOTE = "note"
	MEMORY = "memory"
	TASK = "task"
	FILE = "file"
	CALENDAR = "calendar"
	CALENDAR_EVENT = "calendar_event"
	PLUGIN = "plugin"
	PROMPT = "prompt"
	GROUP = "group"
	REMINDER = "reminder"
	REMINDER_LIST = "reminder_list"


type AttachableResourceType = Literal[
	ResourceType.FILE,
	ResourceType.NOTE,
	ResourceType.THREAD,
	ResourceType.PROJECT,
	ResourceType.REMINDER,
	ResourceType.REMINDER_LIST,
	ResourceType.CALENDAR_EVENT,
	ResourceType.CALENDAR,
]


ATTACHABLE_RESOURCE_TYPES: frozenset[ResourceType] = frozenset(
	get_args(AttachableResourceType.__value__)
)
"""resource types that can be attached to messages."""


class MentionableSubjectType(StrEnum):
	"""kinds of subject a message can address.

	not a ``ResourceType`` subset: a user is a principal rather than an owned
	resource, so mentionable subjects are their own closed set.
	"""

	AGENT = "agent"
	USER = "user"
	GROUP = "group"


RESOURCE_MANAGE_PERMISSION: Mapping[ResourceType, ActionPermission] = MappingProxyType(
	{
		ResourceType.THREAD: ActionPermission.THREADS_MANAGE,
		ResourceType.MESSAGE: ActionPermission.THREADS_MANAGE,
		ResourceType.PROJECT: ActionPermission.PROJECTS_MANAGE,
		ResourceType.NOTE: ActionPermission.NOTES_MANAGE,
		ResourceType.GROUP: ActionPermission.GROUPS_MANAGE,
		ResourceType.REMINDER_LIST: ActionPermission.REMINDERS_MANAGE,
		ResourceType.REMINDER: ActionPermission.REMINDERS_MANAGE,
		ResourceType.CALENDAR: ActionPermission.CALENDAR_MANAGE,
		ResourceType.CALENDAR_EVENT: ActionPermission.CALENDAR_MANAGE,
		ResourceType.FILE: ActionPermission.FILES_MANAGE,
		ResourceType.AGENT: ActionPermission.AGENTS_MANAGE,
		ResourceType.TASK: ActionPermission.TASKS_MANAGE,
		ResourceType.PLUGIN: ActionPermission.PLUGINS_MANAGE,
		ResourceType.PROMPT: ActionPermission.PROMPTS_MANAGE,
		ResourceType.MEMORY: ActionPermission.MEMORIES_MANAGE,
	}
)
"""the operator permission for each resource type.

leaf types resolve to their parent domain's permission, so an operator of a
domain is an operator of everything in it.
"""

if set(RESOURCE_MANAGE_PERMISSION) != set(ResourceType):
	raise RuntimeError("RESOURCE_MANAGE_PERMISSION must cover every resource type")


# access-level rank helper

_LEVEL_RANK: dict[AccessLevel, int] = {
	AccessLevel.READER: 0,
	AccessLevel.EDITOR: 1,
	AccessLevel.ADMIN: 2,
}


def higher_access(
	a: AccessLevel | None,
	b: AccessLevel | None,
) -> AccessLevel | None:
	"""return whichever access level is higher, or None if both are None."""
	if a is None:
		return b
	if b is None:
		return a
	return a if _LEVEL_RANK[a] >= _LEVEL_RANK[b] else b


def highest_access(levels: Iterable[AccessLevel | None]) -> AccessLevel | None:
	"""return the highest access level in an iterable."""
	result: AccessLevel | None = None
	for level in levels:
		result = higher_access(result, level)
	return result


def lowest_access(levels: Iterable[AccessLevel]) -> AccessLevel | None:
	"""return the lowest access level in an iterable, or None if empty."""
	result: AccessLevel | None = None
	for level in levels:
		if result is None or _LEVEL_RANK[level] < _LEVEL_RANK[result]:
			result = level
	return result


def level_satisfies(granted: AccessLevel, required: AccessLevel) -> bool:
	"""check whether one access level satisfies another."""
	return _LEVEL_RANK[granted] >= _LEVEL_RANK[required]


def access_level_index(level: AccessLevel) -> int:
	"""return the canonical index of an access level."""
	return _LEVEL_RANK[level]


# default resource access - typed model, one field per resource type


# resource types that support default resource access (user-owned content).
# admin-only resources (agent, plugin, prompt, memory, task) are governed
# solely by action permissions and explicit access rules.
DEFAULT_ACCESS_RESOURCE_TYPES: frozenset[ResourceType] = frozenset(
	{
		ResourceType.THREAD,
		ResourceType.PROJECT,
		ResourceType.FILE,
		ResourceType.CALENDAR,
		ResourceType.NOTE,
		ResourceType.GROUP,
		ResourceType.REMINDER_LIST,
	}
)


class DefaultResourceAccess(BaseModel):
	"""
	per-resource-type access level defaults.

	only covers user-owned resource types. admin-only resources
	(agents, plugins, prompts, memories, tasks) are controlled via
	action permissions and explicit access rules instead.

	``None`` means "no default for this resource type" - inherits
	from the global settings when used on a role, or means "no
	access" when used on the global settings themselves.
	"""

	model_config = ConfigDict(extra="ignore")

	thread: AccessLevel | None = None
	project: AccessLevel | None = None
	file: AccessLevel | None = None
	calendar: AccessLevel | None = None
	note: AccessLevel | None = None
	group: AccessLevel | None = None
	reminder_list: AccessLevel | None = None

	def get(self, resource_type: ResourceType) -> AccessLevel | None:
		"""look up the access level for a resource type."""
		field_name = resource_type.value
		if field_name not in type(self).model_fields:
			return None
		return self.__dict__.get(field_name)

	def merge(self, other: DefaultResourceAccess) -> DefaultResourceAccess:
		"""merge two access models, keeping the higher level for each."""
		return DefaultResourceAccess(
			**{
				rt.value: higher_access(self.get(rt), other.get(rt))
				for rt in DEFAULT_ACCESS_RESOURCE_TYPES
			}
		)


ALL_PERMISSIONS_WILDCARD = "*"
"""grants every action permission."""

DOMAIN_WILDCARD_SUFFIX = ":*"
"""suffix marking a `<domain>:*` grant."""

ACTION_PERMISSION_DOMAINS: frozenset[str] = frozenset(
	permission.value.split(":", 1)[0] for permission in ActionPermission
)
"""every domain that a `<domain>:*` wildcard may name."""


def permission_domain(permission: str) -> str:
	"""return the domain half of a `{domain}:{action}` permission."""
	return permission.split(":", 1)[0]


def domain_wildcard(domain: str) -> str:
	"""return the wildcard grant covering one domain."""
	return f"{domain}{DOMAIN_WILDCARD_SUFFIX}"


def wildcards_granting(permission: str) -> tuple[str, str]:
	"""return every wildcard grant that satisfies one permission.

	the ONE place that says which wildcards imply a permission. both the python
	resolver and the SQL operator arms match against exactly these, so the two
	engines cannot drift on wildcard semantics.
	"""
	return (
		ALL_PERMISSIONS_WILDCARD,
		domain_wildcard(permission_domain(permission)),
	)


def permission_satisfied_by(permission: str, granted: Iterable[str]) -> bool:
	"""whether a set of grants confers one permission, wildcards included."""
	grants = set(granted)
	if permission in grants:
		return True
	return any(wildcard in grants for wildcard in wildcards_granting(permission))


class PermissionWildcard(str):
	"""`*` or `<domain>:*` - the only non-enum action-permission grants.

	a real type, not an alias: constructing one validates, so a wildcard that
	reaches a principal or the settings store has been checked exactly once, by
	the same code pydantic runs. `wildcards_granting` produces exactly these
	two shapes, so any other string would be a silently dead grant.
	"""

	__slots__ = ()

	def __new__(cls, value: str) -> PermissionWildcard:
		if value != ALL_PERMISSIONS_WILDCARD:
			if not value.endswith(DOMAIN_WILDCARD_SUFFIX):
				raise ValueError(f"not an action permission or wildcard: {value!r}")
			domain = value[: -len(DOMAIN_WILDCARD_SUFFIX)]
			if domain not in ACTION_PERMISSION_DOMAINS:
				raise ValueError(f"unknown action permission domain: {domain!r}")
		return super().__new__(cls, value)

	@classmethod
	def __get_pydantic_core_schema__(
		cls,
		source_type: object,
		handler: GetCoreSchemaHandler,
	) -> core_schema.CoreSchema:
		_ = source_type, handler
		return core_schema.no_info_after_validator_function(
			cls,
			core_schema.str_schema(),
		)


type PermissionGrant = ActionPermission | PermissionWildcard
"""one stored action-permission grant: a known permission or a wildcard."""


def permission_grant(value: str) -> PermissionGrant:
	"""parse one stored grant, raising for a name that is neither."""
	try:
		return ActionPermission(value)
	except ValueError:
		return PermissionWildcard(value)


class DefaultPermissions(BaseModel):
	"""
	default permissions model for both global settings and
	role-scoped defaults.

	resource_access: per-resource-type access level defaults.
	action_permissions: set of action permissions granted by
		default.

	an unknown permission name is an error, not something to drop: renaming or
	removing a permission ships with a data migration that rewrites the stored
	values, so stale names never reach this model.
	"""

	resource_access: DefaultResourceAccess = Field(
		default_factory=DefaultResourceAccess,
	)
	action_permissions: set[PermissionGrant] = Field(
		default_factory=set,
	)
