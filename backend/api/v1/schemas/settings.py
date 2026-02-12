"""settings API schemas.

reads return the full Settings schema.

updates accept a patch schema where all fields are optional and only writable
fields are included.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from api.permissions import (
	ActionPermission,
	DefaultResourceAccess,
)
from api.schemas.preferences import BackgroundType
from api.settings import Settings


class UISettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	default_theme: str | None = Field(
		default=None,
		description="'light', 'dark', or 'system'",
	)
	default_background: BackgroundType | None = Field(
		default=None,
		description="default background for the app",
	)
	auth_pages_background: BackgroundType | None = Field(
		default=None,
		description="background for auth pages (login, signup)",
	)
	sidebar_collapsed: bool | None = Field(default=None, description="collapse sidebar")


class FeaturesSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	enable_file_uploads: bool | None = Field(
		default=None,
		description="enable file uploads",
	)


class AssetsSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	default_embedding_model_id: str | None = Field(
		default=None,
		description="default embedding model id (Model.id)",
	)
	qdrant_url: str | None = Field(
		default=None,
		description="qdrant url or ':memory:' for in-process testing",
	)


class BrandingSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	site_name: str | None = Field(default=None, description="site name")
	logo_url: str | None = Field(default=None, description="logo url")
	favicon_url: str | None = Field(default=None, description="favicon url")
	primary_color: str | None = Field(default=None, description="primary color hex")
	public_frontend_origin: str | None = Field(
		default=None,
		description="public frontend origin",
	)
	public_cdn_origin: str | None = Field(
		default=None,
		description="public cdn origin",
	)
	public_console_origin: str | None = Field(
		default=None,
		description="public console origin",
	)
	pwa_manifest_url: str | None = Field(
		default=None,
		description="external pwa manifest.json url",
	)


class LimitsSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	max_threads_per_user: int | None = Field(
		default=None,
		ge=1,
		description="max threads per user",
	)
	max_messages_per_thread: int | None = Field(
		default=None,
		ge=1,
		description="max messages per thread",
	)
	max_file_size_mb: int | None = Field(
		default=None,
		ge=1,
		description="max file size mb",
	)
	rate_limit_requests_per_minute: int | None = Field(
		default=None,
		ge=1,
		description="rate limit/min",
	)


class OIDCSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	enabled: bool | None = Field(
		default=None,
		description="enable oidc authentication",
	)
	issuer_url: str | None = Field(
		default=None,
		description="oidc issuer url",
	)
	client_id: str | None = Field(
		default=None,
		description="oidc client id",
	)
	client_secret: str | None = Field(
		default=None,
		description="oidc client secret",
	)
	redirect_uri: str | None = Field(
		default=None,
		description="oidc redirect uri",
	)
	scopes: list[str] | None = Field(
		default=None,
		description="oidc scopes",
	)
	only: bool | None = Field(
		default=None,
		description="only allow login via oidc",
	)


class SecuritySettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	allow_signups: bool | None = Field(
		default=None,
		description="allow new user signups",
	)
	auto_signup_role_ids: list[str] | None = Field(
		default=None,
		description="role ids auto-applied to new signups",
	)
	access_token_expire_minutes: int | None = Field(
		default=None,
		ge=1,
		description="access token expire minutes",
	)
	refresh_token_expire_days: int | None = Field(
		default=None,
		ge=1,
		description="refresh token expire days",
	)
	auth_cookie_secure: bool | None = Field(
		default=None,
		description="set secure cookies",
	)
	session_timeout_minutes: int | None = Field(
		default=None,
		ge=5,
		description="session timeout",
	)
	require_email_verification: bool | None = Field(
		default=None,
		description="require email verification",
	)
	allowed_email_domains: list[str] | None = Field(
		default=None,
		description="allowed domains",
	)
	oidc: OIDCSettingsPatch | None = None


class AIMemorySettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	enable_memory: bool | None = Field(default=None, description="enable memory")
	similarity_threshold: float | None = Field(
		default=None,
		ge=0.0,
		le=1.0,
		description="similarity minimum threshold for memory retrieval",
	)
	top_k: int | None = Field(
		default=None,
		ge=1,
		description="number of relevant memories to retrieve",
	)
	messages_to_consider: int | None = Field(
		default=None,
		ge=1,
		description="number of recent messages to consider",
	)


class AIChatContextSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	mode: str | None = Field(
		default=None,
		description="how chats are selected for Agent context enrichment",
	)
	top_k: int | None = Field(
		default=None,
		ge=1,
		description="number of chats to use for context enrichment",
	)


class AISettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	default_agent_id: str | None = Field(default=None, description="default agent id")
	memory: AIMemorySettingsPatch | None = None
	chat_context: AIChatContextSettingsPatch | None = None


class DefaultPermissionsSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	resource_access: DefaultResourceAccess | None = Field(
		default=None,
		description="per-resource-type default access levels",
	)
	action_permissions: list[ActionPermission] | None = Field(
		default=None,
		description="action permissions granted by default",
	)


class SoftDeleteSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	threads: bool | None = Field(default=None, description="soft-delete threads")
	notes: bool | None = Field(default=None, description="soft-delete notes")
	files: bool | None = Field(default=None, description="soft-delete files")


class SettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	ui: UISettingsPatch | None = None
	features: FeaturesSettingsPatch | None = None
	ai: AISettingsPatch | None = None
	branding: BrandingSettingsPatch | None = None
	assets: AssetsSettingsPatch | None = None
	limits: LimitsSettingsPatch | None = None
	security: SecuritySettingsPatch | None = None
	soft_delete: SoftDeleteSettingsPatch | None = None
	default_permissions: DefaultPermissionsSettingsPatch | None = None


class SettingsVersions(BaseModel):
	model_config = ConfigDict(extra="forbid")

	ui: int = 0
	features: int = 0
	ai: int = 0
	branding: int = 0
	assets: int = 0
	limits: int = 0
	security: int = 0
	soft_delete: int = 0
	default_permissions: int = 0


class SettingsUpdateRequest(BaseModel):
	model_config = ConfigDict(extra="forbid")

	data: SettingsPatch
	expected_versions: SettingsVersions | None = None


class SettingsResponse(BaseModel):
	model_config = ConfigDict(extra="forbid")

	versions: SettingsVersions
	data: Settings
