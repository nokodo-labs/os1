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

	# API
	SECRET_KEY: str = "changeme"
	ALGORITHM: str = "HS256"
	ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

	# Database
	# Provide a safe default for dev/CI; env can override to Postgres in real deployment
	DATABASE_URL: str = "sqlite+aiosqlite:///./app.db"

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
		allowed = {"postgresql", "postgresql+psycopg", "sqlite+aiosqlite"}
		scheme = v.split(":", 1)[0]
		if scheme not in allowed:
			raise ValueError(f"Unsupported DATABASE_URL scheme: {scheme}")
		return v


settings = Settings()
