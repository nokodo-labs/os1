"""Notification routers."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.database import get_db
from api.models.notification import Notification
from api.schemas.notification import Notification as NotificationSchema
from api.typeid import TypeID
from api.v1.service import notifications as notification_service
from api.v1.service.auth import Principal, get_current_principal


router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("/users/{user_id}", response_model=list[NotificationSchema])
async def list_user_notifications(
	user_id: TypeID,
	only_unread: bool = False,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[Notification]:
	"""Return notifications for a user."""
	return await notification_service.list_user_notifications(
		db,
		principal=principal,
		user_id=user_id,
		only_unread=only_unread,
	)


@router.post("/{notification_id}/read", response_model=NotificationSchema)
async def mark_notification_read(
	notification_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> Notification:
	"""Mark a notification as read."""
	return await notification_service.mark_notification_read(
		notification_id,
		db,
		principal=principal,
	)


@router.post("/{notification_id}/dismiss", response_model=NotificationSchema)
async def dismiss_notification(
	notification_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> Notification:
	"""Dismiss a notification without marking it read."""
	return await notification_service.dismiss_notification(
		notification_id,
		db,
		principal=principal,
	)
