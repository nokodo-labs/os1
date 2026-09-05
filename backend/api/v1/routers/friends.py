"""friend management routers - nested under /users/{user_id}."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.models.friendship import Friendship
from api.schemas.friendship import (
	FriendRequestCreate,
	FriendResponse,
	FriendshipDetail,
	FriendshipResponse,
)
from api.v1.service.authentication import Principal, get_current_principal
from api.v1.service.events import SessionId
from api.v1.service.friends import (
	accept_friend_request as accept_friend_request_service,
)
from api.v1.service.friends import (
	build_friend_response,
)
from api.v1.service.friends import (
	cancel_friend_request as cancel_friend_request_service,
)
from api.v1.service.friends import (
	decline_friend_request as decline_friend_request_service,
)
from api.v1.service.friends import (
	list_friends as list_friends_service,
)
from api.v1.service.friends import (
	list_incoming_requests as list_incoming_requests_service,
)
from api.v1.service.friends import (
	list_outgoing_requests as list_outgoing_requests_service,
)
from api.v1.service.friends import (
	remove_friend as remove_friend_service,
)
from api.v1.service.friends import (
	send_friend_request as send_friend_request_service,
)
from nokodo_ai.utils.typeid import TypeID


router = APIRouter(prefix="/{user_id}/friends", tags=["friends"])


@router.get("", response_model=list[FriendResponse])
async def list_friends(
	user_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[FriendResponse]:
	"""list all accepted friends."""
	pairs = await list_friends_service(db, principal=principal, target_user_id=user_id)
	return [
		await build_friend_response(
			friend,
			friendship_id,
			db,
			principal=principal,
			is_friend=True,
		)
		for friend, friendship_id in pairs
	]


@router.get("/requests/incoming", response_model=list[FriendshipDetail])
async def list_incoming_requests(
	user_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[Friendship]:
	"""list pending friend requests received by the current user."""
	return await list_incoming_requests_service(
		db, principal=principal, target_user_id=user_id
	)


@router.get("/requests/outgoing", response_model=list[FriendshipDetail])
async def list_outgoing_requests(
	user_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[Friendship]:
	"""list pending friend requests sent by the current user."""
	return await list_outgoing_requests_service(
		db, principal=principal, target_user_id=user_id
	)


@router.post(
	"/requests",
	response_model=FriendshipResponse,
	status_code=status.HTTP_201_CREATED,
)
async def send_friend_request(
	user_id: TypeID,
	body: FriendRequestCreate,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> Friendship:
	"""send a friend request to another user."""
	return await send_friend_request_service(
		user_id,
		body.addressee_id,
		db,
		principal=principal,
		origin_session_id=x_session_id,
	)


@router.post(
	"/requests/{friendship_id}/accept",
	response_model=FriendshipResponse,
)
async def accept_friend_request(
	user_id: TypeID,
	friendship_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> Friendship:
	"""accept an incoming friend request."""
	return await accept_friend_request_service(
		str(friendship_id),
		user_id,
		db,
		principal=principal,
		origin_session_id=x_session_id,
	)


@router.post(
	"/requests/{friendship_id}/decline",
	response_model=FriendshipResponse,
)
async def decline_friend_request(
	user_id: TypeID,
	friendship_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> Friendship:
	"""decline an incoming friend request."""
	return await decline_friend_request_service(
		str(friendship_id),
		user_id,
		db,
		principal=principal,
		origin_session_id=x_session_id,
	)


@router.delete("/requests/{friendship_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_friend_request(
	user_id: TypeID,
	friendship_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> None:
	"""cancel an outgoing friend request."""
	await cancel_friend_request_service(
		str(friendship_id),
		user_id,
		db,
		principal=principal,
		origin_session_id=x_session_id,
	)


@router.delete("/{friend_user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_friend(
	user_id: TypeID,
	friend_user_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> None:
	"""remove an existing friend."""
	await remove_friend_service(
		user_id,
		friend_user_id,
		db,
		principal=principal,
		origin_session_id=x_session_id,
	)
