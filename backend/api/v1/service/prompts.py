"""Service layer for prompt operations."""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.prompt import Prompt
from api.permissions import ResourceType
from api.schemas.prompt import Prompt as PromptOut
from api.schemas.prompt import PromptCreate, PromptUpdate
from api.v1.service.auth import Principal
from api.v1.service.authorization import require_permission
from api.v1.service.prompt_runtime import (
	PromptValidationError,
	http_error_from_validation,
	normalize_command,
	validate_prompt_content,
)
from api.v1.service.resource_payload_cache import (
	get_or_set_resource_payload_cache,
	invalidate_resource_payload_cache,
)
from api.v1.service.sorting import SortDir, apply_sort
from nokodo_ai.utils.typeid import TypeID


async def _ensure_unique_command(
	session: AsyncSession,
	command: str,
	exclude_prompt_id: TypeID | None = None,
) -> None:
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
	result = await session.execute(select(Prompt))
	all_prompts = list(result.scalars().all())
	try:
		validate_prompt_content(
			all_prompts=all_prompts,
			command=command,
			content=content,
			self_id=prompt_id,
		)
	except PromptValidationError as err:
		raise http_error_from_validation(err) from err


async def _validate_all_prompts(
	session: AsyncSession,
	prompt_map_override: dict[str, str] | None = None,
) -> None:
	"""validate that every prompt in the DB has valid references.

	optionally accepts a prompt_map_override to inject pending changes
	(e.g. a renamed or updated prompt) before validation.
	"""
	result = await session.execute(select(Prompt))
	all_prompts = list(result.scalars().all())
	prompt_map = {normalize_command(p.command): p.content for p in all_prompts}
	if prompt_map_override:
		prompt_map.update(prompt_map_override)
	errors: list[str] = []
	for cmd, content in prompt_map.items():
		try:
			validate_prompt_content(
				all_prompts=all_prompts,
				command=cmd,
				content=content,
			)
		except PromptValidationError as err:
			errors.append(f"'{cmd}': {err}")
	if errors:
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail=f"prompt validation failed: {'; '.join(errors)}",
		)


async def _get_prompt(prompt_id: TypeID, session: AsyncSession) -> Prompt:
	prompt = await session.get(Prompt, prompt_id)
	if not prompt:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Prompt not found",
		)
	return prompt


async def create_prompt(
	prompt_in: PromptCreate,
	session: AsyncSession,
	principal: Principal,
) -> Prompt:
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
	return prompt


async def list_prompts(
	session: AsyncSession,
	principal: Principal,
	skip: int = 0,
	limit: int = 50,
	sort_by: str = "command",
	sort_dir: SortDir = "asc",
) -> list[Prompt]:
	require_permission(principal, "prompts:read")
	stmt = (
		apply_sort(
			select(Prompt),
			sort_by=sort_by,
			sort_dir=sort_dir,
			columns={
				"command": Prompt.command,
				"created_at": Prompt.created_at,
				"updated_at": Prompt.updated_at,
			},
			tie_breaker=Prompt.id,
		)
		.offset(skip)
		.limit(limit)
	)
	result = await session.execute(stmt)
	return list(result.scalars().all())


async def get_prompt(
	prompt_id: TypeID,
	session: AsyncSession,
	principal: Principal,
	use_cache: bool = True,
) -> PromptOut:
	require_permission(principal, "prompts:read")

	async def load_payload() -> PromptOut:
		return PromptOut.model_validate(await _get_prompt(prompt_id, session))

	if not use_cache:
		return await load_payload()
	return await get_or_set_resource_payload_cache(
		ResourceType.PROMPT,
		prompt_id,
		PromptOut,
		load_payload,
	)


async def update_prompt(
	prompt_id: TypeID,
	prompt_in: PromptUpdate,
	session: AsyncSession,
	principal: Principal,
) -> Prompt:
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

	# validate the updated prompt's own references
	await _validate_prompt_template(
		session,
		prompt_id=prompt_id,
		command=new_command,
		content=new_content,
	)

	# when the command is renamed, validate that ALL other prompts
	# still resolve correctly (catches broken references)
	old_command = normalize_command(prompt.command)
	if "command" in updates and normalize_command(new_command) != old_command:
		override = {normalize_command(new_command): new_content}
		# remove the old command from the map by marking it absent
		# (validate_all_prompts will rebuild from DB, which still has the old
		# name, so we simulate the rename by injecting the new entry)
		await _validate_all_prompts(session, prompt_map_override=override)

	for field, value in updates.items():
		setattr(prompt, field, value)

	session.add(prompt)
	await session.commit()
	await session.refresh(prompt)
	await invalidate_resource_payload_cache(ResourceType.PROMPT, prompt_id)
	return prompt


async def delete_prompt(
	prompt_id: TypeID,
	session: AsyncSession,
	principal: Principal,
) -> None:
	require_permission(principal, "prompts:manage")
	prompt = await _get_prompt(prompt_id, session)
	await session.delete(prompt)
	await session.commit()
	await invalidate_resource_payload_cache(ResourceType.PROMPT, prompt_id)
