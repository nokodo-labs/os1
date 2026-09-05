"""message attachment persistence helpers."""

from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.access_rule import AccessLevel
from api.models.message import Message
from api.models.message_attachment import MessageAttachment, resource_fk_name
from api.permissions import ATTACHABLE_RESOURCE_TYPES, ResourceType
from api.schemas.message import ResourceAttachment
from api.v1.service.authentication import Principal
from api.v1.service.authorization import (
	invalidate_accessible_users_for_resource,
	require_resource_access,
)
from api.v1.service.vectorize import sync_resource_refs_vector_acl
from nokodo_ai.utils.typeid import TypeID


def _attachment_link(
	message_id: TypeID,
	attachment: ResourceAttachment,
	position: int,
) -> MessageAttachment:
	resource_ids: dict[str, TypeID] = {
		resource_fk_name(attachment.type): attachment.id,
	}
	return MessageAttachment(
		message_id=message_id,
		position=position,
		**resource_ids,
	)


async def create_message_attachments(
	message_id: TypeID,
	attachments: list[ResourceAttachment],
	session: AsyncSession,
	principal: Principal,
) -> list[MessageAttachment]:
	"""validate and persist the ordered resources attached to a message."""
	thread_id = await session.scalar(
		select(Message.thread_id).where(Message.id == message_id)
	)
	if thread_id is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="message not found",
		)
	links: list[MessageAttachment] = []
	seen: set[tuple[ResourceType, str]] = set()
	for attachment in attachments:
		key = (attachment.type, str(attachment.id))
		if key in seen:
			continue
		seen.add(key)
		if attachment.type == ResourceType.THREAD and attachment.id == thread_id:
			raise HTTPException(
				status_code=status.HTTP_409_CONFLICT,
				detail={
					"code": "thread_self_attachment",
					"message": "a thread cannot be attached to one of its own messages",
				},
			)
		try:
			await require_resource_access(
				attachment.id,
				session,
				principal,
				attachment.type,
				required_level=AccessLevel.ADMIN,
			)
		except HTTPException as exc:
			if exc.status_code != status.HTTP_404_NOT_FOUND:
				raise
			try:
				await require_resource_access(
					attachment.id,
					session,
					principal,
					attachment.type,
					required_level=AccessLevel.READER,
				)
			except HTTPException:
				raise exc
			raise HTTPException(
				status_code=status.HTTP_403_FORBIDDEN,
				detail={
					"code": "attachment_admin_required",
					"message": "admin access is required to share this resource",
				},
			) from exc
		links.append(_attachment_link(message_id, attachment, len(links)))
	if links:
		session.add_all(links)
		await session.flush()
	return links


async def replace_message_attachments(
	message_id: TypeID,
	attachments: list[ResourceAttachment],
	session: AsyncSession,
	principal: Principal,
) -> tuple[list[MessageAttachment], list[MessageAttachment]]:
	"""replace all normalized attachments for a message."""
	previous = list(
		(
			await session.scalars(
				select(MessageAttachment).where(
					MessageAttachment.message_id == message_id
				)
			)
		).all()
	)
	await session.execute(
		delete(MessageAttachment).where(MessageAttachment.message_id == message_id)
	)
	current = await create_message_attachments(
		message_id,
		attachments,
		session,
		principal,
	)
	return previous, current


def attachment_resource_refs(
	attachments: list[MessageAttachment],
) -> list[tuple[ResourceType, TypeID]]:
	"""return concrete resource references carried by attachment links."""
	refs: list[tuple[ResourceType, TypeID]] = []
	for attachment in attachments:
		for resource_type in ATTACHABLE_RESOURCE_TYPES:
			resource_id = attachment.__dict__.get(resource_fk_name(resource_type))
			if resource_id is not None:
				refs.append((resource_type, resource_id))
				break
	return list(dict.fromkeys(refs))


async def refresh_attachment_access(
	resource_refs: list[tuple[ResourceType, TypeID]],
	session: AsyncSession,
) -> None:
	"""refresh derived access state changed by attachment links."""
	for resource_type, resource_id in resource_refs:
		await invalidate_accessible_users_for_resource(resource_type, resource_id)
	await sync_resource_refs_vector_acl(resource_refs, session)
