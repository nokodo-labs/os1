"""prompt CRUD service operations."""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from api.models.prompt import PROMPT_TYPEID_PREFIX, Prompt
from api.permissions import ResourceType
from api.schemas.prompt import Prompt as PromptOut
from api.schemas.prompt import (
	PromptCreate,
	PromptListFilters,
	PromptUpdate,
)
from api.v1.service.auth import Principal
from api.v1.service.authorization import require_permission
from api.v1.service.listing import SortDir, apply_sort, exact_typeid_filter
from api.v1.service.prompts.cache import invalidate_prompt_template_cache
from api.v1.service.prompts.external import (
	get_external_prompt,
	list_external_prompts,
	load_external_prompt_placeholders,
)
from api.v1.service.prompts.runtime import (
	PromptValidationError,
	http_error_from_validation,
	normalize_command,
	validate_prompt_content,
)
from api.v1.service.resource_payload_cache import (
	get_or_set_resource_payload_cache,
	invalidate_resource_payload_cache,
)
from nokodo_ai.utils.search import contains_pattern
from nokodo_ai.utils.typeid import TypeID


def _apply_prompt_filters(stmt: Select, filters: PromptListFilters) -> Select:
	"""apply prompt filters to a DB query."""
	if not filters.q or not filters.q.strip():
		return stmt
	pattern = contains_pattern(filters.q.strip())
	return stmt.where(
		or_(
			Prompt.command.ilike(pattern, escape="\\"),
			Prompt.content.ilike(pattern, escape="\\"),
			exact_typeid_filter(Prompt.id, filters.q, PROMPT_TYPEID_PREFIX),
		)
	)


async def _ensure_unique_command(
	session: AsyncSession,
	command: str,
	exclude_prompt_id: TypeID | None = None,
) -> None:
	"""ensure a prompt command does not collide with another DB prompt."""
	stmt = select(Prompt).where(Prompt.command == command)
	if exclude_prompt_id is not None:
		stmt = stmt.where(Prompt.id != exclude_prompt_id)
	result = await session.execute(stmt)
	existing = result.scalars().first()
	if existing:
		raise HTTPException(
			status_code=status.HTTP_409_CONFLICT,
			detail="prompt command already exists",
		)


async def _validate_prompt_template(
	session: AsyncSession,
	prompt_id: TypeID | None,
	command: str,
	content: str,
) -> None:
	"""validate one prompt template against DB and external prompt refs."""
	result = await session.execute(select(Prompt))
	all_prompts = list(result.scalars().all())
	extra_prompt_map = await load_external_prompt_placeholders(session)
	try:
		validate_prompt_content(
			all_prompts=all_prompts,
			command=command,
			content=content,
			self_id=prompt_id,
			extra_prompt_map=extra_prompt_map,
		)
	except PromptValidationError as err:
		raise http_error_from_validation(err) from err


async def _validate_all_prompts(
	session: AsyncSession,
	prompt_map_override: dict[str, str] | None = None,
) -> None:
	"""validate that every DB and external prompt reference resolves."""
	result = await session.execute(select(Prompt))
	all_prompts = list(result.scalars().all())
	prompt_map = {
		normalize_command(prompt.command): prompt.content for prompt in all_prompts
	}
	prompt_map.update(await load_external_prompt_placeholders(session))
	if prompt_map_override:
		prompt_map.update(prompt_map_override)
	errors: list[str] = []
	for command, content in prompt_map.items():
		try:
			validate_prompt_content(
				all_prompts=all_prompts,
				command=command,
				content=content,
				extra_prompt_map=prompt_map,
			)
		except PromptValidationError as err:
			errors.append(f"'{command}': {err}")
	if errors:
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail=f"prompt validation failed: {'; '.join(errors)}",
		)


async def _get_prompt(prompt_id: TypeID, session: AsyncSession) -> Prompt:
	"""load a prompt row or raise a 404 HTTP error."""
	prompt = await session.get(Prompt, prompt_id)
	if not prompt:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Prompt not found",
		)
	return prompt


def _apply_prompt_catalog_filters(
	prompts: list[PromptOut],
	filters: PromptListFilters,
) -> list[PromptOut]:
	"""apply prompt filters to in-memory catalog items."""
	needle = filters.q.strip().lower() if filters.q and filters.q.strip() else None
	filtered: list[PromptOut] = []
	for prompt in prompts:
		if filters.source is not None and prompt.source != filters.source:
			continue
		if needle is not None and not (
			needle in prompt.id.lower()
			or needle in prompt.command.lower()
			or needle in prompt.content.lower()
		):
			continue
		filtered.append(prompt)
	return filtered


def _sort_prompt_catalog(
	prompts: list[PromptOut],
	sort_by: str,
	sort_dir: SortDir,
) -> list[PromptOut]:
	"""sort in-memory prompt catalog items."""
	reverse = sort_dir == "desc"
	if sort_by == "created_at":
		return sorted(prompts, key=lambda prompt: prompt.created_at, reverse=reverse)
	if sort_by == "updated_at":
		return sorted(prompts, key=lambda prompt: prompt.updated_at, reverse=reverse)
	return sorted(prompts, key=lambda prompt: prompt.command, reverse=reverse)


async def create_prompt(
	prompt_in: PromptCreate,
	session: AsyncSession,
	principal: Principal,
) -> Prompt:
	"""create a prompt after validating command uniqueness and references."""
	require_permission(principal, "prompts:manage")
	data = prompt_in.model_dump(by_alias=True)
	await _ensure_unique_command(session, command=data["command"])
	await _validate_prompt_template(
		session,
		prompt_id=None,
		command=data["command"],
		content=data["content"],
	)

	prompt = Prompt(**data)
	session.add(prompt)
	await session.commit()
	await session.refresh(prompt)
	await invalidate_prompt_template_cache(session)
	return prompt


