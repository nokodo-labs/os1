"""calendar scheduled item cache helpers."""

from __future__ import annotations

from datetime import datetime

from api.redis import cache
from api.schemas.scheduled_item import ScheduledItem
from api.settings import settings
from nokodo_ai.utils.typeid import TypeID


def _window_key(start_at: datetime, end_at: datetime) -> str:
	return f"{start_at.isoformat()}:{end_at.isoformat()}"


def _calendar_tag(calendar_id: TypeID) -> str:
	return f"scheduled-items:calendar:{str(calendar_id)}"


def _calendar_event_tag(event_id: TypeID) -> str:
	return f"scheduled-items:calendar-event:{str(event_id)}"


def _calendar_event_cache_key(
	event_id: TypeID,
	start_at: datetime,
	end_at: datetime,
) -> str:
	return ":".join(
		(
			"scheduled-items",
			"calendar-event",
			str(event_id),
			_window_key(start_at, end_at),
		)
	)


async def get_cached_calendar_event_items(
	event_id: TypeID,
	start_at: datetime,
	end_at: datetime,
) -> list[ScheduledItem] | None:
	value = await cache.get(_calendar_event_cache_key(event_id, start_at, end_at))
	if not isinstance(value, list):
		return None
	try:
		return [ScheduledItem.model_validate(item) for item in value]
	except ValueError:
		return None


async def set_cached_calendar_event_items(
	event_id: TypeID,
	calendar_id: TypeID,
	start_at: datetime,
	end_at: datetime,
	items: list[ScheduledItem],
) -> None:
	await cache.set(
		_calendar_event_cache_key(event_id, start_at, end_at),
		[item.model_dump(mode="json") for item in items],
		ttl=settings.cache.scheduled_items_ttl_seconds,
		tags=[_calendar_event_tag(event_id), _calendar_tag(calendar_id)],
	)


async def invalidate_calendar_scheduled_items(calendar_id: TypeID) -> None:
	await cache.invalidate_tag(_calendar_tag(calendar_id))


async def invalidate_calendar_event_scheduled_items(event_id: TypeID) -> None:
	await cache.invalidate_tag(_calendar_event_tag(event_id))
