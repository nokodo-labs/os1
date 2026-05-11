"""friendship and block relationship helpers."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute
from sqlalchemy.sql import ColumnElement

from api.models.block import Block
from api.models.friendship import Friendship, FriendshipStatus
from nokodo_ai.utils.typeid import TypeID


def accepted_friendship_exists(
	user_a_id: TypeID | str,
	user_b_id: ColumnElement[TypeID] | InstrumentedAttribute[TypeID] | TypeID | str,
) -> ColumnElement[bool]:
	"""return whether two users have an accepted friendship."""
	return (
		select(Friendship.id)
		.where(
			Friendship.status == FriendshipStatus.ACCEPTED,
			or_(
				and_(
					Friendship.requester_id == user_a_id,
					Friendship.addressee_id == user_b_id,
				),
				and_(
					Friendship.requester_id == user_b_id,
					Friendship.addressee_id == user_a_id,
				),
			),
		)
		.exists()
	)


def block_exists(
	user_a_id: TypeID | str,
	user_b_id: ColumnElement[TypeID] | InstrumentedAttribute[TypeID] | TypeID | str,
) -> ColumnElement[bool]:
	"""return whether either user has blocked the other."""
	return (
		select(Block.id)
		.where(
			or_(
				and_(Block.blocker_id == user_a_id, Block.blocked_id == user_b_id),
				and_(Block.blocker_id == user_b_id, Block.blocked_id == user_a_id),
			)
		)
		.exists()
	)


async def are_friends(
	user_a_id: TypeID | str,
	user_b_id: TypeID | str,
	session: AsyncSession,
) -> bool:
	"""return True if the two users have an accepted friendship."""
	result = await session.execute(
		select(Friendship.id)
		.where(
			Friendship.status == FriendshipStatus.ACCEPTED,
			or_(
				and_(
					Friendship.requester_id == user_a_id,
					Friendship.addressee_id == user_b_id,
				),
				and_(
					Friendship.requester_id == user_b_id,
					Friendship.addressee_id == user_a_id,
				),
			),
		)
		.limit(1)
	)
	return result.scalar_one_or_none() is not None


async def accepted_friend_ids(
	user_id: TypeID | str,
	target_user_ids: Sequence[TypeID | str],
	session: AsyncSession,
) -> set[TypeID]:
	"""return target IDs that are accepted friends of user_id."""
	if not target_user_ids:
		return set()
	result = await session.execute(
		select(Friendship.requester_id, Friendship.addressee_id).where(
			Friendship.status == FriendshipStatus.ACCEPTED,
			or_(
				and_(
					Friendship.requester_id == user_id,
					Friendship.addressee_id.in_(target_user_ids),
				),
				and_(
					Friendship.addressee_id == user_id,
					Friendship.requester_id.in_(target_user_ids),
				),
			),
		)
	)
	friends: set[TypeID] = set()
	for requester_id, addressee_id in result.all():
		other_id = addressee_id if requester_id == user_id else requester_id
		friends.add(TypeID(str(other_id)))
	return friends


async def blocked_user_ids(
	user_id: TypeID | str,
	target_user_ids: Sequence[TypeID | str],
	session: AsyncSession,
) -> set[TypeID]:
	"""return target IDs blocked in either direction relative to user_id."""
	if not target_user_ids:
		return set()
	result = await session.execute(
		select(Block.blocker_id, Block.blocked_id).where(
			or_(
				and_(
					Block.blocker_id == user_id, Block.blocked_id.in_(target_user_ids)
				),
				and_(
					Block.blocked_id == user_id, Block.blocker_id.in_(target_user_ids)
				),
			)
		)
	)
	blocked: set[TypeID] = set()
	for blocker_id, blocked_id in result.all():
		other_id = blocked_id if blocker_id == user_id else blocker_id
		blocked.add(TypeID(str(other_id)))
	return blocked


async def is_blocked(
	user_a_id: TypeID | str,
	user_b_id: TypeID | str,
	session: AsyncSession,
) -> bool:
	"""return whether either user has blocked the other."""
	result = await session.execute(
		select(Block.id)
		.where(
			or_(
				and_(Block.blocker_id == user_a_id, Block.blocked_id == user_b_id),
				and_(Block.blocker_id == user_b_id, Block.blocked_id == user_a_id),
			)
		)
		.limit(1)
	)
	return result.scalar_one_or_none() is not None
