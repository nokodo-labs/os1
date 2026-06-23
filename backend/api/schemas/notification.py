"""notification schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from api.schemas.common import ORMModel, TimestampedModel
from api.schemas.event import Event
from nokodo_ai.types.json import JSONObject
from nokodo_ai.utils.typeid import TypeID


class NotificationAction(BaseModel):
	"""action button shown by capable notification surfaces."""

	action: str = Field(min_length=1, max_length=64)
	title: str = Field(min_length=1, max_length=80)
	icon_url: str | None = Field(default=None, max_length=2048)

	@field_validator("action", "title", mode="before")
	@classmethod
	def normalize_required_text(cls, value: object) -> object:
		if isinstance(value, str):
			text = value.strip()
			if not text:
				raise ValueError("text is required")
			return text
		return value

	@field_validator("icon_url", mode="before")
	@classmethod
	def normalize_optional_text(cls, value: object) -> object:
		if isinstance(value, str):
			return value.strip() or None
		return value


class NotificationPayload(BaseModel):
	"""user-facing notification payload."""

	title: str = Field(min_length=1, max_length=200)
	body: str | None = Field(default=None, max_length=4000)
	icon_url: str | None = Field(default=None, max_length=2048)
	image_url: str | None = Field(default=None, max_length=2048)
	badge_url: str | None = Field(default=None, max_length=2048)
	action_url: str | None = Field(default=None, max_length=2048)
	tag: str | None = Field(default=None, max_length=128)
	data: JSONObject = Field(default_factory=dict)
	actions: list[NotificationAction] = Field(default_factory=list, max_length=4)
	require_interaction: bool | None = None
	silent: bool | None = None
	renotify: bool | None = None

	@field_validator("title", mode="before")
	@classmethod
	def normalize_title(cls, value: object) -> object:
		if isinstance(value, str):
			text = value.strip()
			if not text:
				raise ValueError("title is required")
			return text
		return value

	@field_validator(
		"body",
		"icon_url",
		"image_url",
		"badge_url",
		"action_url",
		"tag",
		mode="before",
	)
	@classmethod
	def normalize_optional_text(cls, value: object) -> object:
		if isinstance(value, str):
			return value.strip() or None
		return value


class NotificationBase(ORMModel):
	"""mutable notification fields."""

	user_id: TypeID
	event_id: TypeID
	title: str
	body: str | None = None
	icon_url: str | None = None
	image_url: str | None = None
	badge_url: str | None = None
	action_url: str | None = None
	tag: str | None = None
	data: JSONObject = Field(default_factory=dict)
	actions: list[NotificationAction] = Field(default_factory=list, max_length=4)
	require_interaction: bool | None = None
	silent: bool | None = None
	renotify: bool | None = None
	dismissed: bool = False
	expires_at: datetime | None = None


class Notification(NotificationBase, TimestampedModel):
	"""response schema."""

	id: TypeID
	read_at: datetime | None = None
	event: Event | None = None


class NotificationCreate(NotificationPayload):
	"""request schema for creating notification(s)."""

	user_ids: list[TypeID] = Field(min_length=1, max_length=100)


class NotificationListFilters(BaseModel):
	"""filters for listing notifications."""

	only_unread: bool = False


class NotificationPushSubscriptionKeys(BaseModel):
	"""browser-provided web push encryption keys."""

	p256dh: str = Field(min_length=1, max_length=4096)
	auth: str = Field(min_length=1, max_length=4096)


class NotificationPushSubscriptionCreate(BaseModel):
	"""request schema for registering a web push subscription."""

	endpoint: str = Field(min_length=1, max_length=4096)
	keys: NotificationPushSubscriptionKeys
	expires_at: datetime | None = None


class NotificationPushSubscriptionDelete(BaseModel):
	"""request schema for unregistering a web push subscription."""

	endpoint: str = Field(min_length=1, max_length=4096)


class NotificationPushSubscription(TimestampedModel):
	"""registered web push subscription response."""

	id: TypeID
	client_id: TypeID
	endpoint: str
	expires_at: datetime | None = None
	last_used_at: datetime | None = None
