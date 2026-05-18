"""user routers."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.models.user import User
from api.schemas.friendship import UserSearchResult
from api.schemas.sorting import SortDir
from api.schemas.user import User as UserSchema
from api.schemas.user import (
	UserBulkLookupRequest,
	UserCreate,
	UserListFilters,
	UserPermissions,
	UserSortBy,
	UserSummary,
	UserUpdate,
)
from api.v1.routers import blocks as blocks_router
from api.v1.routers import friends as friends_router
from api.v1.routers import user_clients as user_clients_router
from api.v1.service import friends as friends_service
from api.v1.service import users as user_service
from api.v1.service.auth import (
	Principal,
	get_current_principal,
	get_optional_principal,
)
from api.v1.service.events import SessionId
from api.v1.service.user_activity import user_activity_store
from nokodo_ai.utils.typeid import TypeID


router = APIRouter(prefix="/users", tags=["users"])
router.include_router(blocks_router.router)
router.include_router(friends_router.router)
router.include_router(user_clients_router.router)


def _user_with_online(user: User, active_ids: set[str]) -> UserSchema:
	"""serialize a User ORM model with the computed is_online flag."""
	schema = UserSchema.model_validate(user)
	schema.is_online = str(user.id) in active_ids
	return schema


@router.get("", response_model=list[UserSchema])
async def read_users(
	filters: Annotated[UserListFilters, Depends()],
	skip: int = 0,
	limit: int = 100,
	sort_by: UserSortBy = "updated_at",
	sort_dir: SortDir = "desc",
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[UserSchema]:
	"""retrieve users."""
	users = await user_service.list_users(
		db,
		principal=principal,
		skip=skip,
		limit=limit,
		sort_by=sort_by,
		sort_dir=sort_dir,
		q=filters.q,
	)
	active_ids = set(await user_activity_store.get_active_user_ids())
	return [_user_with_online(u, active_ids) for u in users]


@router.get("/count", response_model=int)
async def count_users(
	filters: Annotated[UserListFilters, Depends()],
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> int:
	"""count users matching the list filters."""
	return await user_service.count_users(db, principal=principal, q=filters.q)


@router.get("/active", response_model=list[str])
async def read_active_user_ids(
	principal: Principal = Depends(get_current_principal),
) -> list[str]:
	"""return IDs of users currently connected to the event stream."""
	if not principal.is_admin:
		raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
	return await user_activity_store.get_active_user_ids()


@router.get("/search", response_model=list[UserSearchResult])
async def search_users(
	q: str,
	limit: int = 20,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[UserSearchResult]:
	"""search users by username or privacy-visible profile fields."""
	return await friends_service.search_users(
		q, db, principal=principal, limit=min(limit, 50)
	)


@router.post("/bulk", response_model=list[UserSummary])
async def read_user_summaries(
	body: UserBulkLookupRequest,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[UserSummary]:
	"""look up visible user summaries by ID."""
	return await user_service.get_accessible_user_summaries(
		body.user_ids,
		db,
		principal=principal,
	)


@router.get("/{user_id}", response_model=UserSchema)
async def read_user(
	user_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> UserSchema:
	"""get user by ID."""
	user = await user_service.get_user(user_id, db, principal=principal)
	active_ids = set(await user_activity_store.get_active_user_ids())
	return _user_with_online(user, active_ids)


@router.post("", response_model=UserSchema, status_code=status.HTTP_201_CREATED)
async def create_user(
	user_in: UserCreate,
	principal: Principal | None = Depends(get_optional_principal),
	db: AsyncSession = Depends(get_db),
) -> User:
	"""create new user."""
	return await user_service.create_user(user_in, db, principal=principal)


@router.get("/{user_id}/permissions", response_model=UserPermissions)
async def read_user_permissions(
	user_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> UserPermissions:
	"""get resolved permissions for user."""
	if not principal.is_admin and str(user_id) != principal.user_id:
		raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")

	user = await user_service.get_user(user_id, db, principal=principal)
	# eager-load roles so get_current_principal can iterate without
	# triggering a sync lazy load inside the async session
	await db.refresh(user, ["roles"])
	as_principal = await get_current_principal(user=user, session=db)

	return UserPermissions(
		permissions=sorted(as_principal.permissions),
	)


@router.get("/{user_id}/counts", response_model=dict[str, int])
async def read_user_counts(
	user_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> dict[str, int]:
	"""get counts of all resources owned by user."""
	return await user_service.get_user_counts(user_id, db, principal=principal)


@router.patch("/{user_id}", response_model=UserSchema)
async def update_user(
	user_id: TypeID,
	body: UserUpdate,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> User:
	"""update user."""
	return await user_service.update_user(
		user_id, body, db, principal=principal, origin_session_id=x_session_id
	)
