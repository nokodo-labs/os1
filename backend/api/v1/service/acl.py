"""service helpers for access control entries."""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.acl import AccessControlEntry
from api.models.agent import Agent
from api.models.group import Group
from api.models.project import Project
from api.models.thread import Thread
from api.models.user import User
from api.schemas.acl import AccessControlEntryCreate


async def _ensure_thread_exists(thread_id: str, session: AsyncSession) -> None:
	thread = await session.get(Thread, thread_id)
	if thread is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Thread not found",
		)


async def _ensure_project_exists(project_id: str, session: AsyncSession) -> None:
	project = await session.get(Project, project_id)
	if project is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Project not found",
		)


async def _ensure_principal_exists(
	entry: AccessControlEntryCreate,
	session: AsyncSession,
) -> None:
	if entry.user_id is not None:
		principal = await session.get(User, entry.user_id)
		if principal is None:
			raise HTTPException(
				status_code=status.HTTP_404_NOT_FOUND,
				detail="User not found",
			)
		return

	if entry.group_id is not None:
		principal = await session.get(Group, entry.group_id)
		if principal is None:
			raise HTTPException(
				status_code=status.HTTP_404_NOT_FOUND,
				detail="Group not found",
			)
		return

	if entry.agent_id is not None:
		principal = await session.get(Agent, entry.agent_id)
		if principal is None:
			raise HTTPException(
				status_code=status.HTTP_404_NOT_FOUND,
				detail="Agent not found",
			)
		return

	raise HTTPException(
		status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
		detail="principal not set",
	)


def _principal_key(entry: AccessControlEntryCreate) -> str:
	if entry.user_id is not None:
		return f"user:{entry.user_id}"
	if entry.group_id is not None:
		return f"group:{entry.group_id}"
	return f"agent:{entry.agent_id}"


def _ace_key(ace: AccessControlEntry) -> str:
	if ace.user_id is not None:
		return f"user:{ace.user_id}"
	if ace.group_id is not None:
		return f"group:{ace.group_id}"
	return f"agent:{ace.agent_id}"


async def _list_by_thread(
	thread_id: str,
	session: AsyncSession,
) -> list[AccessControlEntry]:
	stmt = (
		select(AccessControlEntry)
		.where(AccessControlEntry.thread_id == thread_id)
		.order_by(AccessControlEntry.created_at)
	)
	result = await session.execute(stmt)
	return list(result.scalars().all())


async def _list_by_project(
	project_id: str,
	session: AsyncSession,
) -> list[AccessControlEntry]:
	stmt = (
		select(AccessControlEntry)
		.where(AccessControlEntry.project_id == project_id)
		.order_by(AccessControlEntry.created_at)
	)
	result = await session.execute(stmt)
	return list(result.scalars().all())


async def list_thread_acl(
	thread_id: str,
	session: AsyncSession,
) -> list[AccessControlEntry]:
	await _ensure_thread_exists(thread_id, session)
	return await _list_by_thread(thread_id, session)


async def list_project_acl(
	project_id: str,
	session: AsyncSession,
) -> list[AccessControlEntry]:
	await _ensure_project_exists(project_id, session)
	return await _list_by_project(project_id, session)


async def set_thread_acl(
	thread_id: str,
	entries: list[AccessControlEntryCreate],
	session: AsyncSession,
) -> list[AccessControlEntry]:
	await _ensure_thread_exists(thread_id, session)
	existing = await _list_by_thread(thread_id, session)

	existing_by_key = {_ace_key(ace): ace for ace in existing}
	desired_keys: set[str] = set()

	for entry in entries:
		await _ensure_principal_exists(entry, session)
		principal_key = _principal_key(entry)
		if principal_key in desired_keys:
			raise HTTPException(
				status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
				detail="Duplicate principal entries are not allowed",
			)
		desired_keys.add(principal_key)

		ace = existing_by_key.get(principal_key)
		if ace is None:
			ace = AccessControlEntry(thread_id=thread_id)
			session.add(ace)
		else:
			ace.thread_id = thread_id

		ace.project_id = None
		ace.user_id = entry.user_id
		ace.group_id = entry.group_id
		ace.agent_id = entry.agent_id
		ace.role = entry.role
		ace.metadata_ = entry.metadata

	for key, ace in existing_by_key.items():
		if key not in desired_keys:
			await session.delete(ace)

	await session.commit()
	return await _list_by_thread(thread_id, session)


async def set_project_acl(
	project_id: str,
	entries: list[AccessControlEntryCreate],
	session: AsyncSession,
) -> list[AccessControlEntry]:
	await _ensure_project_exists(project_id, session)
	existing = await _list_by_project(project_id, session)

	existing_by_key = {_ace_key(ace): ace for ace in existing}
	desired_keys: set[str] = set()

	for entry in entries:
		await _ensure_principal_exists(entry, session)
		principal_key = _principal_key(entry)
		if principal_key in desired_keys:
			raise HTTPException(
				status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
				detail="Duplicate principal entries are not allowed",
			)
		desired_keys.add(principal_key)

		ace = existing_by_key.get(principal_key)
		if ace is None:
			ace = AccessControlEntry(project_id=project_id)
			session.add(ace)
		else:
			ace.project_id = project_id

		ace.thread_id = None
		ace.user_id = entry.user_id
		ace.group_id = entry.group_id
		ace.agent_id = entry.agent_id
		ace.role = entry.role
		ace.metadata_ = entry.metadata

	for key, ace in existing_by_key.items():
		if key not in desired_keys:
			await session.delete(ace)

	await session.commit()
	return await _list_by_project(project_id, session)