async def list_prompts(
	session: AsyncSession,
	principal: Principal,
	skip: int = 0,
	limit: int = 50,
	sort_by: str = "command",
	sort_dir: SortDir = "asc",
	filters: PromptListFilters | None = None,
) -> list[PromptOut]:
	"""list prompts visible to a principal."""
	require_permission(principal, "prompts:read")
	prompt_filters = filters or PromptListFilters()
	prompts = await _list_prompt_catalog(
		session,
		filters=prompt_filters,
		sort_by=sort_by,
		sort_dir=sort_dir,
	)
	return prompts[skip : skip + limit]


async def _list_custom_prompts(
	session: AsyncSession,
	filters: PromptListFilters,
	sort_by: str,
	sort_dir: SortDir,
) -> list[PromptOut]:
	"""list DB-backed prompts as custom prompt catalog items."""
	if filters.source not in (None, "custom"):
		return []

	stmt = _apply_prompt_filters(select(Prompt), filters)
	stmt = apply_sort(
		stmt,
		sort_by=sort_by,
		sort_dir=sort_dir,
		columns={
			"command": Prompt.command,
			"created_at": Prompt.created_at,
			"updated_at": Prompt.updated_at,
		},
		tie_breaker=Prompt.id,
	)
	result = await session.execute(stmt)
	return [PromptOut.model_validate(prompt) for prompt in result.scalars().all()]


async def _list_prompt_catalog(
	session: AsyncSession,
	filters: PromptListFilters,
	sort_by: str,
	sort_dir: SortDir,
) -> list[PromptOut]:
	"""list prompt catalog items from requested sources."""
	prompts: list[PromptOut] = []
	prompts.extend(await _list_custom_prompts(session, filters, sort_by, sort_dir))
	if filters.source in (None, "external"):
		prompts.extend(await list_external_prompts(session))
	return _sort_prompt_catalog(
		_apply_prompt_catalog_filters(prompts, filters), sort_by, sort_dir
	)


async def count_prompts(
	session: AsyncSession,
	principal: Principal,
	filters: PromptListFilters | None = None,
) -> int:
	"""count prompts visible to a principal."""
	require_permission(principal, "prompts:read")
	prompt_filters = filters or PromptListFilters()
	custom_count = 0
	if prompt_filters.source in (None, "custom"):
		stmt = _apply_prompt_filters(
			select(func.count()).select_from(Prompt), prompt_filters
		)
		custom_count = await session.scalar(stmt) or 0
	external_count = 0
	if prompt_filters.source in (None, "external"):
		external_prompts = await list_external_prompts(session)
		external_count = len(
			_apply_prompt_catalog_filters(external_prompts, prompt_filters)
		)
	return custom_count + external_count


async def get_prompt(
	prompt_id: TypeID | str,
	session: AsyncSession,
	principal: Principal,
	use_cache: bool = True,
) -> PromptOut:
	"""return one prompt API payload, optionally using resource payload cache."""
	require_permission(principal, "prompts:read")
	prompt_id_str = str(prompt_id)
	external_prompt = await get_external_prompt(prompt_id_str, session)
	if external_prompt is not None:
		return external_prompt
	try:
		custom_prompt_id = TypeID(prompt_id_str)
	except ValueError as exc:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="prompt not found",
		) from exc

	async def load_payload() -> PromptOut:
		"""load the prompt payload from the database."""
		return PromptOut.model_validate(await _get_prompt(custom_prompt_id, session))

	if not use_cache:
		return await load_payload()
	return await get_or_set_resource_payload_cache(
		ResourceType.PROMPT,
		custom_prompt_id,
		PromptOut,
		load_payload,
	)


async def update_prompt(
	prompt_id: TypeID,
	prompt_in: PromptUpdate,
	session: AsyncSession,
	principal: Principal,
) -> Prompt:
	"""update a prompt after validating references and command changes."""
	require_permission(principal, "prompts:manage")
	prompt = await _get_prompt(prompt_id, session)
	updates = prompt_in.model_dump(exclude_unset=True, by_alias=True)
	if not updates:
		return prompt

	new_command = str(updates.get("command", prompt.command))
	new_content = str(updates.get("content", prompt.content))

	if "command" in updates:
		await _ensure_unique_command(
			session,
			command=new_command,
			exclude_prompt_id=prompt_id,
		)

	await _validate_prompt_template(
		session,
		prompt_id=prompt_id,
		command=new_command,
		content=new_content,
	)

	old_command = normalize_command(prompt.command)
	if "command" in updates and normalize_command(new_command) != old_command:
		override = {normalize_command(new_command): new_content}
		await _validate_all_prompts(session, prompt_map_override=override)

	for field, value in updates.items():
		setattr(prompt, field, value)

	session.add(prompt)
	await session.commit()
	await session.refresh(prompt)
	await invalidate_resource_payload_cache(ResourceType.PROMPT, prompt_id)
	await invalidate_prompt_template_cache(session)
	return prompt


async def delete_prompt(
	prompt_id: TypeID,
	session: AsyncSession,
	principal: Principal,
) -> None:
	"""delete a prompt and invalidate prompt caches."""
	require_permission(principal, "prompts:manage")
	prompt = await _get_prompt(prompt_id, session)
	await session.delete(prompt)
	await session.commit()
	await invalidate_resource_payload_cache(ResourceType.PROMPT, prompt_id)
	await invalidate_prompt_template_cache(session)
