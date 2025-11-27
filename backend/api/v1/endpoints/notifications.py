"""Notification endpoints."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.core.database import get_db
from api.models.notification import Notification
from api.schemas.notification import Notification as NotificationSchema


router = APIRouter(prefix="/notifications", tags=["notifications"])


async def _get_notification(
	notification_id: str,
	db: AsyncSession,
) -> Notification:
	stmt = (
		select(Notification)
		.options(selectinload(Notification.event))
		.where(Notification.id == notification_id)
	)
	result = await db.execute(stmt)
	notification = result.scalars().one_or_none()
	if not notification:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Notification not found",
		)
	return notification


@router.get("/users/{user_id}", response_model=list[NotificationSchema])
async def list_user_notifications(
	user_id: int,
	only_unread: bool = False,
	db: AsyncSession = Depends(get_db),
) -> list[Notification]:
	"""Return notifications for a user."""
	stmt = (
		select(Notification)
		.options(selectinload(Notification.event))
		.where(Notification.user_id == user_id)
		.order_by(Notification.created_at.desc())
	)

	if only_unread:
		stmt = stmt.where(Notification.read_at.is_(None))

	result = await db.execute(stmt.limit(100))
	return list(result.scalars().all())


@router.post("/{notification_id}/read", response_model=NotificationSchema)
async def mark_notification_read(
	notification_id: str,
	db: AsyncSession = Depends(get_db),
) -> Notification:
	"""Mark a notification as read."""
	notification = await _get_notification(notification_id, db)
	notification.read_at = datetime.now(tz=UTC)
	await db.commit()
	await db.refresh(notification)
	return notification


@router.post("/{notification_id}/dismiss", response_model=NotificationSchema)
async def dismiss_notification(
	notification_id: str,
	db: AsyncSession = Depends(get_db),
) -> Notification:
	"""Dismiss a notification without marking it read."""
	notification = await _get_notification(notification_id, db)
	notification.dismissed = True
	notification.read_at = notification.read_at or datetime.now(tz=UTC)
	await db.commit()
	await db.refresh(notification)
	return notification
