"""python-side user privacy and redaction helpers."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from api.models.user import User
from api.schemas.privacy import PRIVACY_FIELDS, PrivacyField, UserPrivacy, Visibility
from api.v1.service.auth import Principal
from api.v1.service.social.friendship import accepted_friend_ids, are_friends
from nokodo_ai.utils.typeid import TypeID


@dataclass(frozen=True, slots=True)
class RedactedUser:
	"""privacy-redacted public user fields."""

	id: TypeID
	username: str | None
	display_name: str | None
	email: str | None
	avatar_url: str | None


def get_privacy(user: User) -> UserPrivacy:
	"""parse and validate the privacy JSONB column, falling back to defaults."""
	if user.privacy:
		return UserPrivacy.model_validate(user.privacy)
	return UserPrivacy()


def check_visibility(
	setting: Visibility,
	is_friend: bool,
	is_self: bool = False,
) -> bool:
	"""return True if the requester is allowed to see the field."""
	if is_self:
		return True
	if setting == Visibility.EVERYONE:
		return True
	if setting == Visibility.FRIENDS:
		return is_friend
	return False


async def visible_fields(
	target: User,
	requester_id: TypeID | str,
	session: AsyncSession,
	is_friend: bool | None = None,
) -> dict[PrivacyField, bool]:
	"""check all privacy settings for target relative to requester."""
	is_self = target.id == requester_id
	if is_self:
		return {field: True for field in PRIVACY_FIELDS}

	privacy = get_privacy(target)
	friend = is_friend
	if friend is None:
		friend = await are_friends(target.id, requester_id, session)

	privacy_values = privacy.model_dump()
	return {
		field: check_visibility(privacy_values[field], is_friend=friend)
		for field in PRIVACY_FIELDS
	}


async def redact_user(
	user: User,
	session: AsyncSession,
	principal: Principal,
	is_friend: bool | None = None,
) -> RedactedUser:
	"""return a privacy-redacted user identity."""
	if principal.is_admin or user.id == principal.user_id:
		return RedactedUser(
			id=user.id,
			username=user.username,
			display_name=user.display_name,
			email=user.email,
			avatar_url=user.avatar_url,
		)

	visible = await visible_fields(
		user, principal.user_id, session, is_friend=is_friend
	)
	return RedactedUser(
		id=user.id,
		username=user.username,
		display_name=user.display_name if visible["real_name"] else None,
		email=user.email if visible["email"] else None,
		avatar_url=user.avatar_url if visible["profile_picture"] else None,
	)


async def redact_users(
	users: list[User],
	session: AsyncSession,
	principal: Principal,
) -> dict[TypeID, RedactedUser]:
	"""redact many users with one friendship lookup."""
	if principal.is_admin:
		return {user.id: await redact_user(user, session, principal) for user in users}

	target_ids = [user.id for user in users if user.id != principal.user_id]
	friend_ids = await accepted_friend_ids(principal.user_id, target_ids, session)
	redacted: dict[TypeID, RedactedUser] = {}
	for user in users:
		redacted[user.id] = await redact_user(
			user,
			session,
			principal,
			is_friend=user.id in friend_ids,
		)
	return redacted


async def can_send_friend_request(
	target: User,
	session: AsyncSession,
	principal: Principal,
) -> bool:
	"""return whether the target allows a non-friend request from principal."""
	visible = await visible_fields(
		target,
		principal.user_id,
		session,
		is_friend=False,
	)
	return visible["allow_friend_requests"]
