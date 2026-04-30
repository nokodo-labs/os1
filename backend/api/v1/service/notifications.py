"""Service helpers for notifications."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.models.event import Event, EventScope
from api.models.event_types import EventType
from api.models.notification import Notification
from api.v1.service.auth import Principal
from api.v1.service.events import event_connections
from nokodo_ai.utils.typeid import TypeID, new_typeid


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
	principal: Principal,
	user_id: TypeID,
	only_unread: bool = False,
) -> list[Notification]:
	if not principal.is_admin and user_id != principal.user_id:
		raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")

	stmt = (
		select(Notification)
		.options(selectinload(Notification.event))
		.where(Notification.user_id == user_id)
		.where(Notification.dismissed.is_(False))
		.order_by(Notification.created_at.desc())
	)

	if only_unread:
		stmt = stmt.where(Notification.read_at.is_(None))

	result = await session.execute(stmt.limit(100))
	return list(result.scalars().all())


async def send_agent_notification(
	session: AsyncSession,
	title: str,
	body: str,
	user_ids: list[TypeID],
	agent_id: TypeID | None = None,
) -> list[Notification]:
	"""Send notification(s) triggered by an agent.

	Creates NOTIFICATION_AGENT event(s) and associated Notification record(s).
	Returns list of Notification objects created.
	"""
	if title == "" or body == "":
		raise ValueError("notification title and body are required")
	if not user_ids:
		raise ValueError("user_ids is required")

	seen: set[TypeID] = set()
	target_user_ids: list[TypeID] = []
	for uid in user_ids:
		if uid == "" or uid in seen:
			continue
		seen.add(uid)
		target_user_ids.append(uid)
	if not target_user_ids:
		raise ValueError("no recipients provided")

	notifications: list[Notification] = []

	for uid in target_user_ids:
		# create event
		event = Event(
			id=new_typeid("event"),
			scope=EventScope.USER,
			scope_id=uid,
			type=EventType.NOTIFICATION_AGENT,
			data={
				"title": title,
				"body": body,
				"agent_id": agent_id,
			},
			user_id=uid,
		)
		session.add(event)
		await session.flush()

		# create notification linked to event
		notification = Notification(user_id=uid, event_id=event.id)
		session.add(notification)

		notifications.append(notification)

	await session.commit()

	# refresh and broadcast each
	for notif in notifications:
		await session.refresh(notif, attribute_names=["event"])
		await event_connections.broadcast_event(notif.event)

	return notifications


async def mark_notification_read(
	notification_id: str,
	session: AsyncSession,
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
	principal: Principal,
	user_id: str,
) -> int:
	"""Mark all unread notifications as read for a user. Returns count updated."""
	if not principal.is_admin and str(user_id) != str(principal.user.id):
		raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")

	to_update = await session.scalar(
		select(func.count(Notification.id)).where(
			Notification.user_id == user_id,
			Notification.read_at.is_(None),
		)
	)
	if int(to_update or 0) == 0:
		return 0

	stmt = (
		update(Notification)
		.where(Notification.user_id == user_id)
		.where(Notification.read_at.is_(None))
		.values(read_at=datetime.now(tz=UTC))
	)
	result = await session.execute(stmt)
	await session.commit()
	_ = result
	return int(to_update or 0)


async def delete_notification(
	notification_id: str,
	session: AsyncSession,
	principal: Principal,
) -> None:
	"""Delete a notification."""
	notification = await _get_notification(notification_id, session, principal)
	event_id = notification.event_id
	await session.delete(notification)
	await session.flush()

	remaining_stmt = select(func.count(Notification.id)).where(
		Notification.event_id == event_id
	)
	remaining = await session.execute(remaining_stmt)
	if int(remaining.scalar_one()) == 0:
		event = await session.get(Event, event_id)
		if event is not None:
			await session.delete(event)

	await session.commit()
