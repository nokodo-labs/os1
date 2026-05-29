"""external prompt source boundary."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.prompt import Prompt as PromptOut


LoadExternalPromptPlaceholders = Callable[[AsyncSession], Awaitable[dict[str, str]]]
RenderExternalPromptContentMap = Callable[
	[AsyncSession, set[str]],
	Awaitable[dict[str, str]],
]
ListExternalPrompts = Callable[[AsyncSession], Awaitable[list[PromptOut]]]
GetExternalPrompt = Callable[[str, AsyncSession], Awaitable[PromptOut | None]]


@dataclass(frozen=True)
class ExternalPromptSource:
	"""registered provider for prompt templates outside the prompt table."""

	name: str
	prefix: str
	load_placeholders: LoadExternalPromptPlaceholders
	render_content_map: RenderExternalPromptContentMap
	list_prompts: ListExternalPrompts
	get_prompt: GetExternalPrompt


_SOURCES_BY_NAME: dict[str, ExternalPromptSource] = {}


def register_external_prompt_source(source: ExternalPromptSource) -> None:
	"""register an external prompt source with a unique command prefix."""
	_validate_source_shape(source)
	existing = _SOURCES_BY_NAME.get(source.name)
	if existing is not None:
		if existing == source:
			return
		raise ValueError(f"external prompt source already registered: {source.name}")
	for registered in _SOURCES_BY_NAME.values():
		if _prefixes_overlap(source.prefix, registered.prefix):
			raise ValueError(
				"external prompt source prefix conflicts with "
				f"{registered.name}: {source.prefix}"
			)
	_SOURCES_BY_NAME[source.name] = source


async def load_external_prompt_placeholders(session: AsyncSession) -> dict[str, str]:
	"""load placeholder templates for all registered external prompt sources."""
	placeholders: dict[str, str] = {}
	for source in _sources():
		source_content = await source.load_placeholders(session)
		_validate_source_commands(source, source_content.keys())
		for command, content in source_content.items():
			if command in placeholders:
				raise ValueError(f"duplicate external prompt command: {command}")
			placeholders[command] = content
	return placeholders


async def render_external_prompt_content_map(
	session: AsyncSession,
	commands: set[str],
) -> dict[str, str]:
	"""render selected external prompt templates for prompt expansion."""
	if not commands:
		return {}
	rendered: dict[str, str] = {}
	for source in _sources():
		source_commands = {
			command for command in commands if command.startswith(source.prefix)
		}
		if not source_commands:
			continue
		source_content = await source.render_content_map(session, source_commands)
		_validate_source_commands(source, source_content.keys())
		for command, content in source_content.items():
			if command not in source_commands:
				raise ValueError(f"unexpected rendered external prompt: {command}")
			if command in rendered:
				raise ValueError(f"duplicate rendered external prompt: {command}")
			rendered[command] = content
	return rendered


async def list_external_prompts(session: AsyncSession) -> list[PromptOut]:
	"""list prompt catalog items from registered external sources."""
	prompts: list[PromptOut] = []
	seen: set[str] = set()
	for source in _sources():
		source_prompts = await source.list_prompts(session)
		_validate_source_prompt_items(source, source_prompts)
		for prompt in source_prompts:
			if prompt.id in seen:
				raise ValueError(f"duplicate external prompt id: {prompt.id}")
			seen.add(prompt.id)
			prompts.append(prompt)
	return prompts


async def get_external_prompt(
	prompt_id: str,
	session: AsyncSession,
) -> PromptOut | None:
	"""look up one external prompt through the owning source prefix."""
	for source in _sources():
		if not prompt_id.startswith(source.prefix):
			continue
		prompt = await source.get_prompt(prompt_id, session)
		if prompt is not None:
			_validate_source_prompt_items(source, [prompt])
			return prompt
	return None


def _sources() -> tuple[ExternalPromptSource, ...]:
	"""return the currently wired external prompt providers."""
	return tuple(_SOURCES_BY_NAME.values())


def _validate_source_shape(source: ExternalPromptSource) -> None:
	"""validate one external prompt source before registration."""
	if not source.name.strip():
		raise ValueError("external prompt source name is required")
	if not source.prefix.strip():
		raise ValueError("external prompt source prefix is required")
	if source.prefix != source.prefix.strip():
		raise ValueError("external prompt source prefix cannot include edge spaces")


def _validate_source_commands(
	source: ExternalPromptSource,
	commands: Iterable[str],
) -> None:
	"""ensure every exposed command belongs to its source prefix."""
	for command in commands:
		if not isinstance(command, str) or not command.startswith(source.prefix):
			raise ValueError(
				"external prompt source emitted command outside prefix "
				f"{source.name}: {command}"
			)


def _validate_source_prompt_items(
	source: ExternalPromptSource,
	prompts: list[PromptOut],
) -> None:
	"""ensure every exposed prompt belongs to its source prefix."""
	for prompt in prompts:
		if prompt.source != "external" or not prompt.id.startswith(source.prefix):
			raise ValueError(
				"external prompt source emitted prompt outside prefix "
				f"{source.name}: {prompt.id}"
			)


def _prefixes_overlap(left: str, right: str) -> bool:
	"""return whether two prompt source prefixes would route ambiguously."""
	return left.startswith(right) or right.startswith(left)
