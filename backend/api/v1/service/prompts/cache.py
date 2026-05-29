"""prompt template cache helpers."""

from __future__ import annotations

from hashlib import sha256

from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.exc import UnboundExecutionError
from sqlalchemy.ext.asyncio import AsyncSession

from api.boot_settings import boot_settings
from api.models.prompt import Prompt
from api.redis import cache
from api.settings import settings


class PromptTemplate(BaseModel):
	"""cached prompt template content before runtime variable rendering."""

	command: str
	content: str


async def get_cached_prompt_templates(
	session: AsyncSession,
) -> dict[str, str] | None:
	"""return cached prompt templates keyed by normalized command."""
	key = _prompt_templates_key(session)
	value = await _get_cache_value(key)
	if not isinstance(value, list):
		return None
	try:
		templates = [PromptTemplate.model_validate(item) for item in value]
	except ValidationError:
		await _delete_cache_key(key)
		return None
	return {template.command: template.content for template in templates}


async def set_cached_prompt_templates(
	session: AsyncSession,
	prompt_map: dict[str, str],
) -> None:
	"""cache prompt templates keyed by normalized command."""
	await _set_cache_value(
		_prompt_templates_key(session),
		[
			PromptTemplate(command=command, content=content).model_dump(mode="json")
			for command, content in prompt_map.items()
		],
		ttl=settings.cache.prompt_template_ttl_seconds,
		tags=[_prompt_templates_tag(session)],
	)


async def list_prompt_templates(session: AsyncSession) -> dict[str, str]:
	"""load prompt templates from cache or the prompt table."""
	from api.v1.service.prompts.runtime import normalize_command

	cached = await get_cached_prompt_templates(session)
	if cached is not None:
		return dict(cached)
	result = await session.execute(select(Prompt.command, Prompt.content))
	prompt_map = {
		normalize_command(command): content for command, content in result.all()
	}
	await set_cached_prompt_templates(session, prompt_map)
	return prompt_map


async def invalidate_prompt_template_cache(session: AsyncSession) -> None:
	"""invalidate cached prompt templates for the active database binding."""
	await _invalidate_tag(_prompt_templates_tag(session))


def _prompt_templates_key(session: AsyncSession) -> str:
	"""return the Redis key for cached prompt templates."""
	return f"prompts:{_cache_namespace(session)}:templates"


def _prompt_templates_tag(session: AsyncSession) -> str:
	"""return the Redis tag for cached prompt templates."""
	return f"prompts:{_cache_namespace(session)}:templates"


def _cache_namespace(session: AsyncSession) -> str:
	"""derive a stable Redis namespace from the active database binding."""
	try:
		bind = session.get_bind()
	except (AttributeError, UnboundExecutionError):
		seed = f"{boot_settings.DATABASE_URL}:unbound:{id(session)}"
		return sha256(seed.encode()).hexdigest()[:16]
	url = getattr(bind, "url", None)
	if url is None:
		seed = boot_settings.DATABASE_URL
	else:
		seed = url.render_as_string(hide_password=True)
	return sha256(seed.encode()).hexdigest()[:16]


async def _get_cache_value(key: str) -> object | None:
	"""read a prompt cache value and fail open if Redis is not connected yet."""
	try:
		return await cache.get(key)
	except RuntimeError:
		return None


async def _set_cache_value(
	key: str,
	value: object,
	ttl: int,
	tags: list[str],
) -> None:
	"""write a prompt cache value and skip caching if Redis is unavailable."""
	try:
		await cache.set(key, value, ttl=ttl, tags=tags)
	except RuntimeError:
		return


async def _delete_cache_key(key: str) -> None:
	"""delete a corrupt prompt cache entry and ignore unavailable Redis."""
	try:
		await cache.delete(key)
	except RuntimeError:
		return


async def _invalidate_tag(tag: str) -> None:
	"""invalidate a prompt cache tag and ignore unavailable Redis."""
	try:
		await cache.invalidate_tag(tag)
	except RuntimeError:
		return
