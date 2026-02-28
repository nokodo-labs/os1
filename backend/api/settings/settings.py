"""application settings models and singleton."""

from __future__ import annotations

import logging
from enum import StrEnum
from functools import cache
from typing import Any, Final, Literal, Self, cast

from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator
from pydantic_settings import (
	BaseSettings,
	PydanticBaseSettingsSource,
	SettingsConfigDict,
)

from api.permissions import (
	ActionPermission,
	DefaultResourceAccess,
	strip_unknown_action_permissions,
)
from api.schemas.preferences import BackgroundType
from nokodo_ai.utils.typing import extract_literal_values


FieldFlag = Literal["private", "write_locked"]


_settings_logger = logging.getLogger(__name__)

ENV_PREFIX: Final[str] = "NOKODO__"
ENV_NESTED_DELIMITER: Final[str] = "__"


def settings_field[T](
	default: T,
	*,
	description: str | None = None,
	default_factory: Any = None,
	private: bool = False,
	write_locked: bool = False,
	**kwargs: Any,
) -> T:
	"""field with access flags.
	args:
		private: if True, excluded from non-admin API responses
		write_locked: if True, cannot be updated via API (env-only)
	"""
	extra = kwargs.pop("json_schema_extra", {}) or {}
	if private:
		extra["private"] = True
	if write_locked:
		extra["write_locked"] = True
	field_kwargs = dict(
		description=description,
		json_schema_extra=extra or None,
		frozen=write_locked,
		**kwargs,
	)
	if default_factory is not None:
		return cast(T, Field(default_factory=default_factory, **field_kwargs))
	return cast(T, Field(default, **field_kwargs))


def get_field_flags(schema: type[BaseModel], field_name: str) -> dict[FieldFlag, bool]:
	"""get access flags for a field."""
	info = schema.model_fields.get(field_name)
	if not info:
		return {}
	extra = info.json_schema_extra
	if not extra:
		return {}
	if callable(extra):
		return {}
	return {
		flag: bool(extra.get(flag))
		for flag in extract_literal_values(FieldFlag)
		if extra.get(flag)
	}


# section models


class UISettings(BaseModel):
	default_theme: str = Field(
		default="system", description="'light', 'dark', or 'system'"
	)
	default_background: BackgroundType = Field(
		default="darkveil",
		description="default background for the app",
	)
	auth_pages_background: BackgroundType = Field(
		default="lightrays",
		description="background for auth pages (login, signup)",
	)
	sidebar_collapsed: bool = Field(default=False, description="collapse sidebar")


class FeaturesSettings(BaseModel):
	enable_file_uploads: bool = Field(default=True, description="enable file uploads")


class AIMemorySettings(BaseModel):
	enable_memory: bool = Field(default=True, description="enable memory")
	similarity_threshold: float = Field(
		default=0.65,
		ge=0.0,
		le=1.0,
		description="similarity minimum threshold for memory retrieval. "
		"how similar a memory must be to be considered relevant. "
		"0.0 = all memories, 1.0 = exact match",
	)
	top_k: int = Field(
		default=15,
		ge=1,
		description="number of relevant memories to retrieve",
	)
	messages_to_consider: int = Field(
		default=4,
		ge=1,
		description="number of recent messages to consider when retrieving "
		"relevant memories for the agent and for consolidation work",
	)


class AIChatContextSettings(BaseModel):
	mode: Literal["recent", "relevant", "pinned"] = Field(
		default="recent",
		description="how chats are selected for Agent context enrichment",
	)
	top_k: int = Field(
		default=3,
		ge=1,
		description="number of chats to use for context enrichment",
	)


class AITaskSettings(BaseModel):
	"""per-task model overrides for background AI tasks.

	resolution order: per-task model_id → default_model_id → error.
	"""

	default_model_id: str | None = Field(
		default=None,
		description="fallback model id for all background tasks",
	)
	thread_metadata_model_id: str | None = Field(
		default=None,
		description="model for thread metadata generation (title, tags)",
	)
	input_autocomplete_model_id: str | None = Field(
		default=None,
		description="model for input autocomplete suggestions",
	)


class AISettings(BaseModel):
	default_agent_ids: list[str] = Field(
		default_factory=list,
		description="ordered list of default agent ids (tried in order)",
	)
	memory: AIMemorySettings = Field(
		default_factory=AIMemorySettings, description="AI memory settings"
	)
	chat_context: AIChatContextSettings = Field(
		default_factory=AIChatContextSettings, description="chat context settings"
	)
	tasks: AITaskSettings = Field(
		default_factory=AITaskSettings, description="background task model settings"
	)


