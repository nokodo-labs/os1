"""friendship schemas."""

from __future__ import annotations

from datetime import datetime

from api.models.friendship import FriendshipStatus
from api.schemas.common import ORMModel, TimestampedModel
from api.schemas.user import User as UserSchema
from nokodo_ai.utils.typeid import TypeID


class FriendshipBase(ORMModel):
	requester_id: TypeID
	addressee_id: TypeID
	status: FriendshipStatus


class FriendshipResponse(FriendshipBase, TimestampedModel):
	id: TypeID
	accepted_at: datetime | None = None


class FriendshipDetail(FriendshipResponse):
	"""friendship with expanded user info for list endpoints."""

	requester: UserSchema | None = None
	addressee: UserSchema | None = None


class FriendRequestCreate(ORMModel):
	"""send a friend request to another user."""

	addressee_id: TypeID


class FriendResponse(ORMModel):
	"""a confirmed friend - simplified view for the friends list."""

	id: TypeID
	friendship_id: TypeID
	username: str | None = None
	display_name: str | None = None
	email: str | None = None
	avatar_url: str | None = None


class FriendshipEventResponse(TimestampedModel):
	"""a single entry in the friendship event history."""

	id: TypeID
	friendship_id: TypeID
	status: FriendshipStatus
	actor_id: TypeID


class UserSearchResult(ORMModel):
	"""user search result for the add-friends flow."""

	id: TypeID
	username: str | None = None
	display_name: str | None = None
	email: str | None = None
	avatar_url: str | None = None
