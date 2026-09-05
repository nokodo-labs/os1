"""user block schemas."""

from api.schemas.common import ForbidExtraModel, TimestampedModel
from api.schemas.user import User as UserSchema
from nokodo_ai.utils.typeid import TypeID


class BlockCreate(ForbidExtraModel):
	"""payload to block another user."""

	blocked_id: TypeID


class BlockDetail(TimestampedModel):
	"""user block with expanded user info."""

	id: TypeID
	blocker_id: TypeID
	blocked_id: TypeID
	blocker: UserSchema | None = None
	blocked: UserSchema | None = None