class BrandingSettings(BaseModel):
	site_name: str = Field(default="nokodo", description="site name")
	app_version: str = settings_field(
		default="0.1.0",
		write_locked=True,
		description="backend version",
	)
	logo_url: HttpUrl | None = Field(default=None, description="logo url")
	favicon_url: HttpUrl | None = Field(default=None, description="favicon url")
	primary_color: str = Field(default="#6366f1", description="primary color hex")
	support_email: str | None = Field(
		default=None,
		description="support email shown to users awaiting approval",
	)
	admin_email: str | None = Field(
		default=None,
		description="admin email for internal / escalation contact",
	)
	public_frontend_origin: HttpUrl | None = Field(
		default=None,
		description="public frontend origin",
	)
	public_cdn_origin: HttpUrl | None = Field(
		default=None,
		description="public cdn origin",
	)
	public_console_origin: HttpUrl | None = Field(
		default=None,
		description="public admin console origin",
	)
	pwa_manifest_url: HttpUrl | None = Field(
		default=None,
		description="external pwa manifest.json url",
	)
	analytics_key: str | None = settings_field(
		default=None,
		private=True,
		write_locked=True,
		description="analytics key (env-only)",
	)


class LimitsSettings(BaseModel):
	max_threads_per_user: int = Field(
		default=100, ge=1, description="max threads per user"
	)
	max_messages_per_thread: int = Field(
		default=1000, ge=1, description="max messages per thread"
	)
	max_file_size_mb: int = Field(default=50, ge=1, description="max file size mb")
	rate_limit_requests_per_minute: int = Field(
		default=60, ge=1, description="rate limit/min"
	)


class MediaSettings(BaseModel):
	"""external media / asset URLs.

	base_url provides a common prefix for well-known asset filenames.
	individual url fields override the base_url + filename convention.

	resolution order per asset: individual field > base_url/filename > null.

	well-known filenames (appended to base_url):
		favicon.ico, apple-touch-icon.png, sidebar-logo.svg, splash-logo.svg
	"""

	base_url: HttpUrl | None = Field(
		default=None,
		description="base url for all media assets",
		examples=[
			"https://cdn.example.com/brand/",
			"https://raw.githubusercontent.com/org/repo/branch/path/to/assets/",
		],
	)
	favicon_url: HttpUrl | None = Field(
		default=None,
		description="favicon url override",
	)
	apple_touch_icon_url: HttpUrl | None = Field(
		default=None,
		description="apple touch icon url override",
	)
	sidebar_logo_url: HttpUrl | None = Field(
		default=None,
		description="sidebar banner logo url override",
	)
	splash_logo_url: HttpUrl | None = Field(
		default=None,
		description="splash screen logo url override",
	)


class VectorSettings(BaseModel):
	"""vector database collection and search tuning."""

	collection_template: str = Field(
		default="{model}_bm25",
		description="collection name template. '{model}' is replaced with "
		"the slugified embedding model name at runtime",
	)
	sparse_vectors_enabled: bool = Field(
		default=True,
		description="enable BM25 sparse vectors for hybrid search",
	)
	prefetch_limit: int = Field(
		default=100,
		ge=1,
		le=10000,
		description="how many candidates to prefetch before fusion/reranking",
	)
	fusion_algorithm: Literal["rrf", "dbsf"] = Field(
		default="rrf",
		description="score fusion algorithm: rrf (reciprocal rank fusion) or "
		"dbsf (distribution-based score fusion)",
	)
	normalize_scores: bool = Field(
		default=True,
		description="normalize fused scores to 0-1 range",
	)


class EmbeddingsSettings(BaseModel):
	"""embedding model configuration."""

	vector_size: int = Field(
		default=1536,
		ge=1,
		description="default vector dimension for the embedding model",
	)
	batch_size: int = Field(
		default=64,
		ge=1,
		le=4096,
		description="batch size for embedding generation during vectorization",
	)


class RerankSettings(BaseModel):
	"""default reranking behavior."""

	default_strategy: str = Field(
		default="native",
		description="default reranking strategy: none, native, or external",
	)
	top_k: int = Field(
		default=10,
		ge=1,
		le=100,
		description="number of results to keep after reranking",
	)


