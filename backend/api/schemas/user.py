"""user schemas."""

import re
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

from api.schemas.common import MISSING, MissingType, ORMModel, TimestampedModel
from api.schemas.preferences import UserPreferences
from api.schemas.privacy import UserPrivacy
from api.schemas.sorting import CommonSortBy
from nokodo_ai.utils.typeid import TypeID


type UserSortBy = (
	CommonSortBy
	| Literal[
		"email",
		"display_name",
		"is_active",
		"is_superuser",
	]
)


_USERNAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._]{1,28}[a-zA-Z0-9]$")

Username = Annotated[
	str,
	Field(min_length=3, max_length=30, examples=["johndoe"]),
]


def _validate_username(v: str) -> str:
	"""3-30 chars, alphanumeric + periods + underscores.

	cannot start or end with a period/underscore, no consecutive periods.
	"""
	v = v.strip().lower()
	if not _USERNAME_RE.match(v):
		raise ValueError(
			"username must be 3-30 characters: letters, numbers, periods, "
			"or underscores. cannot start/end with a period or underscore"
		)
	if ".." in v:
		raise ValueError("username cannot contain consecutive periods")
	return v


class UserBase(BaseModel):
	"""base user schema."""

	email: EmailStr
	username: Username
	display_name: str | None = None
	bio: str | None = None
	avatar_url: str | None = None
	is_active: bool = True
	is_superuser: bool = False
	find_by_email: bool = True
	privacy: UserPrivacy = Field(default_factory=UserPrivacy)
	preferences: UserPreferences = Field(default_factory=UserPreferences)
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
	username: Username
	display_name: str | None = None
	is_active: bool | None = None
	is_superuser: bool | None = None

	@field_validator("username", mode="before")
	@classmethod
	def check_username(cls, v: str) -> str:
		return _validate_username(v)


class UserUpdate(BaseModel):
	"""schema for updating a user."""

	email: EmailStr | MissingType = MISSING
	password: str | MissingType = MISSING
	username: Username | MissingType = MISSING
	is_active: bool | MissingType = MISSING
	display_name: str | None | MissingType = MISSING
	bio: str | None | MissingType = Field(default=MISSING, max_length=500)
	avatar_url: str | None | MissingType = MISSING
	find_by_email: bool | MissingType = MISSING
	privacy: UserPrivacy | MissingType = MISSING
	preferences: UserPreferences | MissingType = MISSING
	integration_tokens: dict[str, Any] | MissingType = MISSING
	usage_quotas: dict[str, Any] | MissingType = MISSING
	role_ids: list[TypeID] | MissingType = MISSING

	@field_validator("username", mode="before")
	@classmethod
	def check_username(cls, v: str) -> str:
		return _validate_username(v)


class UserBulkLookupRequest(BaseModel):
	"""request visible user summaries by ID."""

	user_ids: list[TypeID] = Field(default_factory=list, max_length=100)


class UserSummary(ORMModel):
	"""minimal user identity for allowed lookup results."""

	id: TypeID
	username: str | None = None
	display_name: str | None = None
	avatar_url: str | None = None


class User(UserBase, TimestampedModel):
	"""schema for user response."""

	id: TypeID
	last_active_at: datetime | None = None
	is_online: bool = False


class UserPermissions(BaseModel):
	"""resolved permissions for a user."""

	permissions: list[str]
