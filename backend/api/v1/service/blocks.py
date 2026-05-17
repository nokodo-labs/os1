"""service helpers for user blocks."""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.models.block import Block
from api.models.user import User
from api.permissions import ActionPermission
from api.v1.service.auth import Principal
from api.v1.service.authorization import require_permission
from nokodo_ai.utils.typeid import TypeID


def _ensure_block_read_access(target_user_id: TypeID, principal: Principal) -> None:
	"""ensure the principal can view the target user's block list.

	self: always allowed.
	manage permission: allows cross-user read access (admin/moderator).
	"""
	if str(target_user_id) == principal.user_id:
		return
	if principal.has_permission(ActionPermission.USER_BLOCKS_MANAGE.value):
		return
	raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")


def _ensure_block_write_access(subject_user_id: TypeID, principal: Principal) -> None:
	"""ensure the principal can create or remove blocks for the subject user.

	self: always allowed (still requires create permission for creation).
	manage permission: allows cross-user writes (admin/moderator).
	"""
	if str(subject_user_id) == principal.user_id:
		return
	if principal.has_permission(ActionPermission.USER_BLOCKS_MANAGE.value):
		return
	raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")


async def list_blocks(
	session: AsyncSession,
	principal: Principal,
	subject_user_id: TypeID,
) -> list[Block]:
	"""list users blocked by the target user."""
	_ensure_block_read_access(subject_user_id, principal)
	stmt = (
		select(Block)
		.where(Block.blocker_id == str(subject_user_id))
		.options(selectinload(Block.blocker), selectinload(Block.blocked))
		.order_by(Block.created_at.desc())
	)
	result = await session.execute(stmt)
	return list(result.scalars().all())


async def block_user(
	session: AsyncSession,
	principal: Principal,
	subject_user_id: TypeID,
	blocked_user_id: TypeID,
) -> Block:
	"""block another user for the subject user."""
	require_permission(principal, ActionPermission.USER_BLOCKS_CREATE)
	_ensure_block_write_access(subject_user_id, principal)
	blocker_id = str(subject_user_id)
	blocked_id = str(blocked_user_id)
	if blocker_id == blocked_id:
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="cannot block yourself",
		)

	blocked = await session.get(User, blocked_id)
	if not blocked:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="user not found",
		)

	existing = await _get_block(session, blocker_id, blocked_id)
	if existing is not None:
		return existing

	block = Block(blocker_id=blocker_id, blocked_id=blocked_id)
	session.add(block)
	await session.flush()
	return await _load_block(session, block.id)


async def unblock_user(
	session: AsyncSession,
	principal: Principal,
	subject_user_id: TypeID,
	blocked_user_id: TypeID,
) -> None:
	"""remove a block for the subject user."""
	_ensure_block_write_access(subject_user_id, principal)
	block = await _get_block(session, str(subject_user_id), str(blocked_user_id))
	if block is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="block not found",
		)
	await session.delete(block)
	await session.flush()


async def _get_block(
	session: AsyncSession,
	blocker_id: str,
	blocked_id: str,
) -> Block | None:
	result = await session.execute(
		select(Block)
		.where(Block.blocker_id == blocker_id, Block.blocked_id == blocked_id)
		.options(selectinload(Block.blocker), selectinload(Block.blocked))
	)
	return result.scalar_one_or_none()


async def _load_block(session: AsyncSession, block_id: TypeID) -> Block:
	result = await session.execute(
		select(Block)
		.where(Block.id == block_id)
		.options(selectinload(Block.blocker), selectinload(Block.blocked))
	)
	block = result.scalar_one_or_none()
	if block is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="block not found",
		)
	return block
