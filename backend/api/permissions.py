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
"""

from __future__ import annotations

import logging
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


logger = logging.getLogger(__name__)


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

	# settings
	SETTINGS_READ = "settings:read"
	SETTINGS_MANAGE = "settings:manage"

	# events
	EVENTS_READ = "events:read"
	EVENTS_MANAGE = "events:manage"

	# resource creation (for types governed by access rules)
	THREADS_CREATE = "threads:create"
	PROJECTS_CREATE = "projects:create"
	NOTES_CREATE = "notes:create"
	GROUPS_CREATE = "groups:create"
	REMINDERS_CREATE = "reminders:create"
	MEMORIES_CREATE = "memories:create"
	TASKS_CREATE = "tasks:create"
	AGENTS_CREATE = "agents:create"
	FILES_CREATE = "files:create"

	# resource admin-override (bypass access rules)
	AGENTS_MANAGE = "agents:manage"

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

	# app access
	FRONTEND_ACCESS = "frontend:access"
	CONSOLE_ACCESS = "console:access"


class ResourceType(StrEnum):
	"""supported resource types for access control."""

	THREAD = "thread"
	PROJECT = "project"
	AGENT = "agent"
	NOTE = "note"
	MEMORY = "memory"
	TASK = "task"
	FILE = "file"
	PLUGIN = "plugin"
	PROMPT = "prompt"
	GROUP = "group"
	REMINDER_LIST = "reminder_list"


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


# default resource access - typed model, one field per resource type


# resource types that support default resource access (user-owned content).
# admin-only resources (agent, plugin, prompt, memory, task) are governed
# solely by action permissions and explicit access rules.
DEFAULT_ACCESS_RESOURCE_TYPES: frozenset[ResourceType] = frozenset(
	{
		ResourceType.THREAD,
		ResourceType.PROJECT,
		ResourceType.FILE,
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


def strip_unknown_action_permissions(v: object) -> object:
	"""silently discard permission values that no longer exist.

	use as the body of a pydantic ``field_validator(mode="before")``
	on any field typed as ``set[ActionPermission]`` or
	``list[ActionPermission]``.

	this prevents deserialization failures when stored data contains
	permissions that were renamed or removed.
	"""
	if isinstance(v, (list, set, frozenset)):
		known = {p.value for p in ActionPermission}
		dropped = {x for x in v if isinstance(x, str) and x not in known}
		if dropped:
			logger.debug("ignoring unknown action permissions: %s", dropped)
		return {x for x in v if isinstance(x, str) and x in known}
	return v


class DefaultPermissions(BaseModel):
	"""
	default permissions model for both global settings and
	role-scoped defaults.

	resource_access: per-resource-type access level defaults.
	action_permissions: set of action permissions granted by
		default.
	"""

	resource_access: DefaultResourceAccess = Field(
		default_factory=DefaultResourceAccess,
	)
	action_permissions: set[ActionPermission] = Field(
		default_factory=set,
	)

	@field_validator("action_permissions", mode="before")
	@classmethod
	def _strip_unknown(cls, v: object) -> object:
		return strip_unknown_action_permissions(v)
