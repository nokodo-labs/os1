"""permission type definitions — canonical source of truth.

enums and the DefaultPermissions model live here so both
``api.models`` and ``api.settings`` can import them without
introducing a cross-layer dependency.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


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


class DefaultPermissions(BaseModel):
	"""
	default permissions model for both global settings and
	role-scoped defaults.

	resource_access: maps resource type → minimum access level
		granted by default.
	action_permissions: set of action permissions granted by
		default.
	"""

	resource_access: dict[ResourceType, AccessLevel] = Field(
		default_factory=dict,
	)
	action_permissions: set[ActionPermission] = Field(
		default_factory=set,
	)
