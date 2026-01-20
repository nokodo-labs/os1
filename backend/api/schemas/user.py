"""user schemas."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from nokodo_ai.utils.typeid import TypeID


class UserBase(BaseModel):
	"""base user schema."""

	email: EmailStr
	display_name: str | None = None
	avatar_url: str | None = None
	is_active: bool = True
	is_superuser: bool = False
	preferences: dict[str, Any] = Field(default_factory=dict)
	integration_tokens: dict[str, Any] = Field(default_factory=dict)
	usage_quotas: dict[str, Any] = Field(default_factory=dict)


class UserCreate(BaseModel):
	"""schema for creating a user.

	note: is_active and is_superuser are optional.
	the server decides final values:
	- bootstrap (first user): may be superuser only if explicitly requested
	- unauthenticated: regular user only (is_active=True, is_superuser=False)
	- authenticated superuser: can set privileges
	"""

	email: EmailStr
	password: str
	display_name: str | None = None
	is_active: bool | None = None
	is_superuser: bool | None = None


class UserUpdate(BaseModel):
	"""schema for updating a user."""

	email: EmailStr | None = None
	password: str | None = None
	is_active: bool | None = None
	display_name: str | None = None
	avatar_url: str | None = None
	preferences: dict[str, Any] | None = None
	integration_tokens: dict[str, Any] | None = None
	usage_quotas: dict[str, Any] | None = None


class User(UserBase):
	"""schema for user response."""

	model_config = ConfigDict(from_attributes=True)

	id: TypeID
	role_id: TypeID | None = None
	created_at: datetime
	updated_at: datetime
