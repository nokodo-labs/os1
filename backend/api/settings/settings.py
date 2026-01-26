"""application settings models and singleton."""

from __future__ import annotations

from functools import cache
from typing import Any, Final, Literal, Self

from pydantic import BaseModel, Field, HttpUrl, field_validator
from pydantic_settings import (
	BaseSettings,
	PydanticBaseSettingsSource,
	SettingsConfigDict,
)

from nokodo_ai.utils.typing import extract_literal_values


FieldFlag = Literal["private", "write_locked"]


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
		return Field(default_factory=default_factory, **field_kwargs)
	return Field(default, **field_kwargs)


def get_field_flags(schema: type[BaseModel], field_name: str) -> dict[FieldFlag, bool]:
	"""get access flags for a field."""
	info = schema.model_fields.get(field_name)
	if not info:
		return {}
	extra = info.json_schema_extra
	if not extra:
		return {}
	return {
		flag: bool(extra.get(flag))
		for flag in extract_literal_values(FieldFlag)
		if extra.get(flag)
	}


# ---------------------------------------------------------------------------
# section models
# ---------------------------------------------------------------------------


class UISettings(BaseModel):
	default_theme: str = Field(
		default="system", description="'light', 'dark', or 'system'"
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


class AISettings(BaseModel):
	default_agent_id: str | None = Field(default=None, description="default agent id")
	memory: AIMemorySettings = Field(
		default_factory=AIMemorySettings, description="AI memory settings"
	)
	chat_context: AIChatContextSettings = Field(
		default_factory=AIChatContextSettings, description="chat context settings"
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


class AssetsSettings(BaseModel):
	default_embedding_model_id: str | None = Field(
		default=None,
		description="default embedding model id (Model.id)",
	)
	qdrant_url: str = Field(
		default="http://localhost:6333",
		description="qdrant url or ':memory:' for in-process testing",
	)


class SecuritySettings(BaseModel):
	secret_key: str = settings_field(
		default="changeme",
		private=True,
		write_locked=True,
		description="application secret key (env-only)",
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


# ---------------------------------------------------------------------------
# root settings
# ---------------------------------------------------------------------------


class Settings(BaseSettings):
	model_config = SettingsConfigDict(
		case_sensitive=False,
		env_prefix=ENV_PREFIX,
		env_nested_delimiter=ENV_NESTED_DELIMITER,
		validate_assignment=True,
		extra="ignore",
	)
	ui: UISettings = Field(default_factory=UISettings)
	features: FeaturesSettings = Field(default_factory=FeaturesSettings)
	ai: AISettings = Field(default_factory=AISettings)
	branding: BrandingSettings = Field(default_factory=BrandingSettings)
	assets: AssetsSettings = Field(default_factory=AssetsSettings)
	limits: LimitsSettings = Field(default_factory=LimitsSettings)
	security: SecuritySettings = Field(default_factory=SecuritySettings)

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
		self.__dict__.update(new.__dict__)
		self.__pydantic_fields_set__ = new.__pydantic_fields_set__
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
