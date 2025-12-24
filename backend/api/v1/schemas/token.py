from pydantic import BaseModel

from nokodo_ai.utils.typeid import TypeID


class Token(BaseModel):
	access_token: str
	token_type: str


class TokenPayload(BaseModel):
	sub: TypeID | None = None