class VectorDatabaseProvider(StrEnum):
	"""supported vector database providers."""

	QDRANT = "qdrant"
	PINECONE = "pinecone"
	WEAVIATE = "weaviate"
	MILVUS = "milvus"
	PGVECTOR = "pgvector"
	REDIS = "redis"
	OPENSEARCH = "opensearch"


class VectorDatabaseApiKeys(BaseModel):
	"""provider-specific credentials for vector databases."""

	qdrant_api_key: str | None = settings_field(
		default=None,
		private=True,
		description="api key for qdrant",
	)
	pinecone_api_key: str | None = settings_field(
		default=None,
		private=True,
		description="api key for pinecone",
	)
	weaviate_api_key: str | None = settings_field(
		default=None,
		private=True,
		description="api key for weaviate",
	)
	milvus_token: str | None = settings_field(
		default=None,
		private=True,
		description="token for milvus",
	)
	redis_password: str | None = settings_field(
		default=None,
		private=True,
		description="password for redis",
	)
	opensearch_api_key: str | None = settings_field(
		default=None,
		private=True,
		description="api key for opensearch",
	)


class VectorDatabaseSettings(BaseModel):
	"""vector database connection settings."""

	provider: VectorDatabaseProvider = Field(
		default=VectorDatabaseProvider.QDRANT,
		description="vector database provider",
	)
	url: str = Field(
		default="http://localhost:6333",
		description="vector database endpoint url or local mode location",
	)
	api_keys: VectorDatabaseApiKeys = Field(
		default_factory=VectorDatabaseApiKeys,
		description="provider-specific api key and token settings",
	)


class LocalStorageConfig(BaseModel):
	"""local filesystem storage configuration."""

	root_path: str = Field(
		default="data/uploads",
		description="root directory for local file storage",
	)


class S3StorageConfig(BaseModel):
	"""S3-compatible storage configuration."""

	endpoint_url: str | None = Field(
		default=None,
		description="S3-compatible endpoint (MinIO, R2, etc.)",
	)
	bucket: str = Field(
		default="nokodo-ai",
		description=("S3 bucket name. must be globally unique per deployment."),
	)
	region: str = Field(default="us-east-1", description="AWS region")
	access_key_id: str | None = settings_field(
		default=None, private=True, description="S3 access key id"
	)
	secret_access_key: str | None = settings_field(
		default=None, private=True, description="S3 secret access key"
	)
	prefix: str = Field(default="", description="key prefix within the bucket")
	presigned_url_ttl: int = Field(
		default=3600, description="presigned URL expiration in seconds"
	)
	multipart_threshold: int = Field(
		default=100 * 1024 * 1024,
		description="bytes above which multipart upload kicks in",
	)
	multipart_chunk_size: int = Field(
		default=10 * 1024 * 1024,
		description="multipart upload chunk size in bytes",
	)
	max_retries: int = Field(default=3, description="max retry attempts")
	retry_mode: Literal["legacy", "standard", "adaptive"] = Field(
		default="adaptive", description="botocore retry mode"
	)


class StorageSettings(BaseModel):
	"""file storage backend configuration.

	set `backend` to choose which storage system is active.
	only the selected backend is instantiated at startup.
	"""

	backend: Literal["local", "s3"] = Field(
		default="local",
		description="active storage backend: 'local' or 's3'",
	)
	local: LocalStorageConfig = Field(default_factory=LocalStorageConfig)
	s3: S3StorageConfig = Field(default_factory=S3StorageConfig)


class AssetsSettings(BaseModel):
	default_embedding_model_id: str | None = Field(
		default=None,
		description="default embedding model id (Model.id)",
	)
	vector_database: VectorDatabaseSettings = Field(
		default_factory=VectorDatabaseSettings,
		description="vector database provider and connection settings",
	)
	vector: VectorSettings = Field(
		default_factory=VectorSettings,
		description="vector database collection and search tuning",
	)
	embeddings: EmbeddingsSettings = Field(
		default_factory=EmbeddingsSettings,
		description="embedding model configuration",
	)
	rerank: RerankSettings = Field(
		default_factory=RerankSettings,
		description="default reranking behavior",
	)
	storage: StorageSettings = Field(
		default_factory=StorageSettings,
		description="file storage backend configuration",
	)


