"""service helpers for notifications."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.elements import ColumnElement

from api.models.event import Event, EventScope
from api.models.event_types import EventType
from api.models.notification import Notification, NotificationPushSubscription
from api.models.user_client import UserClient
from api.schemas.notification import (
	NotificationAction,
	NotificationListFilters,
	NotificationPayload,
	NotificationPushSubscriptionCreate,
	NotificationPushSubscriptionDelete,
)
from api.service.web_assets import (
	STATIC_ASSET_PATH,
	app_url,
	cdn_asset_url,
	resolve_asset_source,
)
from api.settings import settings
from api.settings.settings import ManifestAssetSettings
from api.v1.service.auth import Principal
from api.v1.service.events import fanout_event
from api.v1.service.web_push import schedule_notification_push
from nokodo_ai.types.json import JSONArray, JSONObject
from nokodo_ai.utils.typeid import TypeID, new_typeid


def _action_data(actions: list[NotificationAction] | None) -> JSONArray:
	"""serialize notification actions into JSON-safe payload data."""
	items: JSONArray = []
	for action in actions or []:
		item: JSONObject = {
			"action": action.action,
			"title": action.title,
		}
		if action.icon_url:
			item["icon_url"] = action.icon_url
		items.append(item)
	return items


def _event_data(
	payload: NotificationPayload,
	actions: JSONArray,
	expires_at: datetime | None,
	notification_id: TypeID,
	agent_id: TypeID | None,
) -> JSONObject:
	"""build event data from the normalized notification payload."""
	custom_data = dict(payload.data)
	custom_data["notification_id"] = str(notification_id)
	if payload.action_url is not None:
		custom_data["action_url"] = payload.action_url
	payload_data: JSONObject = {
		"id": str(notification_id),
		"title": payload.title,
		"body": payload.body,
		"icon_url": payload.icon_url,
		"image_url": payload.image_url,
		"badge_url": payload.badge_url,
		"action_url": payload.action_url,
		"tag": payload.tag,
		"data": custom_data,
		"actions": actions,
		"require_interaction": payload.require_interaction,
		"silent": payload.silent,
		"renotify": payload.renotify,
		"expires_at": expires_at.isoformat() if expires_at is not None else None,
	}
	event_data: JSONObject = {
		"notification_id": str(notification_id),
		"payload": payload_data,
	}
	if agent_id is not None:
		event_data["agent_id"] = str(agent_id)
	return event_data


def shortcut_notification_icon_url(
	asset: ManifestAssetSettings,
	filename: str,
) -> str | None:
	"""resolve a PWA shortcut asset URL for notification payloads."""
	frontend = (
		str(settings.branding.public_frontend_origin).rstrip("/")
		if settings.branding.public_frontend_origin
		else ""
	)
	cdn = (
		str(settings.branding.public_cdn_origin).rstrip("/")
		if settings.branding.public_cdn_origin
		else None
	)
	return resolve_asset_source(
		asset.source,
		asset.url,
		app_url(frontend, f"/shortcuts/{filename}"),
		cdn_asset_url(cdn, STATIC_ASSET_PATH, "shortcuts", filename) if cdn else None,
	)


def _notification_expires_at(now: datetime) -> datetime | None:
	"""resolve notification expiration from admin settings."""
	ttl_seconds = settings.notifications.notification_ttl_seconds
	if ttl_seconds is not None:
		return now + timedelta(seconds=ttl_seconds)
	return None


def _not_expired_filter(now: datetime) -> ColumnElement[bool]:
	return or_(Notification.expires_at.is_(None), Notification.expires_at > now)


def _is_expired(notification: Notification, now: datetime | None = None) -> bool:
	if notification.expires_at is None:
		return False
	return notification.expires_at <= (now or datetime.now(tz=UTC))


async def _get_notification(
	notification_id: str,
	session: AsyncSession,
	principal: Principal,
) -> Notification:
	"""return one notification visible to the principal."""
	stmt = (
		select(Notification)
		.options(selectinload(Notification.event))
		.where(Notification.id == notification_id)
		.where(_not_expired_filter(datetime.now(tz=UTC)))
	)
	if not principal.is_admin:
		stmt = stmt.where(Notification.user_id == principal.user.id)
	result = await session.execute(stmt)
	notification = result.scalars().one_or_none()
	if not notification:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="notification not found",
		)
	return notification


async def list_user_notifications(
	session: AsyncSession,
	principal: Principal,
	user_id: TypeID,
	filters: NotificationListFilters | None = None,
) -> list[Notification]:
	"""return visible notifications for a user."""
	if not principal.is_admin and user_id != principal.user_id:
		raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
	notification_filters = filters or NotificationListFilters()

	stmt = (
		select(Notification)
		.options(selectinload(Notification.event))
		.where(Notification.user_id == user_id)
		.where(Notification.dismissed.is_(False))
		.where(_not_expired_filter(datetime.now(tz=UTC)))
		.order_by(Notification.created_at.desc())
	)

	if notification_filters.only_unread:
		stmt = stmt.where(Notification.read_at.is_(None))

	result = await session.execute(stmt.limit(100))
	return list(result.scalars().all())


async def create_notifications(
	session: AsyncSession,
	payload: NotificationPayload,
	user_ids: list[TypeID],
	event_type: str = EventType.NOTIFICATION_CUSTOM,
	agent_id: TypeID | None = None,
) -> list[Notification]:
	"""create durable notification(s) and their live event signals.


	notifications are the durable, self-contained inbox and push payload.
	events are the live/replay signal that points at the notification and carries
	the same display projection for clients that are already connected.
	"""
	action_items = _action_data(payload.actions)
	now = datetime.now(tz=UTC)
	expires_at = _notification_expires_at(now)
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
		notification_id = new_typeid("notif")
		event = Event(
			id=new_typeid("event"),
			scope=EventScope.USER,
			scope_id=uid,
			type=event_type,
			data=_event_data(
				payload,
				action_items,
				expires_at,
				notification_id,
				agent_id,
			),
			user_id=uid,
		)
		session.add(event)
		await session.flush()

		notification = Notification(
			id=notification_id,
			user_id=uid,
			event_id=event.id,
			title=payload.title,
			body=payload.body,
			icon_url=payload.icon_url,
			image_url=payload.image_url,
			badge_url=payload.badge_url,
			action_url=payload.action_url,
			tag=payload.tag,
			data=payload.data,
			actions=action_items,
			require_interaction=payload.require_interaction,
			silent=payload.silent,
			renotify=payload.renotify,
			expires_at=expires_at,
		)
		session.add(notification)

		notifications.append(notification)

	await session.commit()

	# refresh and broadcast each
	for notif in notifications:
		await session.refresh(notif, attribute_names=["event"])
		await deliver_notification(notif)

	return notifications


async def deliver_notification(notification: Notification) -> None:
	"""deliver one durable notification to live and background channels."""
	if _is_expired(notification):
		return
	await fanout_event(notification.event)
	schedule_notification_push(notification)


async def mark_notification_read(
	notification_id: str,
	session: AsyncSession,
	principal: Principal,
) -> Notification:
	"""mark one notification read for the principal."""
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
	"""dismiss one notification for the principal."""
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
	"""mark all unread notifications as read for a user. returns count updated."""
	if not principal.is_admin and str(user_id) != str(principal.user.id):
		raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")

	to_update = await session.scalar(
		select(func.count(Notification.id)).where(
			Notification.user_id == user_id,
			Notification.read_at.is_(None),
			_not_expired_filter(datetime.now(tz=UTC)),
		)
	)
	if int(to_update or 0) == 0:
		return 0

	stmt = (
		update(Notification)
		.where(Notification.user_id == user_id)
		.where(Notification.read_at.is_(None))
		.where(_not_expired_filter(datetime.now(tz=UTC)))
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
	"""delete a notification."""
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


async def upsert_push_subscription(
	session: AsyncSession,
	principal: Principal,
	user_id: TypeID,
	client_id: TypeID,
	payload: NotificationPushSubscriptionCreate,
) -> NotificationPushSubscription:
	"""create or refresh one browser web push subscription."""
	client = await _get_push_client(session, principal, user_id, client_id)

	stmt = select(NotificationPushSubscription).where(
		NotificationPushSubscription.endpoint == payload.endpoint
	)
	result = await session.execute(stmt)
	subscription = result.scalars().one_or_none()

	if subscription is None:
		subscription = NotificationPushSubscription(
			client_id=client.id,
			endpoint=payload.endpoint,
			p256dh=payload.keys.p256dh,
			auth=payload.keys.auth,
			expires_at=payload.expires_at,
			last_used_at=datetime.now(tz=UTC),
		)
		session.add(subscription)
	else:
		subscription.client_id = client.id
		subscription.p256dh = payload.keys.p256dh
		subscription.auth = payload.keys.auth
		subscription.expires_at = payload.expires_at
		subscription.last_used_at = datetime.now(tz=UTC)

	await session.commit()
	await session.refresh(subscription)
	return subscription


async def unregister_push_subscription(
	session: AsyncSession,
	principal: Principal,
	user_id: TypeID,
	client_id: TypeID,
	payload: NotificationPushSubscriptionDelete,
) -> None:
	"""delete a user client's web push subscription by endpoint."""
	client = await _get_push_client(session, principal, user_id, client_id)
	stmt = select(NotificationPushSubscription).where(
		NotificationPushSubscription.client_id == client.id,
		NotificationPushSubscription.endpoint == payload.endpoint,
	)
	result = await session.execute(stmt)
	subscription = result.scalars().one_or_none()
	if subscription is not None:
		await session.delete(subscription)
		await session.commit()


