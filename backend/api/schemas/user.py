"""User schemas."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserBase(BaseModel):
	"""Base user schema."""

	email: EmailStr
	username: str
	display_name: str | None = None
	avatar_url: str | None = None
	is_active: bool = True
	is_superuser: bool = False
	preferences: dict[str, Any] = Field(default_factory=dict)
	integration_tokens: dict[str, Any] = Field(default_factory=dict)
	usage_quotas: dict[str, Any] = Field(default_factory=dict)


class UserCreate(UserBase):
	"""Schema for creating a user."""

	password: str


class UserUpdate(BaseModel):
	"""Schema for updating a user."""

	email: EmailStr | None = None
	username: str | None = None
	password: str | None = None
	is_active: bool | None = None
	display_name: str | None = None
	avatar_url: str | None = None
	preferences: dict[str, Any] | None = None
	integration_tokens: dict[str, Any] | None = None
	usage_quotas: dict[str, Any] | None = None


class User(UserBase):
	"""Schema for user response."""

	model_config = ConfigDict(from_attributes=True)

	id: int
	role_id: str | None = None
	created_at: datetime
	updated_at: datetime
