"""service helpers for friendship operations.

all friend-read and friend-write logic is encapsulated here so that the
router layer never builds queries directly. this also means migrating from
the current OR-query lookup to a dual-row table (one row per direction)
only requires touching _find_friendship and list_friends.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.models.block import Block
from api.models.event import Event, EventScope
from api.models.event_types import EventType
from api.models.friendship import Friendship, FriendshipEvent, FriendshipStatus
from api.models.user import User
from api.v1.service import events as event_service
from api.v1.service.auth import Principal
from api.v1.service.authorization import require_permission
from nokodo_ai.utils.search import contains_pattern


async def send_friend_request(
	addressee_id: str,
	session: AsyncSession,
	principal: Principal,
	origin_session_id: str | None = None,
) -> Friendship:
	"""send a friend request to another user."""
	require_permission(principal, "friends:create")
	requester_id = principal.user_id

	if requester_id == addressee_id:
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="cannot send a friend request to yourself",
		)

	target = await session.get(User, addressee_id)
	if not target:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="user not found",
		)

	# block check - prevent requests when either party has blocked the other
	if await _is_blocked(requester_id, addressee_id, session):
		raise HTTPException(
			status_code=status.HTTP_403_FORBIDDEN,
			detail="cannot send friend request",
		)

	existing = await _find_friendship(requester_id, addressee_id, session)
	if existing:
		if existing.status == FriendshipStatus.ACCEPTED:
			raise HTTPException(
				status_code=status.HTTP_409_CONFLICT,
				detail="already friends",
			)
		if existing.status == FriendshipStatus.PENDING:
			# if the OTHER person already requested us, auto-accept
			if existing.requester_id == addressee_id:
				return await _accept(existing, session, principal, origin_session_id)
			raise HTTPException(
				status_code=status.HTTP_409_CONFLICT,
				detail="friend request already pending",
			)
		# if previously declined or removed, allow re-request
		if existing.status in (
			FriendshipStatus.DECLINED,
			FriendshipStatus.REMOVED,
		):
			existing.status = FriendshipStatus.PENDING
			existing.requester_id = requester_id
			existing.addressee_id = addressee_id
			await session.flush()
			await _record_event(existing, FriendshipStatus.PENDING, principal, session)
			await _publish_request_event(
				existing, session, principal, origin_session_id
			)
			return existing

	friendship = Friendship(
		requester_id=requester_id,
		addressee_id=addressee_id,
		status=FriendshipStatus.PENDING,
	)
	session.add(friendship)
	await session.flush()
	await _record_event(friendship, FriendshipStatus.PENDING, principal, session)
	await _publish_request_event(friendship, session, principal, origin_session_id)
	return friendship


async def accept_friend_request(
	friendship_id: str,
	session: AsyncSession,
	principal: Principal,
	origin_session_id: str | None = None,
) -> Friendship:
	"""accept an incoming friend request."""
	friendship = await _get_friendship(friendship_id, session)
	if friendship.addressee_id != principal.user_id:
		raise HTTPException(
			status_code=status.HTTP_403_FORBIDDEN,
			detail="only the recipient can accept a friend request",
		)
	if friendship.status != FriendshipStatus.PENDING:
		raise HTTPException(
			status_code=status.HTTP_409_CONFLICT,
			detail=f"request is {friendship.status}, not pending",
		)
	return await _accept(friendship, session, principal, origin_session_id)


async def decline_friend_request(
	friendship_id: str,
	session: AsyncSession,
	principal: Principal,
	origin_session_id: str | None = None,
) -> Friendship:
	"""decline an incoming friend request."""
	friendship = await _get_friendship(friendship_id, session)
	if friendship.addressee_id != principal.user_id:
		raise HTTPException(
			status_code=status.HTTP_403_FORBIDDEN,
			detail="only the recipient can decline a friend request",
		)
	if friendship.status != FriendshipStatus.PENDING:
		raise HTTPException(
			status_code=status.HTTP_409_CONFLICT,
			detail=f"request is {friendship.status}, not pending",
		)
	friendship.status = FriendshipStatus.DECLINED
	await session.flush()
	await _record_event(friendship, FriendshipStatus.DECLINED, principal, session)
	event = Event(
		scope=EventScope.USER,
		scope_id=friendship.requester_id,
		type=EventType.FRIEND_REQUEST_DECLINED,
		data={
			"friendship_id": str(friendship.id),
			"declined_by": principal.user_id,
		},
		user_id=principal.user_id,
	)
	await event_service.publish_event(
		session, event=event, origin_session_id=origin_session_id
	)
	return friendship


async def remove_friend(
	friend_user_id: str,
	session: AsyncSession,
	principal: Principal,
	origin_session_id: str | None = None,
) -> None:
	"""remove an existing friend.

	sets the friendship status to REMOVED rather than deleting the row so the
	history (and FriendshipEvent log) is preserved.
	"""
	friendship = await _find_friendship(principal.user_id, friend_user_id, session)
	if not friendship or friendship.status != FriendshipStatus.ACCEPTED:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="friendship not found",
		)
	other_user_id = (
		friendship.addressee_id
		if friendship.requester_id == principal.user_id
		else friendship.requester_id
	)
	friendship.status = FriendshipStatus.REMOVED
	await session.flush()
	await _record_event(friendship, FriendshipStatus.REMOVED, principal, session)
	event = Event(
		scope=EventScope.USER,
		scope_id=other_user_id,
		type=EventType.FRIEND_REMOVED,
		data={
			"removed_by": principal.user_id,
			"friend_id": other_user_id,
		},
		user_id=principal.user_id,
	)
	await event_service.publish_event(
		session, event=event, origin_session_id=origin_session_id
	)


async def list_friends(
	session: AsyncSession,
	principal: Principal,
) -> list[tuple[User, str]]:
	"""list all accepted friends of the current user.

	returns (friend_user, friendship_id) tuples. uses an OR-query across
	requester_id / addressee_id. see the module docstring for the dual-row
	upgrade path that would simplify this to a single equality condition.
	"""
	user_id = principal.user_id
	stmt = (
		select(Friendship)
		.where(
			Friendship.status == FriendshipStatus.ACCEPTED,
			or_(
				Friendship.requester_id == user_id,
				Friendship.addressee_id == user_id,
			),
		)
		.options(
			selectinload(Friendship.requester),
			selectinload(Friendship.addressee),
		)
	)
	result = await session.execute(stmt)
	friendships = result.scalars().all()
	friends: list[tuple[User, str]] = []
	for f in friendships:
		friend = f.addressee if f.requester_id == user_id else f.requester
		friends.append((friend, str(f.id)))
	return friends


async def list_incoming_requests(
	session: AsyncSession,
	principal: Principal,
) -> list[Friendship]:
	"""list pending friend requests sent TO the current user."""
	stmt = (
		select(Friendship)
		.where(
			Friendship.addressee_id == principal.user_id,
			Friendship.status == FriendshipStatus.PENDING,
		)
		.options(selectinload(Friendship.requester))
		.order_by(Friendship.created_at.desc())
	)
	result = await session.execute(stmt)
	return list(result.scalars().all())


async def list_outgoing_requests(
	session: AsyncSession,
	principal: Principal,
) -> list[Friendship]:
	"""list pending friend requests sent BY the current user."""
	stmt = (
		select(Friendship)
		.where(
			Friendship.requester_id == principal.user_id,
			Friendship.status == FriendshipStatus.PENDING,
		)
		.options(selectinload(Friendship.addressee))
		.order_by(Friendship.created_at.desc())
	)
	result = await session.execute(stmt)
	return list(result.scalars().all())


async def search_users(
	query: str,
	session: AsyncSession,
	principal: Principal,
	limit: int = 20,
) -> list[User]:
	"""search users by username, display_name, or email.

	username and display_name are always searched. email is only matched
	when the target user has find_by_email enabled (privacy control).
	"""
	q = contains_pattern(query)
	stmt = (
		select(User)
		.where(
			User.id != principal.user_id,
			User.is_active.is_(True),
			or_(
				User.username.ilike(q, escape="\\"),
				User.display_name.ilike(q, escape="\\"),
				User.find_by_email.is_(True)
				& User.email.ilike(q, escape="\\"),
			),
		)
		.limit(limit)
	)
	result = await session.execute(stmt)
	return list(result.scalars().all())


async def _find_friendship(
	user_a: str,
	user_b: str,
	session: AsyncSession,
) -> Friendship | None:
	"""find a friendship row between two users, in either direction.

	single refactor point for the dual-row migration: replace the OR-query
	with a simple equality lookup once the table stores two rows per pair.
	"""
	stmt = select(Friendship).where(
		or_(
			(Friendship.requester_id == user_a) & (Friendship.addressee_id == user_b),
			(Friendship.requester_id == user_b) & (Friendship.addressee_id == user_a),
		)
	)
	result = await session.execute(stmt)
	return result.scalar_one_or_none()


async def _get_friendship(
	friendship_id: str,
	session: AsyncSession,
) -> Friendship:
	"""load a friendship by id or raise 404."""
	friendship = await session.get(Friendship, friendship_id)
	if not friendship:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="friend request not found",
		)
	return friendship


async def _is_blocked(
	user_a: str,
	user_b: str,
	session: AsyncSession,
) -> bool:
	"""check whether a block exists between two users in either direction."""
	stmt = (
		select(Block.id)
		.where(
			or_(
				(Block.blocker_id == user_a) & (Block.blocked_id == user_b),
				(Block.blocker_id == user_b) & (Block.blocked_id == user_a),
			)
		)
		.limit(1)
	)
	result = await session.execute(stmt)
	return result.scalar_one_or_none() is not None


async def _record_event(
	friendship: Friendship,
	new_status: FriendshipStatus,
	principal: Principal,
	session: AsyncSession,
) -> None:
	"""append a FriendshipEvent to the history log."""
	event = FriendshipEvent(
		friendship_id=str(friendship.id),
		status=new_status,
		actor_id=principal.user_id,
	)
	session.add(event)
	await session.flush()


async def _accept(
	friendship: Friendship,
	session: AsyncSession,
	principal: Principal,
	origin_session_id: str | None,
) -> Friendship:
	"""mark a friendship as accepted and publish events."""
	friendship.status = FriendshipStatus.ACCEPTED
	friendship.accepted_at = datetime.now(UTC)
	await session.flush()
	await _record_event(friendship, FriendshipStatus.ACCEPTED, principal, session)

	for target_id in (friendship.requester_id, friendship.addressee_id):
		event = Event(
			scope=EventScope.USER,
			scope_id=target_id,
			type=EventType.FRIEND_REQUEST_ACCEPTED,
			data={
				"friendship_id": str(friendship.id),
				"requester_id": friendship.requester_id,
				"addressee_id": friendship.addressee_id,
			},
			user_id=principal.user_id,
		)
		await event_service.publish_event(
			session, event=event, origin_session_id=origin_session_id
		)
	return friendship


async def _publish_request_event(
	friendship: Friendship,
	session: AsyncSession,
	principal: Principal,
	origin_session_id: str | None,
) -> None:
	"""publish a friend request event to the addressee."""
	event = Event(
		scope=EventScope.USER,
		scope_id=friendship.addressee_id,
		type=EventType.FRIEND_REQUEST_SENT,
		data={
			"friendship_id": str(friendship.id),
			"requester_id": friendship.requester_id,
		},
		user_id=principal.user_id,
	)
	await event_service.publish_event(
		session, event=event, origin_session_id=origin_session_id
	)
