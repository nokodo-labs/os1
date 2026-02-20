"""Prompt rendering, variable building, and validation with Jinja2.

this module is the single entry point for all prompt-related operations:
- jinja2 template rendering with composable includes
- runtime prompt variable building from user + client context
- full agent instruction rendering via render_agent_instructions()
- prompt validation for CRUD operations
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from jinja2 import DictLoader, Environment, StrictUndefined, TemplateNotFound
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.prompt import Prompt
from api.models.user import User
from api.schemas.preferences import (
	AccountPreferences,
	AIPreferences,
	UserPreferences,
)
from nokodo_ai.utils.typeid import TypeID


if TYPE_CHECKING:
	from api.schemas.runs import ClientContext


_PROMPT_REF_RE = re.compile(r"{{\s*PROMPTS\.([a-zA-Z0-9-_]+)\s*}}")
_INCLUDE_RE = re.compile(r"{%-?\s*include\s+['\"]([a-zA-Z0-9-_/]+)['\"]\s*-?%}")
_MAX_DEPTH = 50


def normalize_command(command: str) -> str:
	"""strip any leading slash and spaces for consistent lookup keys."""
	return command.lstrip("/").replace(" ", "-")


def _prepare_template(text: str) -> str:
	"""Convert legacy PROMPTS.* placeholders to Jinja include directives."""
	return _PROMPT_REF_RE.sub(lambda m: f'{{% include "{m.group(1)}" %}}', text)


def _collect_includes(text: str) -> set[str]:
	"""Find referenced prompts via Jinja include or legacy PROMPTS.* syntax."""
	names = set(_PROMPT_REF_RE.findall(text))
	names |= {match for match in _INCLUDE_RE.findall(text)}
	return {normalize_command(name) for name in names}


class PromptValidationError(ValueError):
	"""Raised when prompt references are invalid."""


def _validate_graph(
	prompt_map: dict[str, str],
	start_key: str,
	*,
	max_depth: int = _MAX_DEPTH,
) -> None:
	errors: list[str] = []

	def visit(current: str, path: list[str], depth: int) -> None:
		if depth > max_depth:
			errors.append(
				f"nesting depth ({depth}) exceeds maximum allowed ({max_depth})"
			)
			return
		if current in path:
			errors.append("circular dependency detected")
			return
		content = prompt_map.get(current)
		if content is None:
			errors.append(f"referenced prompt '{current}' does not exist")
			return
		next_path = path + [current]
		for ref in _collect_includes(content):
			visit(ref, next_path, depth + 1)

	visit(start_key, [], 0)
	if errors:
		raise PromptValidationError("; ".join(dict.fromkeys(errors)))


def _build_env(prompt_map: dict[str, str]) -> Environment:
	return Environment(
		loader=DictLoader(prompt_map),
		autoescape=False,
		undefined=StrictUndefined,
		keep_trailing_newline=True,
	)


def render_prompt_from_map(
	prompt_map: dict[str, str],
	*,
	command: str,
	variables: dict[str, object] | None = None,
	max_depth: int = _MAX_DEPTH,
) -> str:
	key = normalize_command(command)
	prepared_map = {k: _prepare_template(v) for k, v in prompt_map.items()}
	_validate_graph(prepared_map, key, max_depth=max_depth)
	env = _build_env(prepared_map)
	try:
		template = env.get_template(key)
	except TemplateNotFound as exc:
		raise PromptValidationError(
			f"referenced prompt '{key}' does not exist"
		) from exc
	return template.render(**(variables or {}))


async def render_prompt_from_db(
	session: AsyncSession,
	*,
	command: str,
	variables: dict[str, object] | None = None,
	max_depth: int = _MAX_DEPTH,
) -> str:
	result = await session.execute(select(Prompt.command, Prompt.content))
	prompt_map = {normalize_command(cmd): content for cmd, content in result.all()}
	return render_prompt_from_map(
		prompt_map,
		command=command,
		variables=variables,
		max_depth=max_depth,
	)


async def render_inline_with_prompts(
	session: AsyncSession,
	*,
	text: str,
	variables: dict[str, object] | None = None,
	max_depth: int = _MAX_DEPTH,
) -> str:
	"""Render an inline template that may include DB prompts."""
	result = await session.execute(select(Prompt.command, Prompt.content))
	prompt_map = {normalize_command(cmd): content for cmd, content in result.all()}
	inline_key = "__inline__"
	prompt_map[inline_key] = text
	return render_prompt_from_map(
		prompt_map,
		command=inline_key,
		variables=variables,
		max_depth=max_depth,
	)


def validate_prompt_content(
	*,
	all_prompts: Iterable[Prompt],
	command: str,
	content: str,
	max_depth: int = _MAX_DEPTH,
	self_id: TypeID | None = None,
) -> None:
	prompt_map: dict[str, str] = {}
	for p in all_prompts:
		if self_id is not None and str(p.id) == str(self_id):
			continue
		prompt_map[normalize_command(p.command)] = p.content
	prompt_map[normalize_command(command)] = content
	prepared_map = {k: _prepare_template(v) for k, v in prompt_map.items()}
	_validate_graph(prepared_map, normalize_command(command), max_depth=max_depth)


def http_error_from_validation(err: PromptValidationError) -> HTTPException:
	return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))


# runtime prompt variable building


def _parse_preferences(user: User) -> UserPreferences:
	"""safely parse user preferences json into the typed schema."""
	raw = user.preferences or {}
	try:
		return UserPreferences.model_validate(raw)
	except Exception:
		return UserPreferences()


def _resolve_bio(prefs: UserPreferences) -> str:
	"""resolve the effective bio respecting the useAccountBio toggle."""
	ai = prefs.ai or AIPreferences()
	account = prefs.account or AccountPreferences()
	if ai.use_account_bio:
		return account.bio or ""
	return ai.bio or ""


def _compute_age(birth_date_str: str | None, now: datetime) -> str:
	"""compute age in years from an ISO date string, or empty string."""
	if not birth_date_str:
		return ""
	try:
		parts = birth_date_str.split("-")
		birth = datetime(int(parts[0]), int(parts[1]), int(parts[2]), tzinfo=UTC)
		age = now.year - birth.year
		if (now.month, now.day) < (birth.month, birth.day):
			age -= 1
		return str(max(0, age))
	except (ValueError, IndexError):
		return ""


def _tz_label(dt: datetime) -> str:
	"""build a human-readable timezone label for a datetime."""
	if dt.tzinfo is None:
		return ""
	abbr = dt.strftime("%Z") or ""
	offset = dt.utcoffset()
	if offset is not None:
		total = int(offset.total_seconds())
		sign = "+" if total >= 0 else "-"
		h, rem = divmod(abs(total), 3600)
		m = rem // 60
		offset_str = f"UTC{sign}{h:02d}:{m:02d}"
	else:
		offset_str = ""
	if abbr and offset_str:
		return f"{abbr} ({offset_str})"
	return abbr or offset_str


def _build_date_set(dt: datetime, prefix: str) -> dict[str, object]:
	"""build a full set of date/time variables for a given datetime and prefix."""
	tz_label = _tz_label(dt)
	tz_suffix = f" {tz_label}" if tz_label else ""
	return {
		f"{prefix}_date": dt.strftime("%Y-%m-%d"),
		f"{prefix}_time": dt.strftime("%H:%M") + tz_suffix,
		f"{prefix}_datetime": dt.isoformat(),
		f"{prefix}_day": dt.strftime("%A"),
		f"{prefix}_date_full": dt.strftime("%B %d, %Y"),
		f"{prefix}_date_short": dt.strftime("%Y-%m-%d"),
		f"{prefix}_date_weekday": dt.strftime("%A, %B %d"),
		f"{prefix}_date_weekday_full": dt.strftime("%A, %B %d, %Y"),
		f"{prefix}_date_month_day": dt.strftime("%B %d"),
		f"{prefix}_time_12h": dt.strftime("%I:%M %p").lstrip("0") + tz_suffix,
		f"{prefix}_time_24h": dt.strftime("%H:%M") + tz_suffix,
		f"{prefix}_time_seconds": dt.strftime("%H:%M:%S") + tz_suffix,
		f"{prefix}_datetime_full": dt.strftime("%A, %B %d, %Y at %I:%M %p").replace(
			" 0", " "
		)
		+ tz_suffix,
		f"{prefix}_datetime_short": dt.strftime("%Y-%m-%d %H:%M") + tz_suffix,
		f"{prefix}_timezone": tz_label or _NA,
	}


_NA = "N/A"


def _tz_display(dt: datetime) -> dict[str, object]:
	"""build timezone display variants for a timezone-aware datetime."""
	tz = dt.tzinfo
	if tz is None:
		return {
			"user_timezone": _NA,
			"user_timezone_abbr": _NA,
			"user_utc_offset": _NA,
			"user_timezone_name": _NA,
		}
	offset = dt.utcoffset()
	if offset is not None:
		total_seconds = int(offset.total_seconds())
		sign = "+" if total_seconds >= 0 else "-"
		hours, remainder = divmod(abs(total_seconds), 3600)
		minutes = remainder // 60
		utc_offset = f"UTC{sign}{hours:02d}:{minutes:02d}"
	else:
		utc_offset = _NA

	tz_name = str(tz)
	tz_abbr = dt.strftime("%Z") or _NA

	return {
		"user_timezone": tz_name,
		"user_timezone_abbr": tz_abbr,
		"user_utc_offset": utc_offset,
		"user_timezone_name": tz_name,
	}


def _build_date_variables(
	client_context: ClientContext | None,
) -> dict[str, object]:
	"""build date/time variables for both server and user timezone."""
	utc_now = datetime.now(UTC)
	variables: dict[str, object] = {}

	# server time (UTC) - always available
	variables.update(_build_date_set(utc_now, "server"))

	# user time - only if client provides timezone
	user_now: datetime | None = None
	if client_context and client_context.timezone:
		try:
			tz = ZoneInfo(client_context.timezone)
			user_now = utc_now.astimezone(tz)
		except (KeyError, ValueError):
			pass

	if user_now is not None:
		variables.update(_build_date_set(user_now, "current"))
		variables.update(_tz_display(user_now))
	else:
		# fall back to server time for current_* variables
		variables.update(_build_date_set(utc_now, "current"))
		variables.update(
			{
				"user_timezone": _NA,
				"user_timezone_abbr": _NA,
				"user_utc_offset": _NA,
				"user_timezone_name": _NA,
			}
		)

	return variables


def _build_location_variables(
	client_context: ClientContext | None,
) -> dict[str, object]:
	"""build location variables from client context."""
	if (
		client_context
		and client_context.latitude is not None
		and client_context.longitude is not None
	):
		return {
			"client_latitude": str(client_context.latitude),
			"client_longitude": str(client_context.longitude),
			"client_location": client_context.location_label or _NA,
		}
	return {
		"client_latitude": _NA,
		"client_longitude": _NA,
		"client_location": _NA,
	}


def _resolve_now(client_context: ClientContext | None) -> datetime:
	"""resolve the current time, preferring the client's timezone if available."""
	utc_now = datetime.now(UTC)
	if client_context and client_context.timezone:
		try:
			tz = ZoneInfo(client_context.timezone)
			return utc_now.astimezone(tz)
		except (KeyError, ValueError):
			pass
	return utc_now


