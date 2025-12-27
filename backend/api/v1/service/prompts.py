"""Service layer for prompt operations."""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.prompt import Prompt
from api.schemas.prompt import PromptCreate, PromptUpdate
from api.v1.service.prompt_runtime import (
	PromptValidationError,
	http_error_from_validation,
	validate_prompt_content,
)


async def _ensure_unique_command(
	session: AsyncSession,
	*,
	command: str,
	exclude_prompt_id: str | None = None,
) -> None:
	stmt = select(Prompt).where(Prompt.command == command)
	if exclude_prompt_id is not None:
		stmt = stmt.where(Prompt.id != exclude_prompt_id)
	result = await session.execute(stmt)
	existing = result.scalars().first()
	if existing:
		raise HTTPException(
			status_code=status.HTTP_409_CONFLICT,
			detail="Prompt command already exists",
		)


async def _validate_prompt_template(
	session: AsyncSession,
	*,
	prompt_id: str | None,
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


async def _get_prompt(prompt_id: str, session: AsyncSession) -> Prompt:
	prompt = await session.get(Prompt, prompt_id)
	if not prompt:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Prompt not found",
		)
	return prompt


async def create_prompt(prompt_in: PromptCreate, session: AsyncSession) -> Prompt:
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


async def list_prompts(session: AsyncSession) -> list[Prompt]:
	result = await session.execute(select(Prompt).order_by(Prompt.command))
	return list(result.scalars().all())


async def get_prompt(prompt_id: str, session: AsyncSession) -> Prompt:
	return await _get_prompt(prompt_id, session)


async def update_prompt(
	prompt_id: str,
	prompt_in: PromptUpdate,
	session: AsyncSession,
) -> Prompt:
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

	for field, value in updates.items():
		setattr(prompt, field, value)

	session.add(prompt)
	await session.commit()
	await session.refresh(prompt)
	return prompt


async def delete_prompt(prompt_id: str, session: AsyncSession) -> None:
	prompt = await _get_prompt(prompt_id, session)
	await session.delete(prompt)
	await session.commit()
