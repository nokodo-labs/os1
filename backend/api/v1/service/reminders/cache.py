"""reminder scheduled item cache helpers."""

from __future__ import annotations

from datetime import datetime

from api.redis import cache
from api.schemas.scheduled_item import ScheduledItem
from api.settings import settings
from nokodo_ai.utils.typeid import TypeID


def _window_key(start_at: datetime, end_at: datetime) -> str:
	return f"{start_at.isoformat()}:{end_at.isoformat()}"


def _reminder_list_tag(list_id: TypeID) -> str:
	return f"scheduled-items:reminder-list:{str(list_id)}"


def _reminder_tag(reminder_id: TypeID) -> str:
	return f"scheduled-items:reminder:{str(reminder_id)}"


def _reminder_cache_key(
	reminder_id: TypeID,
	start_at: datetime,
	end_at: datetime,
	include_completed: bool,
) -> str:
	return ":".join(
		(
			"scheduled-items",
			"reminder",
			str(reminder_id),
			_window_key(start_at, end_at),
			"completed" if include_completed else "pending",
		)
	)


async def get_cached_reminder_items(
	reminder_id: TypeID,
	start_at: datetime,
	end_at: datetime,
	include_completed: bool,
) -> list[ScheduledItem] | None:
	value = await cache.get(
		_reminder_cache_key(reminder_id, start_at, end_at, include_completed)
	)
	if not isinstance(value, list):
		return None
	try:
		return [ScheduledItem.model_validate(item) for item in value]
	except ValueError:
		return None


async def set_cached_reminder_items(
	reminder_id: TypeID,
	list_id: TypeID,
	start_at: datetime,
	end_at: datetime,
	include_completed: bool,
	items: list[ScheduledItem],
) -> None:
	await cache.set(
		_reminder_cache_key(reminder_id, start_at, end_at, include_completed),
		[item.model_dump(mode="json") for item in items],
		ttl=settings.cache.scheduled_items_ttl_seconds,
		tags=[_reminder_tag(reminder_id), _reminder_list_tag(list_id)],
	)


async def invalidate_reminder_list_scheduled_items(list_id: TypeID) -> None:
	await cache.invalidate_tag(_reminder_list_tag(list_id))


async def invalidate_reminder_scheduled_items(reminder_id: TypeID) -> None:
	await cache.invalidate_tag(_reminder_tag(reminder_id))
