"""Application configuration."""

from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
	"""Application settings."""

	model_config = SettingsConfigDict(
		env_file=".env",
		env_file_encoding="utf-8",
		case_sensitive=True,
		extra="ignore",
	)

	# Application
	PROJECT_NAME: str = "nokodo AI"
	VERSION: str = "0.1.0"
	APP_ENV: Literal["dev", "staging", "production"] = "dev"
	DEBUG: bool = False
	JSON_LOGS: bool = False

	# API
	SECRET_KEY: str = "changeme"
	ALGORITHM: str = "HS256"
	ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
	REFRESH_TOKEN_EXPIRE_DAYS: int = 90
	AUTH_COOKIE_SECURE: bool = False

	# Public origins (runtime config for static frontends)
	# These are intentionally "public" (safe to expose to clients).
	PUBLIC_FRONTEND_ORIGIN: str | None = None
	PUBLIC_CDN_ORIGIN: str | None = None

	# Database (Postgres everywhere: dev, tests, prod)
	DATABASE_URL: str = (
		"postgresql+psycopg://nokodo-ai-admin:nokodo-ai@127.0.0.1:5432/nokodo-ai-dev"
	)

	# Testing
	TESTING: bool = False

	# CORS
	CORS_ORIGINS: list[str] = [
		"http://localhost:888",
		"http://localhost:8383",
		"http://localhost:3000",
	]

	@field_validator("CORS_ORIGINS", mode="before")
	@classmethod
	def parse_cors_origins(cls, v: str | list[str]) -> list[str]:
		"""Parse CORS origins from string or list."""
		if isinstance(v, str):
			return [origin.strip() for origin in v.split(",")]
		return v

	@field_validator("DATABASE_URL")
	@classmethod
	def validate_database_url(cls, v: str) -> str:
		"""Ensure supported DB URL schemes only."""
		allowed = {"postgresql", "postgresql+psycopg"}
		scheme = v.split(":", 1)[0]
		if scheme not in allowed:
			raise ValueError(f"Unsupported DATABASE_URL scheme: {scheme}")
		return v


settings = Settings()


def configure_psycopg_asyncio_event_loop_policy() -> None:
	"""configure the asyncio event loop policy for psycopg on windows.

	this is a compatibility shim for legacy imports.
	"""
	from api.core.runtime import (
		configure_psycopg_asyncio_event_loop_policy as _configure_psycopg_policy,
	)

	_configure_psycopg_policy()
