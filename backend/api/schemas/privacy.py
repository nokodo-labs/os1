"""user privacy schemas.

privacy = access control for who can see/interact with a user.
this is separate from preferences (which are UI/UX settings).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class Visibility(StrEnum):
	"""who can see a given piece of user data."""

	EVERYONE = "everyone"
	FRIENDS = "friends"
	PRIVATE = "private"


type PrivacyField = Literal[
	"online_status",
	"profile_picture",
	"real_name",
	"bio",
	"email",
	"gender",
	"birth_date",
	"allow_dms",
	"allow_friend_requests",
]


PRIVACY_FIELDS: tuple[PrivacyField, ...] = (
	"online_status",
	"profile_picture",
	"real_name",
	"bio",
	"email",
	"gender",
	"birth_date",
	"allow_dms",
	"allow_friend_requests",
)


class UserPrivacy(BaseModel):
	"""privacy settings stored in the user.privacy JSONB column.

	validated at the service layer - the column stores jsonb and
	the service ensures conformance via this schema.
	"""

	online_status: Visibility = Field(default=Visibility.FRIENDS)
	profile_picture: Visibility = Field(default=Visibility.EVERYONE)
	real_name: Visibility = Field(default=Visibility.FRIENDS)
	bio: Visibility = Field(default=Visibility.EVERYONE)
	email: Visibility = Field(default=Visibility.PRIVATE)
	gender: Visibility = Field(default=Visibility.FRIENDS)
	birth_date: Visibility = Field(default=Visibility.FRIENDS)
	allow_dms: Visibility = Field(default=Visibility.FRIENDS)
	allow_friend_requests: Visibility = Field(default=Visibility.EVERYONE)


def privacy_field_default(field: PrivacyField) -> Visibility:
	"""return the schema default for a privacy field."""
	default = UserPrivacy.model_fields[field].default
	if isinstance(default, Visibility):
		return default
	raise TypeError(f"privacy field {field} has no visibility default")
