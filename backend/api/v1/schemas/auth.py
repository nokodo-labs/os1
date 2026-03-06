"""authentication schemas."""

from pydantic import BaseModel, Field

from nokodo_ai.utils.typeid import TypeID


class Token(BaseModel):
	access_token: str
	token_type: str
	refresh_token: str | None = None


class TokenPayload(BaseModel):
	sub: TypeID | None = None


class PasswordChange(BaseModel):
	"""payload for self-service password change."""

	current_password: str = Field(..., min_length=1)
	new_password: str = Field(..., min_length=8)
