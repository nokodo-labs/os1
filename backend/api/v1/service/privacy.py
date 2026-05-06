"""privacy enforcement helpers.

every endpoint that exposes user data (profile, online status, DMs)
must check the target user's privacy settings against the requesting
user's relationship before returning data.
"""

from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.friendship import Friendship, FriendshipStatus
from api.models.user import User
from api.schemas.privacy import UserPrivacy, Visibility


async def are_friends(
	user_a_id: str,
	user_b_id: str,
	session: AsyncSession,
) -> bool:
	"""return True if the two users have an accepted friendship."""
	stmt = (
		select(Friendship.id)
		.where(
			Friendship.status == FriendshipStatus.ACCEPTED,
			or_(
				(Friendship.requester_id == user_a_id)
				& (Friendship.addressee_id == user_b_id),
				(Friendship.requester_id == user_b_id)
				& (Friendship.addressee_id == user_a_id),
			),
		)
		.limit(1)
	)
	result = await session.execute(stmt)
	return result.scalar_one_or_none() is not None


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
	"""return True if the requester is allowed to see the field.

	is_self always grants access regardless of the setting.
	"""
	if is_self:
		return True
	if setting == Visibility.EVERYONE:
		return True
	if setting == Visibility.FRIENDS:
		return is_friend
	return False


async def visible_fields(
	target: User,
	requester_id: str,
	session: AsyncSession,
) -> dict[str, bool]:
	"""check all privacy settings for target relative to requester.

	returns a dict mapping each privacy field to whether the requester
	is allowed to see it.
	"""
	is_self = str(target.id) == requester_id
	if is_self:
		return {
			"online_status": True,
			"profile_picture": True,
			"real_name": True,
			"bio": True,
			"gender": True,
			"birth_date": True,
			"allow_dms": True,
			"allow_friend_requests": True,
		}

	privacy = get_privacy(target)
	is_friend = await are_friends(str(target.id), requester_id, session)

	return {
		"online_status": check_visibility(privacy.online_status, is_friend=is_friend),
		"profile_picture": check_visibility(
			privacy.profile_picture, is_friend=is_friend
		),
		"real_name": check_visibility(privacy.real_name, is_friend=is_friend),
		"bio": check_visibility(privacy.bio, is_friend=is_friend),
		"gender": check_visibility(privacy.gender, is_friend=is_friend),
		"birth_date": check_visibility(privacy.birth_date, is_friend=is_friend),
		"allow_dms": check_visibility(privacy.allow_dms, is_friend=is_friend),
		"allow_friend_requests": check_visibility(
			privacy.allow_friend_requests, is_friend=is_friend
		),
	}
