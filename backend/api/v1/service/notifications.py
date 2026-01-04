"""Service helpers for notifications."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.models.notification import Notification
from api.v1.service.auth import Principal


async def _get_notification(
	notification_id: str,
	session: AsyncSession,
	principal: Principal,
) -> Notification:
	stmt = (
		select(Notification)
		.options(selectinload(Notification.event))
		.where(Notification.id == notification_id)
	)
	if not principal.is_admin:
		stmt = stmt.where(Notification.user_id == principal.user.id)
	result = await session.execute(stmt)
	notification = result.scalars().one_or_none()
	if not notification:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Notification not found",
		)
	return notification


async def list_user_notifications(
	session: AsyncSession,
	*,
	principal: Principal,
	user_id: str,
	only_unread: bool = False,
) -> list[Notification]:
	if not principal.is_admin and str(user_id) != str(principal.user.id):
		raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")

	stmt = (
		select(Notification)
		.options(selectinload(Notification.event))
		.where(Notification.user_id == user_id)
		.order_by(Notification.created_at.desc())
	)

	if only_unread:
		stmt = stmt.where(Notification.read_at.is_(None))

	result = await session.execute(stmt.limit(100))
	return list(result.scalars().all())


async def mark_notification_read(
	notification_id: str,
	session: AsyncSession,
	*,
	principal: Principal,
) -> Notification:
	notification = await _get_notification(notification_id, session, principal)
	notification.read_at = datetime.now(tz=UTC)
	await session.commit()
	await session.refresh(notification)
	return notification


async def dismiss_notification(
	notification_id: str,
	session: AsyncSession,
	*,
	principal: Principal,
) -> Notification:
	notification = await _get_notification(notification_id, session, principal)
	notification.dismissed = True
	notification.read_at = notification.read_at or datetime.now(tz=UTC)
	await session.commit()
	await session.refresh(notification)
	return notification


async def mark_all_notifications_read(
	session: AsyncSession,
	*,
	principal: Principal,
	user_id: str,
) -> int:
	"""Mark all unread notifications as read for a user. Returns count updated."""
	if not principal.is_admin and str(user_id) != str(principal.user.id):
		raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")

	stmt = (
		update(Notification)
		.where(Notification.user_id == user_id)
		.where(Notification.read_at.is_(None))
		.values(read_at=datetime.now(tz=UTC))
	)
	result = await session.execute(stmt)
	await session.commit()
	return result.rowcount


async def delete_notification(
	notification_id: str,
	session: AsyncSession,
	*,
	principal: Principal,
) -> None:
	"""Delete a notification."""
	notification = await _get_notification(notification_id, session, principal)
	await session.delete(notification)
	await session.commit()
