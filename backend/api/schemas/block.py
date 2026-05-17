"""user block schemas."""

from __future__ import annotations

from api.schemas.common import ORMModel, TimestampedModel
from api.schemas.user import User as UserSchema
from nokodo_ai.utils.typeid import TypeID


class BlockCreate(ORMModel):
	"""payload to block another user."""

	blocked_id: TypeID


class BlockDetail(TimestampedModel):
	"""user block with expanded user info."""

	id: TypeID
	blocker_id: TypeID
	blocked_id: TypeID
	blocker: UserSchema | None = None
	blocked: UserSchema | None = None
