from pydantic import BaseModel

from api.schemas.typeid import TypeID


class Token(BaseModel):
	access_token: str
	token_type: str


class TokenPayload(BaseModel):
	sub: TypeID | None = None
