"""user session schemas."""

from datetime import datetime

from api.schemas.common import TimestampedModel
from nokodo_ai.utils.typeid import TypeID


class UserSession(TimestampedModel):
	"""server-side login session response."""

	id: TypeID
	user_id: TypeID
	client_id: TypeID | None = None
	rotated_at: datetime | None = None
	last_used_at: datetime | None = None
	expires_at: datetime
	revoked_at: datetime | None = None
	user_agent: str | None = None
	is_active: bool
