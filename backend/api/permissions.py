"""permission type definitions — canonical source of truth.

enums and the DefaultPermissions model live here so both
``api.models`` and ``api.settings`` can import them without
introducing a cross-layer dependency.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


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
	ROLES_ADMIN = "roles:admin"

	# user management
	USERS_READ = "users:read"
	USERS_MANAGE = "users:manage"
	USERS_CREATE = "users:create"

	# settings
	SETTINGS_READ = "settings:read"
	SETTINGS_WRITE = "settings:write"

	# events
	EVENTS_READ = "events:read"
	EVENTS_MANAGE = "events:manage"

	# agents
	AGENTS_READ = "agents:read"
	AGENTS_MANAGE = "agents:manage"

	# models / providers
	MODELS_READ = "models:read"
	MODELS_MANAGE = "models:manage"
	PROVIDERS_READ = "providers:read"
	PROVIDERS_MANAGE = "providers:manage"

	# plugins
	PLUGINS_READ = "plugins:read"
	PLUGINS_MANAGE = "plugins:manage"

	# prompts
	PROMPTS_READ = "prompts:read"
	PROMPTS_MANAGE = "prompts:manage"


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


# ---------------------------------------------------------------------------
# access-level rank helper
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# default resource access — typed model, one field per resource type
# ---------------------------------------------------------------------------


class DefaultResourceAccess(BaseModel):
	"""
	per-resource-type access level defaults.

	``None`` means "no default for this resource type" — inherits
	from the global settings when used on a role, or means "no
	access" when used on the global settings themselves.
	"""

	model_config = ConfigDict(extra="forbid")

	thread: AccessLevel | None = None
	project: AccessLevel | None = None
	agent: AccessLevel | None = None
	note: AccessLevel | None = None
	memory: AccessLevel | None = None
	task: AccessLevel | None = None
	file: AccessLevel | None = None
	plugin: AccessLevel | None = None
	prompt: AccessLevel | None = None

	def get(self, resource_type: ResourceType) -> AccessLevel | None:
		"""look up the access level for a resource type."""
		return getattr(self, resource_type.value)

	def merge(self, other: DefaultResourceAccess) -> DefaultResourceAccess:
		"""merge two access models, keeping the higher level for each."""
		return DefaultResourceAccess(
			**{
				rt.value: higher_access(self.get(rt), other.get(rt))
				for rt in ResourceType
			}
		)


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
