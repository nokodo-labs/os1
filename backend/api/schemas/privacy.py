"""user privacy schemas.

privacy = access control for who can see/interact with a user.
this is separate from preferences (which are UI/UX settings).
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class Visibility(StrEnum):
	"""who can see a given piece of user data."""

	EVERYONE = "everyone"
	FRIENDS = "friends"
	PRIVATE = "private"


class UserPrivacy(BaseModel):
	"""privacy settings stored in the user.privacy JSONB column.

	validated at the service layer - the column stores jsonb and
	the service ensures conformance via this schema.
	"""

	online_status: Visibility = Field(default=Visibility.FRIENDS)
	profile_picture: Visibility = Field(default=Visibility.EVERYONE)
	real_name: Visibility = Field(default=Visibility.EVERYONE)
	bio: Visibility = Field(default=Visibility.EVERYONE)
	gender: Visibility = Field(default=Visibility.FRIENDS)
	birth_date: Visibility = Field(default=Visibility.FRIENDS)
	allow_dms: Visibility = Field(default=Visibility.FRIENDS)
	allow_friend_requests: Visibility = Field(default=Visibility.EVERYONE)
