"""notification routers."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.models.event_types import EventType
from api.models.notification import Notification
from api.permissions import ActionPermission
from api.schemas.notification import Notification as NotificationSchema
from api.schemas.notification import (
	NotificationCreate,
	NotificationListFilters,
)
from api.v1.service.authentication import Principal, get_current_principal
from api.v1.service.authorization import require_permission
from api.v1.service.notifications import (
	create_notifications as create_notifications_service,
)
from api.v1.service.notifications import (
	delete_notification as delete_notification_service,
)
from api.v1.service.notifications import (
	dismiss_notification as dismiss_notification_service,
)
from api.v1.service.notifications import (
	list_user_notifications as list_user_notifications_service,
)
from api.v1.service.notifications import (
	mark_all_notifications_read as mark_all_notifications_read_service,
)
from api.v1.service.notifications import (
	mark_notification_read as mark_notification_read_service,
)
from nokodo_ai.utils.typeid import TypeID


router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.post(
	"",
	response_model=list[NotificationSchema],
	status_code=status.HTTP_201_CREATED,
)
async def create_notifications(
	payload: NotificationCreate,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[Notification]:
	"""create ad hoc notification(s) for testing and management."""
	require_permission(principal, ActionPermission.NOTIFICATIONS_MANAGE)
	return await create_notifications_service(
		db,
		payload=payload,
		user_ids=payload.user_ids,
		event_type=EventType.NOTIFICATION_CUSTOM,
	)


@router.get("/users/{user_id}", response_model=list[NotificationSchema])
async def list_user_notifications(
	user_id: TypeID,
	filters: Annotated[NotificationListFilters, Depends()],
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[Notification]:
	"""return notifications for a user."""
	return await list_user_notifications_service(
		db,
		principal=principal,
		user_id=user_id,
		filters=filters,
	)


@router.post("/{notification_id}/read", response_model=NotificationSchema)
async def mark_notification_read(
	notification_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> Notification:
	"""mark a notification as read."""
	return await mark_notification_read_service(
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
	"""dismiss a notification without marking it read."""
	return await dismiss_notification_service(
		notification_id,
		db,
		principal=principal,
	)


@router.post("/users/{user_id}/read-all", response_model=int)
async def mark_all_notifications_read(
	user_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> int:
	"""mark all notifications as read for a user and return the update count."""
	return await mark_all_notifications_read_service(
		db,
		principal=principal,
		user_id=user_id,
	)


@router.delete("/{notification_id}", status_code=204)
async def delete_notification(
	notification_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> None:
	"""delete a notification."""
	await delete_notification_service(
		notification_id,
		db,
		principal=principal,
	)
