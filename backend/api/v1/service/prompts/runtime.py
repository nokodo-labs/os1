"""prompt rendering, variable building, and validation with Jinja2.

this module owns prompt template rendering, runtime variable building, agent
instruction rendering, and prompt reference validation.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, cast
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from jinja2 import DictLoader, Environment, StrictUndefined, TemplateNotFound
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.prompt import Prompt
from api.models.user import User
from api.schemas.common import MISSING, MissingType
from api.schemas.preferences import AccountPreferences, AIPreferences
from api.v1.service.prompts.cache import list_prompt_templates
from api.v1.service.prompts.external import render_external_prompt_content_map
from nokodo_ai.utils.typeid import TypeID


if TYPE_CHECKING:
	from api.schemas.runs import ClientContext


def _preference_value[T](value: T | MissingType, default: T) -> T:
	"""return a preference value or its default when missing."""
	if value is MISSING:
		return default
	return cast(T, value)


# sentinel markers for filter injection points.
# jinja2 renders {{ variable_name }} into these sentinels at template time.
# filters find-and-replace the sentinel with actual content.
# if the sentinel is absent from the rendered prompt, the filter is a no-op.
SENTINEL_USER_MEMORIES = "<<FILTER:user_memories>>"
SENTINEL_CHAT_CONTEXT = "<<FILTER:chat_context>>"
SENTINEL_CHAT_WINDOW_INFO = "<<FILTER:chat_window_info>>"
SENTINEL_CITATION_SOURCES = "<<FILTER:citation_sources>>"

_PROMPT_REF_RE = re.compile(r"{{\s*PROMPTS\.([a-zA-Z0-9-_]+)\s*}}")
_INCLUDE_RE = re.compile(r"{%-?\s*include\s+['\"]([a-zA-Z0-9-_/]+)['\"]\s*-?%}")
_MAX_DEPTH = 50


def normalize_command(command: str) -> str:
	"""strip any leading slash and spaces for consistent lookup keys."""
	return command.lstrip("/").replace(" ", "-")


def _prepare_template(text: str) -> str:
	"""convert legacy PROMPTS.* placeholders to Jinja include directives."""
	return _PROMPT_REF_RE.sub(lambda match: f'{{% include "{match.group(1)}" %}}', text)


def _collect_includes(text: str) -> set[str]:
	"""find referenced prompts via Jinja include or legacy PROMPTS.* syntax."""
	names = set(_PROMPT_REF_RE.findall(text))
	names |= {match for match in _INCLUDE_RE.findall(text)}
	return {normalize_command(name) for name in names}


class PromptValidationError(ValueError):
	"""raised when prompt references are invalid."""


def _validate_graph(
	prompt_map: dict[str, str],
	start_key: str,
	max_depth: int = _MAX_DEPTH,
) -> None:
	"""validate prompt include graph reachability and recursion limits."""
	errors: list[str] = []

	def visit(current: str, path: list[str], depth: int) -> None:
		"""walk reachable prompt references from one prompt key."""
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


def _finalize(value: object) -> object:
	"""Jinja2 finalize hook that renders None as an empty string."""
	if value is None:
		return ""
	return value


def _build_env(prompt_map: dict[str, str]) -> Environment:
	"""build a strict Jinja2 environment for prompt templates."""
	return Environment(
		loader=DictLoader(prompt_map),
		autoescape=False,
		undefined=StrictUndefined,
		finalize=_finalize,
		keep_trailing_newline=True,
	)


def render_prompt_from_map(
	prompt_map: dict[str, str],
	command: str,
	variables: dict[str, object] | None = None,
	max_depth: int = _MAX_DEPTH,
) -> str:
	"""render one prompt template from an already-loaded prompt map."""
	key = normalize_command(command)
	prepared_map = {key: _prepare_template(value) for key, value in prompt_map.items()}
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
	command: str,
	variables: dict[str, object] | None = None,
	max_depth: int = _MAX_DEPTH,
) -> str:
	"""render one prompt command using cached DB prompt templates."""
	prompt_map = await list_prompt_templates(session)
	external_prompts = await _render_referenced_external_prompts(
		session,
		prompt_map,
		normalize_command(command),
		max_depth=max_depth,
	)
	prompt_map.update(external_prompts)
	return render_prompt_from_map(
		prompt_map,
		command=command,
		variables=variables,
		max_depth=max_depth,
	)


async def render_inline_with_prompts(
	session: AsyncSession,
	text: str,
	variables: dict[str, object] | None = None,
	max_depth: int = _MAX_DEPTH,
) -> str:
	"""render an inline template that may include DB or external prompts."""
	prompt_map = await list_prompt_templates(session)
	inline_key = "__inline__"
	prompt_map[inline_key] = text
	external_prompts = await _render_referenced_external_prompts(
		session,
		prompt_map,
		inline_key,
		max_depth=max_depth,
	)
	prompt_map.update(external_prompts)
	return render_prompt_from_map(
		prompt_map,
		command=inline_key,
		variables=variables,
		max_depth=max_depth,
	)


def validate_prompt_content(
	all_prompts: Iterable[Prompt],
	command: str,
	content: str,
	max_depth: int = _MAX_DEPTH,
	self_id: TypeID | None = None,
	extra_prompt_map: dict[str, str] | None = None,
) -> None:
	"""validate that a prompt template references only available prompts."""
	prompt_map: dict[str, str] = {}
	for prompt in all_prompts:
		if self_id is not None and str(prompt.id) == str(self_id):
			continue
		prompt_map[normalize_command(prompt.command)] = prompt.content
	if extra_prompt_map:
		prompt_map.update(extra_prompt_map)
	prompt_map[normalize_command(command)] = content
	prepared_map = {key: _prepare_template(value) for key, value in prompt_map.items()}
	_validate_graph(prepared_map, normalize_command(command), max_depth=max_depth)


async def _render_referenced_external_prompts(
	session: AsyncSession,
	prompt_map: dict[str, str],
	start_key: str,
	max_depth: int,
) -> dict[str, str]:
	"""render external prompts referenced by a local prompt graph."""
	references = _collect_reachable_includes(prompt_map, start_key, max_depth=max_depth)
	references.add(start_key)
	return await render_external_prompt_content_map(session, references)


def _collect_reachable_includes(
	prompt_map: dict[str, str],
	start_key: str,
	max_depth: int,
) -> set[str]:
	"""collect include commands reachable from one prompt key."""
	prepared_map = {key: _prepare_template(value) for key, value in prompt_map.items()}
	references: set[str] = set()
	visited: set[str] = set()

	def visit(current: str, depth: int) -> None:
		"""walk local prompt includes while collecting referenced commands."""
		if depth > max_depth or current in visited:
			return
		visited.add(current)
		content = prepared_map.get(current)
		if content is None:
			return
		for ref in _collect_includes(content):
			references.add(ref)
			visit(ref, depth + 1)

	visit(start_key, 0)
	return references


def http_error_from_validation(err: PromptValidationError) -> HTTPException:
	"""convert prompt validation errors into HTTP 400 responses."""
	return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))


def _resolve_bio(
	ai_bio: str | None,
	account_bio: str | None,
	use_account_bio: bool,
) -> str | None:
	"""resolve the effective bio respecting the useAccountBio toggle."""
	if use_account_bio:
		return account_bio or None
	return ai_bio or None


def _compute_age(birth_date_str: str | None, now: datetime) -> int | None:
	"""compute age in years from an ISO date string, or None."""
	if not birth_date_str:
		return None
	try:
		birth = date.fromisoformat(birth_date_str)
		age = now.year - birth.year
		if (now.month, now.day) < (birth.month, birth.day):
			age -= 1
		return max(0, age)
	except ValueError:
		return None


def _tz_label(dt: datetime) -> str:
	"""build a human-readable timezone label for a datetime."""
	if dt.tzinfo is None:
		return ""
	abbr = dt.strftime("%Z") or ""
	offset = dt.utcoffset()
	if offset is not None:
		total = int(offset.total_seconds())
		sign = "+" if total >= 0 else "-"
		hours, remainder = divmod(abs(total), 3600)
		minutes = remainder // 60
		offset_str = f"UTC{sign}{hours:02d}:{minutes:02d}"
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
		f"{prefix}_timezone": tz_label or None,
	}


def _tz_display(dt: datetime) -> dict[str, object]:
	"""build timezone display variants for a timezone-aware datetime."""
	tz = dt.tzinfo
	if tz is None:
		return {
			"user_timezone": None,
			"user_timezone_abbr": None,
			"user_utc_offset": None,
			"user_timezone_name": None,
		}
	offset = dt.utcoffset()
	if offset is not None:
		total_seconds = int(offset.total_seconds())
		sign = "+" if total_seconds >= 0 else "-"
		hours, remainder = divmod(abs(total_seconds), 3600)
		minutes = remainder // 60
		utc_offset = f"UTC{sign}{hours:02d}:{minutes:02d}"
	else:
		utc_offset = None

	tz_name = str(tz)
	tz_abbr = dt.strftime("%Z") or None

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

	variables.update(_build_date_set(utc_now, "server"))

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
		variables.update(_build_date_set(utc_now, "current"))
		variables.update(
			{
				"user_timezone": None,
				"user_timezone_abbr": None,
				"user_utc_offset": None,
				"user_timezone_name": None,
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
			"client_location": client_context.location_label or None,
		}
	return {
		"client_latitude": None,
		"client_longitude": None,
		"client_location": None,
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
	"""build the dict of always-available prompt template variables."""
	now = _resolve_now(client_context)
	variables: dict[str, object] = _build_date_variables(client_context)

	def client_value(attr: str) -> object:
		"""read an optional field from the client context."""
		if client_context is None:
			return None
		return getattr(client_context, attr, None)

	gamepads = (
		", ".join(client_context.gamepads)
		if client_context and client_context.gamepads
		else None
	)

	variables.update(
		{
			"client_timezone": client_value("timezone"),
			"client_language": client_value("language"),
			"client_os": client_value("os"),
			"client_browser": client_value("browser"),
			"client_is_mobile": client_value("is_mobile"),
			"client_pwa_installed": client_value("pwa_installed"),
			"client_user_agent": client_value("user_agent"),
			"client_offline": client_value("offline"),
			"client_display_mode": client_value("display_mode"),
			"client_preferred_color_scheme": client_value("preferred_color_scheme"),
			"client_prefers_reduced_motion": client_value("prefers_reduced_motion"),
			"client_prefers_contrast": client_value("prefers_contrast"),
			"client_idle_state": client_value("idle_state"),
			"client_gamepad_count": client_value("gamepad_count"),
			"client_gamepads": gamepads,
			"client_connection_type": client_value("connection_type"),
			"client_connection_effective_type": client_value(
				"connection_effective_type"
			),
			"client_connection_downlink_mbps": client_value("connection_downlink_mbps"),
			"client_connection_rtt_ms": client_value("connection_rtt_ms"),
			"client_connection_save_data": client_value("connection_save_data"),
			"client_battery_supported": client_value("battery_supported"),
			"client_battery_charging": client_value("battery_charging"),
			"client_battery_level": client_value("battery_level"),
			"client_battery_charging_time_seconds": client_value(
				"battery_charging_time_seconds"
			),
			"client_battery_discharging_time_seconds": client_value(
				"battery_discharging_time_seconds"
			),
		}
	)

	variables.update(_build_location_variables(client_context))

	variables["chat_window_info"] = SENTINEL_CHAT_WINDOW_INFO
	variables["citation_sources"] = SENTINEL_CITATION_SOURCES

	if user is None:
		variables["user_memories"] = SENTINEL_USER_MEMORIES
		variables["chat_context"] = SENTINEL_CHAT_CONTEXT
		variables.update(
			{
				"user_name": None,
				"user_real_name": None,
				"user_username": None,
				"user_email": None,
				"user_bio": None,
				"user_gender": None,
				"user_birth_date": None,
				"user_age": None,
				"user_custom_instructions": None,
				"ai_personality": None,
			}
		)
		return variables

	prefs = user.prefs
	ai_section = prefs.ai
	account_section = prefs.account
	ai = ai_section if isinstance(ai_section, AIPreferences) else None
	account = (
		account_section if isinstance(account_section, AccountPreferences) else None
	)

	if ai and _preference_value(ai.memories_enabled, True) is False:
		variables["user_memories"] = ""
	else:
		variables["user_memories"] = SENTINEL_USER_MEMORIES

	if ai and _preference_value(ai.chat_recall, True) is False:
		variables["chat_context"] = ""
	else:
		variables["chat_context"] = SENTINEL_CHAT_CONTEXT

	birth_date = _preference_value(account.birth_date, None) if account else None
	age = _compute_age(birth_date, now)
	ai_bio = _preference_value(ai.bio, None) if ai else None
	account_bio = _preference_value(account.bio, None) if account else None
	use_account_bio = _preference_value(ai.use_account_bio, False) if ai else False

	variables.update(
		{
			"user_name": user.display_name or user.username,
			"user_real_name": user.display_name,
			"user_username": user.username,
			"user_email": user.email,
			"user_bio": _resolve_bio(
				ai_bio,
				account_bio,
				use_account_bio=use_account_bio,
			),
			"user_gender": _preference_value(account.gender, None) if account else None,
			"user_birth_date": birth_date,
			"user_age": age,
			"user_custom_instructions": _preference_value(ai.custom_instructions, None)
			if ai
			else None,
			"ai_personality": _preference_value(ai.personality, None) if ai else None,
		}
	)

	return variables


async def render_agent_instructions(
	session: AsyncSession,
	text: str,
	user: User | None = None,
	client_context: ClientContext | None = None,
) -> str:
	"""render agent system instructions with runtime context variables."""
	variables = build_prompt_variables(user, client_context)
	return await render_inline_with_prompts(
		session,
		text=text,
		variables=variables,
	)
