"""Web Push delivery helpers."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from cryptography.hazmat.primitives import serialization
from py_vapid import Vapid, b64urlencode
from pywebpush import WebPushException, webpush
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.database import async_session_local
from api.local_tasks import create_background_task
from api.models.notification import Notification, NotificationPushSubscription
from api.models.user import User
from api.models.user_client import UserClient
from api.schemas.preferences import NotificationPreferences
from api.settings import settings
from nokodo_ai.types.json import JSONObject
from nokodo_ai.utils.typeid import TypeID


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class VapidKeypair:
	"""browser public key and server private key for Web Push."""

	public_key: str
	private_key: str


def generate_vapid_keypair() -> VapidKeypair:
	"""generate a browser-ready VAPID key pair with py_vapid."""
	vapid = Vapid()
	vapid.generate_keys()
	public_bytes = vapid.public_key.public_bytes(
		serialization.Encoding.X962,
		serialization.PublicFormat.UncompressedPoint,
	)
	return VapidKeypair(
		public_key=b64urlencode(public_bytes),
		private_key=vapid.private_pem().decode("utf-8"),
	)


def _web_push_configured() -> bool:
	"""return whether server-side Web Push delivery can run."""
	notification_settings = settings.notifications
	return bool(
		notification_settings.web_push_enabled
		and notification_settings.vapid_public_key
		and notification_settings.vapid_private_key
	)


def schedule_notification_push(notification: Notification) -> None:
	"""schedule background push delivery for a durable notification."""
	if not _web_push_configured():
		return
	if notification.silent is True:
		return
	create_background_task(
		send_notification_push(notification.id),
		name=f"notification_push:{notification.id}",
	)


async def send_notification_push(notification_id: TypeID) -> None:
	"""send one notification through Web Push to active subscriptions."""
	if not _web_push_configured():
		return
	async with async_session_local() as session:
		notification = await _load_notification(session, notification_id)
		if notification is None:
			return
		if notification.silent is True:
			return
		if _user_disables_push(notification.user):
			return

		now = datetime.now(tz=UTC)
		ttl = _push_ttl(notification, now)
		if ttl is None:
			return
		stmt = (
			select(NotificationPushSubscription)
			.join(NotificationPushSubscription.client)
			.where(UserClient.user_id == notification.user_id)
		)
		result = await session.execute(stmt)
		subscriptions = list(result.scalars().all())
		payload = json.dumps(_notification_payload(notification))

		for subscription in subscriptions:
			if subscription.expires_at is not None and subscription.expires_at <= now:
				await session.delete(subscription)
				continue
			await _send_subscription(session, subscription, payload, ttl)

		await session.commit()


async def _load_notification(
	session: AsyncSession,
	notification_id: TypeID,
) -> Notification | None:
	stmt = (
		select(Notification)
		.options(selectinload(Notification.user))
		.where(Notification.id == notification_id)
	)
	result = await session.execute(stmt)
	return result.scalars().one_or_none()


def _user_disables_push(user: User) -> bool:
	preferences = user.prefs.notifications
	if not isinstance(preferences, NotificationPreferences):
		return False
	return preferences.enabled is False or preferences.push_enabled is False


def _notification_payload(notification: Notification) -> JSONObject:
	data = dict(notification.data or {})
	data["notification_id"] = str(notification.id)
	if notification.action_url:
		data["action_url"] = notification.action_url
	if notification.event_id:
		data["event_id"] = str(notification.event_id)

	payload: JSONObject = {
		"id": str(notification.id),
		"title": notification.title,
		"body": notification.body,
		"icon_url": notification.icon_url,
		"image_url": notification.image_url,
		"badge_url": notification.badge_url,
		"action_url": notification.action_url,
		"tag": notification.tag,
		"data": data,
		"actions": notification.actions or [],
		"require_interaction": notification.require_interaction,
		"silent": notification.silent,
		"renotify": notification.renotify,
		"expires_at": notification.expires_at.isoformat()
		if notification.expires_at is not None
		else None,
	}
	return payload


def _push_ttl(notification: Notification, now: datetime) -> int | None:
	configured_ttl = settings.notifications.web_push_ttl_seconds
	if notification.expires_at is None:
		return configured_ttl
	seconds_remaining = int((notification.expires_at - now).total_seconds())
	if seconds_remaining <= 0:
		return None
	return min(configured_ttl, seconds_remaining)


async def _send_subscription(
	session: AsyncSession,
	subscription: NotificationPushSubscription,
	payload: str,
	ttl: int,
) -> None:
	notification_settings = settings.notifications
	private_key = notification_settings.vapid_private_key
	if not private_key:
		return
	subscription_info: dict[str, str | bytes | dict[str, str | bytes]] = {
		"endpoint": subscription.endpoint,
		"keys": {
			"p256dh": subscription.p256dh,
			"auth": subscription.auth,
		},
	}
	vapid_claims: dict[str, str | int] = {"sub": notification_settings.vapid_subject}
	try:
		await asyncio.to_thread(
			webpush,
			subscription_info=subscription_info,
			data=payload,
			vapid_private_key=private_key,
			vapid_claims=vapid_claims,
			ttl=ttl,
		)
		subscription.last_used_at = datetime.now(tz=UTC)
	except WebPushException as exc:
		status_code = _response_status_code(exc)
		if status_code in {404, 410}:
			await session.delete(subscription)
		else:
			logger.warning(
				"web push delivery failed for subscription %s: %s",
				subscription.id,
				exc,
			)


def _response_status_code(exc: WebPushException) -> int | None:
	response = getattr(exc, "response", None)
	return getattr(response, "status_code", None)
