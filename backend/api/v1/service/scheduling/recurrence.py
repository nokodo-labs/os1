"""pure recurrence expansion helpers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dateutil.rrule import rruleset, rrulestr

from api.schemas.scheduled_item import Recurrence
from nokodo_ai.types import JSONObject


def recurrence_from_storage(value: JSONObject | Recurrence | None) -> Recurrence | None:
	"""parse a stored recurrence value."""
	if value is None:
		return None
	if isinstance(value, Recurrence):
		return value
	return Recurrence.model_validate(value)


def recurrence_to_storage(value: Recurrence | None) -> JSONObject | None:
	"""serialize a recurrence value for json storage."""
	if value is None:
		return None
	return {
		"rrule": list(value.rrule),
		"rdate": [item.isoformat() for item in value.rdate],
		"exdate": [item.isoformat() for item in value.exdate],
		"timezone": value.timezone,
	}


def recurrence_after_split(
	anchor_at: datetime,
	recurrence: Recurrence | JSONObject | None,
	split_at: datetime,
) -> Recurrence | None:
	"""return the remaining recurrence starting at a split occurrence."""
	parsed = recurrence_from_storage(recurrence)
	if parsed is None:
		return None
	series_timezone = _resolve_timezone(parsed.timezone)
	anchor = _ensure_aware(anchor_at, series_timezone)
	split = _ensure_aware(split_at, series_timezone)
	rules = [
		adjusted
		for rule in parsed.rrule
		if (adjusted := _rule_after_split(rule, anchor, split, series_timezone))
	]
	rdates = [
		_ensure_aware(rdate, series_timezone)
		for rdate in parsed.rdate
		if _ensure_aware(rdate, series_timezone) >= split
	]
	exdates = [
		_ensure_aware(exdate, series_timezone)
		for exdate in parsed.exdate
		if _ensure_aware(exdate, series_timezone) >= split
	]
	if not rules and not rdates:
		return None
	return Recurrence(
		rrule=rules,
		rdate=rdates,
		exdate=exdates,
		timezone=parsed.timezone,
	)


def expand_occurrence_starts(
	anchor_at: datetime,
	recurrence: Recurrence | JSONObject | None,
	window_start: datetime,
	window_end: datetime,
	duration: timedelta = timedelta(0),
	limit: int = 2000,
) -> list[datetime]:
	"""expand original occurrence starts that intersect a window."""
	parsed = recurrence_from_storage(recurrence)
	series_timezone = _resolve_timezone(parsed.timezone if parsed else None)
	anchor = _ensure_aware(anchor_at, series_timezone)
	start = _ensure_aware(window_start, series_timezone)
	end = _ensure_aware(window_end, series_timezone)
	if end < start:
		return []

	if parsed is None:
		return [anchor] if _overlaps(anchor, duration, start, end) else []

	rule_window_start = start - duration
	rule_set = rruleset()
	has_source = False

	for rule_text in parsed.rrule:
		parsed_rule = rrulestr(_normalize_rule(rule_text), dtstart=anchor)
		if isinstance(parsed_rule, rruleset):
			added_from_nested = 0
			for occurrence in parsed_rule.xafter(rule_window_start, inc=True):
				candidate = _ensure_aware(occurrence, series_timezone)
				if candidate > end:
					break
				rule_set.rdate(candidate)
				added_from_nested += 1
				if added_from_nested >= limit:
					break
		else:
			rule_set.rrule(parsed_rule)
		has_source = True

	for rdate in parsed.rdate:
		rule_set.rdate(_ensure_aware(rdate, series_timezone))
		has_source = True

	for exdate in parsed.exdate:
		rule_set.exdate(_ensure_aware(exdate, series_timezone))

	if not has_source:
		return []

	unique: dict[datetime, None] = {}
	for occurrence in rule_set.xafter(rule_window_start, inc=True):
		candidate = _ensure_aware(occurrence, series_timezone)
		if candidate > end:
			break
		if _overlaps(candidate, duration, start, end):
			unique[candidate] = None
		if len(unique) >= limit:
			break
	return sorted(unique)


def occurrence_exists(
	anchor_at: datetime,
	recurrence: Recurrence | JSONObject | None,
	original_occurrence_at: datetime,
) -> bool:
	"""check whether an original occurrence belongs to a series."""
	start = original_occurrence_at - timedelta(seconds=1)
	end = original_occurrence_at + timedelta(seconds=1)
	return any(
		item == original_occurrence_at
		for item in expand_occurrence_starts(anchor_at, recurrence, start, end)
	)


def _normalize_rule(rule_text: str) -> str:
	rule = rule_text.strip()
	return rule if rule.upper().startswith("RRULE:") else f"RRULE:{rule}"


def _rule_after_split(
	rule_text: str,
	anchor_at: datetime,
	split_at: datetime,
	timezone: ZoneInfo | None,
) -> str | None:
	count = _rule_count(rule_text)
	if count is None:
		return rule_text
	parsed_rule = rrulestr(_normalize_rule(rule_text), dtstart=anchor_at)
	window_end = split_at - timedelta(microseconds=1)
	if window_end < anchor_at:
		seen_before_split = 0
	else:
		seen_before_split = len(
			[
				_ensure_aware(occurrence, timezone)
				for occurrence in parsed_rule.between(anchor_at, window_end, inc=True)
			]
		)
	remaining = count - seen_before_split
	if remaining <= 0:
		return None
	return _replace_rule_count(rule_text, remaining)


def _rule_count(rule_text: str) -> int | None:
	for part in _rule_body(rule_text).split(";"):
		name, sep, value = part.partition("=")
		if sep and name.upper() == "COUNT":
			return int(value)
	return None


def _replace_rule_count(rule_text: str, count: int) -> str:
	prefix = "RRULE:" if rule_text.strip().upper().startswith("RRULE:") else ""
	parts = []
	for part in _rule_body(rule_text).split(";"):
		name, sep, _value = part.partition("=")
		parts.append(f"COUNT={count}" if sep and name.upper() == "COUNT" else part)
	return f"{prefix}{';'.join(parts)}"


def _rule_body(rule_text: str) -> str:
	rule = rule_text.strip()
	return rule[6:] if rule.upper().startswith("RRULE:") else rule


def _resolve_timezone(timezone: str | None) -> ZoneInfo | None:
	if not timezone:
		return None
	try:
		return ZoneInfo(timezone)
	except ZoneInfoNotFoundError:
		return None


def _ensure_aware(value: datetime, timezone: ZoneInfo | None) -> datetime:
	if value.tzinfo is None:
		return value.replace(tzinfo=timezone or UTC)
	return value.astimezone(timezone) if timezone else value.astimezone(UTC)


def _overlaps(
	occurrence_start: datetime,
	duration: timedelta,
	window_start: datetime,
	window_end: datetime,
) -> bool:
	occurrence_end = occurrence_start + duration
	return occurrence_start <= window_end and occurrence_end >= window_start
