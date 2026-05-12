"""service helpers for friendship operations.

all friend-read and friend-write logic is encapsulated here so that the
router layer never builds queries directly. this also means migrating from
the current OR-query lookup to a dual-row table (one row per direction)
only requires touching _find_friendship and list_friends.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql import Select

from api.models.event import Event, EventScope
from api.models.event_types import EventType
from api.models.friendship import Friendship, FriendshipEvent, FriendshipStatus
from api.models.user import User
from api.schemas.friendship import FriendResponse, UserSearchResult
from api.v1.service import events as event_service
from api.v1.service.auth import Principal
from api.v1.service.authorization import require_permission
from api.v1.service.social import friendship as relationship_service
from api.v1.service.social import privacy as privacy_service
from api.v1.service.social.visibility import (
	user_bio_filter_predicate,
	user_display_name_filter_predicate,
	user_email_filter_predicate,
	user_search_candidate_predicate,
	user_username_filter_predicate,
)
from nokodo_ai.utils.search import contains_pattern
from nokodo_ai.utils.typeid import TypeID


def _apply_user_search_filters(
	stmt: Select,
	query: str,
	principal: Principal,
) -> Select:
	"""apply privacy-aware user search filters."""
	pattern = contains_pattern(query.strip())
	return stmt.where(
		User.id != principal.user_id,
		user_search_candidate_predicate(principal),
		or_(
			and_(
				user_username_filter_predicate(principal),
				User.username.ilike(pattern, escape="\\"),
			),
			and_(
				user_display_name_filter_predicate(principal),
				User.display_name.ilike(pattern, escape="\\"),
			),
			and_(
				user_email_filter_predicate(principal),
				User.email.ilike(pattern, escape="\\"),
			),
			and_(
				user_bio_filter_predicate(principal),
				User.bio.ilike(pattern, escape="\\"),
			),
		),
	)


async def build_friend_response(
	user: User,
	friendship_id: TypeID,
	session: AsyncSession,
	principal: Principal,
	is_friend: bool | None = None,
) -> FriendResponse:
	"""build a sanitized accepted-friend response."""
	redacted = await privacy_service.redact_user(
		user,
		session,
		principal,
		is_friend=is_friend,
	)
	return FriendResponse(
		id=user.id,
		friendship_id=friendship_id,
		username=user.username,
		display_name=redacted.display_name,
		email=redacted.email,
		avatar_url=redacted.avatar_url,
	)


def _build_user_search_result(
	redacted: privacy_service.RedactedUser,
) -> UserSearchResult:
	"""build a sanitized user search result."""
	return UserSearchResult(
		id=redacted.id,
		username=redacted.username,
		display_name=redacted.display_name,
		email=redacted.email,
		avatar_url=redacted.avatar_url,
	)


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
	if await relationship_service.is_blocked(requester_id, addressee_id, session):
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

	if not await privacy_service.can_send_friend_request(target, session, principal):
		raise HTTPException(
			status_code=status.HTTP_403_FORBIDDEN,
			detail="cannot send friend request",
		)

	if existing:
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
	await event_service.persist_and_fanout_event(
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
	await event_service.persist_and_fanout_event(
		session, event=event, origin_session_id=origin_session_id
	)


async def list_friends(
	session: AsyncSession,
	principal: Principal,
) -> list[tuple[User, TypeID]]:
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
	friends: list[tuple[User, TypeID]] = []
	blocked_ids = await relationship_service.blocked_user_ids(
		user_id,
		[
			f.addressee_id if f.requester_id == user_id else f.requester_id
			for f in friendships
		],
		session,
	)
	for f in friendships:
		friend = f.addressee if f.requester_id == user_id else f.requester
		if friend.id in blocked_ids:
			continue
		friends.append((friend, f.id))
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
) -> list[UserSearchResult]:
	"""search users by username or privacy-visible profile fields."""
	if not query.strip():
		return []
	stmt = _apply_user_search_filters(select(User), query, principal).limit(limit)
	result = await session.execute(stmt)
	users = list(result.scalars().all())
	redacted = await privacy_service.redact_users(users, session, principal)
	return [_build_user_search_result(redacted[user.id]) for user in users]


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
		await event_service.persist_and_fanout_event(
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
	await event_service.persist_and_fanout_event(
		session, event=event, origin_session_id=origin_session_id
	)
