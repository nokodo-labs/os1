"""boot-time settings.

these settings are loaded from env + .env only and are intended for values that
require a server restart to take effect.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class BootSettings(BaseSettings):
	model_config = SettingsConfigDict(
		env_file=".env",
		env_file_encoding="utf-8",
		case_sensitive=True,
		extra="ignore",
	)

	ENV: Literal["dev", "production"] = Field(
		default="production",
		description="runtime environment profile",
	)
	DEBUG: bool = False
	JSON_LOGS: bool = False
	TESTING: bool = False

	BRANCHING_MIGRATIONS: bool = Field(
		default=False,
		description="enable branching migrations support (alembic>=1.10) "
		"via `heads` command instead of `head` on startup migrations.",
	)

	@field_validator(
		"DEBUG", "JSON_LOGS", "TESTING", "BRANCHING_MIGRATIONS", mode="before"
	)
	@classmethod
	def coerce_bool(cls, v: object) -> bool:
		if isinstance(v, bool):
			return v
		if isinstance(v, str):
			return v.lower() in {"1", "true", "yes", "on"}
		return bool(v)

	DATABASE_URL: str = (
		"postgresql+psycopg://nokodo-ai-admin:nokodo-ai@127.0.0.1:5432/nokodo-ai-dev"
	)

	@field_validator("DATABASE_URL")
	@classmethod
	def validate_database_url(cls, v: str) -> str:
		"""ensure supported db url schemes only."""
		allowed = {"postgresql", "postgresql+psycopg"}
		scheme = v.split(":", 1)[0]
		if scheme not in allowed:
			raise ValueError(f"unsupported DATABASE_URL scheme: {scheme}")
		return v

boot_settings = BootSettings()
