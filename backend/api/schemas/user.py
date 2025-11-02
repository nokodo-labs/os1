"""User schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr


class UserBase(BaseModel):
	"""Base user schema."""

	email: EmailStr
	username: str
	is_active: bool = True
	is_superuser: bool = False


class UserCreate(UserBase):
	"""Schema for creating a user."""

	password: str


class UserUpdate(BaseModel):
	"""Schema for updating a user."""

	email: EmailStr | None = None
	username: str | None = None
	password: str | None = None
	is_active: bool | None = None


class User(UserBase):
	"""Schema for user response."""

	model_config = ConfigDict(from_attributes=True)

	id: int
	created_at: datetime
	updated_at: datetime