class OIDCSettings(BaseModel):
	"""openid connect provider configuration."""

	enabled: bool = Field(default=False, description="enable oidc authentication")
	issuer_url: HttpUrl | None = Field(
		default=None,
		description="oidc issuer url",
	)
	client_id: str | None = Field(
		default=None,
		description="oidc client id",
	)
	client_secret: str | None = settings_field(
		default=None,
		private=True,
		description="oidc client secret",
	)
	redirect_uri: HttpUrl | None = Field(
		default=None,
		description="oidc redirect uri",
	)
	scopes: list[str] = Field(
		default_factory=lambda: ["openid", "profile", "email"],
		description="oidc scopes",
	)
	only: bool = Field(
		default=False,
		description="only allow login via oidc (disables password login)",
	)

	def is_configured(self) -> bool:
		"""check whether all required oidc fields are set."""
		return bool(
			self.issuer_url
			and self.client_id
			and self.client_secret
			and self.redirect_uri
		)

	@model_validator(mode="after")
	def validate_oidc_flags(self) -> OIDCSettings:
		if self.only and not self.enabled:
			raise ValueError("oidc.only requires oidc.enabled")
		if self.only and not self.is_configured():
			raise ValueError("oidc.only requires oidc provider configuration")
		if self.enabled and not self.is_configured():
			raise ValueError(
				"oidc.enabled requires issuer_url, client_id, client_secret, "
				"and redirect_uri"
			)
		return self


class SecuritySettings(BaseModel):
	secret_key: str = settings_field(
		default="changeme",
		private=True,
		write_locked=True,
		description="application secret key (env-only)",
	)
	allow_signups: bool = Field(
		default=True,
		description="allow new user signups",
	)
	auto_signup_role_ids: list[str] | None = Field(
		default=None,
		description="role ids auto-applied to new signups",
	)
	jwt_algorithm: str = settings_field(
		default="HS256",
		write_locked=True,
		description="jwt algorithm",
	)
	access_token_expire_minutes: int = Field(
		default=30,
		ge=1,
		description="access token expire minutes",
	)
	refresh_token_expire_days: int = Field(
		default=90,
		ge=1,
		description="refresh token expire days",
	)
	auth_cookie_secure: bool = Field(
		default=True,
		description="set secure cookies",
	)
	session_timeout_minutes: int = Field(
		default=30, ge=5, description="session timeout"
	)
	require_email_verification: bool = Field(
		default=True, description="require email verification"
	)
	allowed_email_domains: list[str] = Field(
		default_factory=list, description="allowed domains"
	)
	oidc: OIDCSettings = Field(
		default_factory=OIDCSettings,
		description="openid connect provider settings",
	)
	enable_oauth: bool = settings_field(
		default=True,
		write_locked=True,
		description="enable oauth (env-only)",
	)
	cors_origins: list[str] = settings_field(
		default=[
			"http://localhost:888",
			"http://localhost:8383",
		],
		write_locked=True,
		description="cors origins (env-only)",
	)
	cors_origins_regex: list[str] = settings_field(
		default=[r"^https?://.*\.local:888$", r"^https?://.*\.local:8383$"],
		write_locked=True,
		description="cors origins regex patterns (env-only). set as JSON array object.",
	)
	allowed_hosts: list[str] = settings_field(
		default=[
			"localhost",
			"0.0.0.0",
			"127.0.0.1",
			".local",
		],
		write_locked=True,
		description=(
			"allowed host patterns for Origin validation (env-only). "
			"supports '*', leading-dot domains like '.local', and exact hostnames"
		),
	)

	@field_validator("cors_origins", "allowed_hosts", mode="before")
	@classmethod
	def parse_comma_separated_strings(cls, v: str | list[str]) -> list[str]:
		if isinstance(v, str):
			return [item.strip() for item in v.split(",") if item.strip()]
		return v


# soft-delete section


class SoftDeleteSettings(BaseModel):
	"""per-resource soft-delete toggles.

	when enabled, deleting a resource sets its deleted_at timestamp
	instead of removing the row from the database.
	"""

	threads: bool = Field(default=True, description="soft-delete threads")
	notes: bool = Field(default=True, description="soft-delete notes")
	files: bool = Field(default=True, description="soft-delete files")


# default permissions section