async def list_push_subscriptions(
	session: AsyncSession,
	principal: Principal,
	user_id: TypeID,
	client_id: TypeID,
) -> list[NotificationPushSubscription]:
	"""list web push subscriptions registered by a user client."""
	client = await _get_push_client(session, principal, user_id, client_id)
	stmt = (
		select(NotificationPushSubscription)
		.where(NotificationPushSubscription.client_id == client.id)
		.order_by(NotificationPushSubscription.created_at.desc())
	)
	result = await session.execute(stmt)
	return list(result.scalars().all())


async def delete_push_subscription(
	user_id: TypeID,
	client_id: TypeID,
	subscription_id: TypeID,
	session: AsyncSession,
	principal: Principal,
) -> None:
	"""delete a web push subscription visible to the principal."""
	client = await _get_push_client(session, principal, user_id, client_id)
	stmt = select(NotificationPushSubscription).where(
		NotificationPushSubscription.id == subscription_id,
		NotificationPushSubscription.client_id == client.id,
	)
	result = await session.execute(stmt)
	subscription = result.scalars().one_or_none()
	if subscription is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="push subscription not found",
		)
	await session.delete(subscription)
	await session.commit()


async def _get_push_client(
	session: AsyncSession,
	principal: Principal,
	user_id: TypeID,
	client_id: TypeID,
) -> UserClient:
	"""return the user client that owns push subscriptions for a route."""
	if not principal.is_admin and user_id != principal.user_id:
		raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
	stmt = select(UserClient).where(
		UserClient.id == client_id,
		UserClient.user_id == user_id,
	)
	result = await session.execute(stmt)
	client = result.scalars().one_or_none()
	if client is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="client not found",
		)
	return client
