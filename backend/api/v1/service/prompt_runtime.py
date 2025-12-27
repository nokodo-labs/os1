"""Prompt rendering and validation with Jinja2."""

from __future__ import annotations

import re
from collections.abc import Iterable

from fastapi import HTTPException, status
from jinja2 import DictLoader, Environment, StrictUndefined, TemplateNotFound
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.prompt import Prompt


_PROMPT_REF_RE = re.compile(r"{{\s*PROMPTS\.([a-zA-Z0-9-_]+)\s*}}")
_INCLUDE_RE = re.compile(r"{%-?\s*include\s+['\"]([a-zA-Z0-9-_/]+)['\"]\s*-?%}")
_MAX_DEPTH = 50


def normalize_command(command: str) -> str:
	return command.lstrip("/")


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
			errors.append(f"referenced prompt '/{current}' does not exist")
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
			f"referenced prompt '/{key}' does not exist"
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
	self_id: str | None = None,
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