class DefaultPermissionsSettings(BaseModel):
	"""global default permissions applied when no role or
	explicit rule grants access."""

	resource_access: DefaultResourceAccess = Field(
		default_factory=DefaultResourceAccess,
		description="per-resource-type default access levels",
	)
	action_permissions: list[ActionPermission] = Field(
		default_factory=lambda: [
			ActionPermission.SETTINGS_READ,
			ActionPermission.THREADS_CREATE,
			ActionPermission.PROJECTS_CREATE,
			ActionPermission.NOTES_CREATE,
			ActionPermission.GROUPS_CREATE,
			ActionPermission.REMINDERS_CREATE,
			ActionPermission.MEMORIES_CREATE,
			ActionPermission.TASKS_CREATE,
			ActionPermission.FILES_CREATE,
		],
		description="action permissions granted by default",
	)

	@field_validator("action_permissions", mode="before")
	@classmethod
	def _strip_unknown(cls, v: object) -> object:
		return strip_unknown_action_permissions(v)


# root settings


class Settings(BaseSettings):
	model_config = SettingsConfigDict(
		case_sensitive=False,
		env_file=".env",
		env_prefix=ENV_PREFIX,
		env_nested_delimiter=ENV_NESTED_DELIMITER,
		validate_assignment=True,
		extra="ignore",
	)
	ui: UISettings = Field(default_factory=UISettings)
	features: FeaturesSettings = Field(default_factory=FeaturesSettings)
	ai: AISettings = Field(default_factory=AISettings)
	branding: BrandingSettings = Field(default_factory=BrandingSettings)
	media: MediaSettings = Field(default_factory=MediaSettings)
	assets: AssetsSettings = Field(default_factory=AssetsSettings)
	limits: LimitsSettings = Field(default_factory=LimitsSettings)
	security: SecuritySettings = Field(default_factory=SecuritySettings)
	soft_delete: SoftDeleteSettings = Field(default_factory=SoftDeleteSettings)
	default_permissions: DefaultPermissionsSettings = Field(
		default_factory=DefaultPermissionsSettings
	)

	@staticmethod
	@cache
	def _build_custom_exclude(
		schema: type[BaseModel], exclude_flags: tuple[FieldFlag, ...]
	) -> dict[str, Any]:
		"""build model_dump exclude dict based on field flags."""
		exclude: dict[str, Any] = {}
		for field_name, field_info in schema.model_fields.items():
			flags = get_field_flags(schema, field_name)
			if any(flags.get(flag) for flag in exclude_flags):
				exclude[field_name] = True
				continue
			annotation = field_info.annotation

			if isinstance(annotation, type) and issubclass(annotation, BaseModel):
				nested_exclude = Settings._build_custom_exclude(
					annotation, exclude_flags
				)
				if nested_exclude:
					exclude[field_name] = nested_exclude
		return exclude

	def custom_dump(self, exclude_private: bool = False) -> dict[str, Any]:
		"""model_dump with custom excludes."""
		exclude = {}
		if exclude_private:
			exclude.update(
				self._build_custom_exclude(
					schema=type(self), exclude_flags=("private",)
				)
			)

		return self.model_dump(exclude=exclude or None)

	def reload(self) -> Self:
		"""reload settings from all sources."""
		new = Settings()
		vars(self).update(vars(new))
		self.__pydantic_fields_set__ = set(new.__pydantic_fields_set__)
		return self

	@classmethod
	def settings_customise_sources(
		cls,
		settings_cls: type[BaseSettings],
		init_settings: PydanticBaseSettingsSource,
		env_settings: PydanticBaseSettingsSource,
		dotenv_settings: PydanticBaseSettingsSource,
		file_secret_settings: PydanticBaseSettingsSource,
	) -> tuple[PydanticBaseSettingsSource, ...]:
		from api.settings.database import DbSettingsSource

		return (
			init_settings,
			DbSettingsSource(settings_cls),
			env_settings,
			dotenv_settings,
			file_secret_settings,
		)


settings: Settings = Settings()


# public helpers


def check_writable(
	schema: type[BaseModel],
	fields: dict[str, Any],
	prefix: str,
) -> None:
	"""recursively validate that no write_locked fields are being changed.

	raises ValueError for unknown or write_locked fields.
	"""
	for field_name, value in fields.items():
		if field_name not in schema.model_fields:
			raise ValueError(f"{prefix}: unknown field '{field_name}'")
		if get_field_flags(schema, field_name).get("write_locked", False):
			raise ValueError(f"{prefix}: field '{field_name}' is not writable")
		# recurse into nested BaseModel sub-sections
		if isinstance(value, dict):
			field_info = schema.model_fields[field_name]
			annotation = field_info.annotation
			if isinstance(annotation, type) and issubclass(annotation, BaseModel):
				check_writable(annotation, value, f"{prefix}.{field_name}")
