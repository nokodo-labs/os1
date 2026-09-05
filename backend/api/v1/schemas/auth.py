"""authentication schemas."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from api.models.user import User
from api.schemas.preferences import UserPreferences
from nokodo_ai.utils.typeid import TypeID


class Token(BaseModel):
	access_token: str
	token_type: str
	refresh_token: str | None = None


class TokenPayload(BaseModel):
	sub: TypeID | None = None


class UserSubject(BaseModel):
	"""identity snapshot of the user behind a principal."""

	model_config = ConfigDict(frozen=True)

	kind: Literal["user"] = "user"
	id: TypeID
	email: str
	username: str
	display_name: str | None = None
	is_active: bool = True
	is_superuser: bool = False
	preferences: dict[str, object] = Field(default_factory=dict)

	@classmethod
	def from_user(cls, user: User) -> UserSubject:
		"""snapshot the principal-relevant scalars off a flushed user row."""
		return cls(
			id=user.id,
			email=user.email,
			username=user.username,
			display_name=user.display_name,
			is_active=user.is_active,
			is_superuser=user.is_superuser,
			preferences=user.preferences or {},
		)

	@property
	def prefs(self) -> UserPreferences:
		"""parsed preferences as a typed schema."""
		try:
			return UserPreferences.model_validate(self.preferences or {})
		except ValidationError:
			return UserPreferences()