def build_prompt_variables(
	user: User | None = None,
	client_context: ClientContext | None = None,
) -> dict[str, object]:
	"""build the dict of always-available prompt template variables.

	these are injected into every jinja2 render call so prompts
	and system instructions can reference them without explicit wiring.

	args:
		user: the authenticated user, or none for anonymous context.
		client_context: optional device/environment data from the client.

	returns:
		flat dict of variable_name → value.
	"""
	now = _resolve_now(client_context)
	variables: dict[str, object] = _build_date_variables(client_context)

	# client context variables
	variables.update(
		{
			"client_timezone": (
				client_context.timezone
				if client_context and client_context.timezone
				else _NA
			),
			"client_language": (
				client_context.language
				if client_context and client_context.language
				else _NA
			),
			"client_os": (
				client_context.os if client_context and client_context.os else _NA
			),
			"client_browser": (
				client_context.browser
				if client_context and client_context.browser
				else _NA
			),
			"client_is_mobile": (
				client_context.is_mobile
				if client_context and client_context.is_mobile is not None
				else _NA
			),
			"client_pwa_installed": (
				client_context.pwa_installed
				if client_context and client_context.pwa_installed is not None
				else _NA
			),
		}
	)

	# location variables (from browser geolocation)
	variables.update(_build_location_variables(client_context))

	if user is None:
		variables.update(
			{
				"user_name": _NA,
				"user_email": _NA,
				"user_bio": _NA,
				"user_gender": _NA,
				"user_birth_date": _NA,
				"user_age": _NA,
				"user_custom_instructions": _NA,
				"ai_personality": _NA,
			}
		)
		return variables

	prefs = _parse_preferences(user)
	account = prefs.account or AccountPreferences()
	ai = prefs.ai or AIPreferences()
	birth_date = account.birth_date or ""
	age = _compute_age(birth_date, now)

	variables.update(
		{
			"user_name": user.display_name or user.email.split("@")[0],
			"user_email": user.email,
			"user_bio": _resolve_bio(prefs) or _NA,
			"user_gender": account.gender or _NA,
			"user_birth_date": birth_date or _NA,
			"user_age": age or _NA,
			"user_custom_instructions": ai.custom_instructions or _NA,
			"ai_personality": ai.personality or _NA,
		}
	)

	return variables


# unified agent instruction rendering


async def render_agent_instructions(
	session: AsyncSession,
	*,
	text: str,
	user: User | None = None,
	client_context: ClientContext | None = None,
) -> str:
	"""render agent system instructions with full context.

	this is the single entry point agents.py should call.
	it builds runtime variables from user + client context,
	loads prompt library from DB, and renders through jinja2.

	args:
		session: active database session.
		text: the raw system prompt template text.
		user: the authenticated user (or none).
		client_context: optional device/environment data from the client.

	returns:
		fully rendered instruction string.
	"""
	variables = build_prompt_variables(user, client_context)
	return await render_inline_with_prompts(
		session,
		text=text,
		variables=variables,
	)
