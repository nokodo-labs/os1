"""user routers."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.models.user import User
from api.permissions import ActionPermission
from api.schemas.friendship import UserSearchResult
from api.schemas.sorting import SortDir
from api.schemas.user import User as UserSchema
from api.schemas.user import (
	UserBulkLookupRequest,
	UserCreate,
	UserEmailChange,
	UserListFilters,
	UserPasswordChange,
	UserPermissions,
	UserSortBy,
	UserSummary,
	UserUpdate,
)
from api.settings import settings
from api.v1.routers import blocks as blocks_router
from api.v1.routers import friends as friends_router
from api.v1.routers import user_clients as user_clients_router
from api.v1.routers import user_sessions as user_sessions_router
from api.v1.service.authentication import (
	Principal,
	build_principal,
	get_current_principal,
	get_optional_principal,
)
from api.v1.service.authorization import require_permission
from api.v1.service.events import SessionId
from api.v1.service.friends import search_users as search_users_service
from api.v1.service.users import (
	change_email,
	change_password,
	get_accessible_user_summaries,
	get_user,
	get_user_counts,
	list_active_user_ids,
	list_users,
)
from api.v1.service.users import (
	count_users as count_users_service,
)
from api.v1.service.users import (
	create_user as create_user_service,
)
from api.v1.service.users import (
	delete_user as delete_user_service,
)
from api.v1.service.users import (
	update_user as update_user_service,
)
from nokodo_ai.utils.typeid import TypeID


router = APIRouter(prefix="/users", tags=["users"])
router.include_router(blocks_router.router)
router.include_router(friends_router.router)
router.include_router(user_clients_router.router)
router.include_router(user_sessions_router.router)


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
	users = await list_users(
		db,
		principal=principal,
		skip=skip,
		limit=limit,
		sort_by=sort_by,
		sort_dir=sort_dir,
		q=filters.q,
	)
	active_ids = set(await list_active_user_ids())
	return [_user_with_online(u, active_ids) for u in users]


@router.get("/count", response_model=int)
async def count_users(
	filters: Annotated[UserListFilters, Depends()],
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> int:
	"""count users matching the list filters."""
	return await count_users_service(db, principal=principal, q=filters.q)


@router.get("/active", response_model=list[str])
async def read_active_user_ids(
	principal: Principal = Depends(get_current_principal),
) -> list[str]:
	"""return IDs of users currently connected to the event stream."""
	require_permission(principal, ActionPermission.USERS_READ)
	return await list_active_user_ids()


@router.get("/search", response_model=list[UserSearchResult])
async def search_users(
	q: str,
	limit: int = 20,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[UserSearchResult]:
	"""search users by username or privacy-visible profile fields."""
	return await search_users_service(q, db, principal=principal, limit=min(limit, 50))


@router.post("/bulk", response_model=list[UserSummary])
async def read_user_summaries(
	body: UserBulkLookupRequest,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[UserSummary]:
	"""look up visible user summaries by ID."""
	return await get_accessible_user_summaries(
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
	user = await get_user(user_id, db, principal=principal)
	active_ids = set(await list_active_user_ids())
	return _user_with_online(user, active_ids)


@router.post("", response_model=UserSchema, status_code=status.HTTP_201_CREATED)
async def create_user(
	user_in: UserCreate,
	principal: Principal | None = Depends(get_optional_principal),
	db: AsyncSession = Depends(get_db),
) -> User:
	"""create new user."""
	return await create_user_service(user_in, db, principal=principal)


@router.get("/{user_id}/permissions", response_model=UserPermissions)
async def read_user_permissions(
	user_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> UserPermissions:
	"""get resolved permissions for user."""
	user = await get_user(user_id, db, principal=principal)
	# eager-load roles so build_principal can iterate without
	# triggering a sync lazy load inside the async session
	await db.refresh(user, ["roles"])
	as_principal = await build_principal(user=user, session=db)

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
	return await get_user_counts(user_id, db, principal=principal)


@router.patch("/{user_id}", response_model=UserSchema)
async def update_user(
	user_id: TypeID,
	body: UserUpdate,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> User:
	"""update user."""
	return await update_user_service(
		user_id, body, db, principal=principal, origin_session_id=x_session_id
	)


@router.post("/{user_id}/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_user_password(
	user_id: TypeID,
	body: UserPasswordChange,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> None:
	"""change a user's password. self-service requires the current password."""
	if settings.security.oidc.only:
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="password change not available with oidc-only authentication",
		)
	await change_password(user_id, body, db, principal=principal)


@router.post("/{user_id}/change-email", response_model=UserSchema)
async def change_user_email(
	user_id: TypeID,
	body: UserEmailChange,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> User:
	"""change a user's email address."""
	return await change_email(user_id, body, db, principal=principal)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
	user_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> None:
	"""delete user."""
	await delete_user_service(user_id, db, principal=principal)
