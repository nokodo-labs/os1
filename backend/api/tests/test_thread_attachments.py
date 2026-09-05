"""message attachment authorization lifecycle coverage."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.access_rule import AccessLevel, AccessRule
from api.models.file import File
from api.models.message import MessageType, UserMessage
from api.models.message_attachment import MessageAttachment
from api.models.thread import Thread
from api.permissions import ResourceType
from api.schemas.message import ResourceAttachment
from api.schemas.thread import ThreadUpdate
from api.tests.factories import create_user, principal_for
from api.v1.service.authorization import (
	fetch_bulk_acl_metadata,
	get_effective_access_level,
)
from api.v1.service.threads import attachments as attachment_service
from api.v1.service.threads import core as thread_service
from api.v1.service.threads.attachments import (
	attachment_resource_refs,
	create_message_attachments,
	refresh_attachment_access,
	replace_message_attachments,
)
from api.v1.service.threads.core import delete_thread
from api.v1.service.threads.messages import delete_user_message_turn
from nokodo_ai.utils.typeid import TypeID, new_typeid


async def _file(
	session: AsyncSession,
	owner_id: str,
	label: str,
) -> File:
	resource = File(
		owner_id=owner_id,
		storage_backend="local",
		storage_key=f"{label}-{uuid4().hex}.txt",
		filename=f"{label}.txt",
	)
	session.add(resource)
	await session.flush()
	return resource


@pytest.mark.asyncio
async def test_attachment_refresh_invalidates_and_syncs_changed_refs(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	file_id = new_typeid("file")
	note_id = new_typeid("note")
	links = [
		MessageAttachment(message_id=new_typeid("msg"), file_id=file_id),
		MessageAttachment(message_id=new_typeid("msg"), note_id=note_id),
		MessageAttachment(message_id=new_typeid("msg"), file_id=file_id),
	]
	refs = attachment_resource_refs(links)
	invalidated: list[tuple[ResourceType, TypeID]] = []
	synced: list[tuple[ResourceType, TypeID]] = []

	async def record_invalidation(
		resource_type: ResourceType,
		resource_id: TypeID,
	) -> None:
		invalidated.append((resource_type, resource_id))

	async def record_sync(
		resource_refs: list[tuple[ResourceType, TypeID]],
		session: AsyncSession,
	) -> None:
		assert session is db_session
		synced.extend(resource_refs)

	monkeypatch.setattr(
		attachment_service,
		"invalidate_accessible_users_for_resource",
		record_invalidation,
	)
	monkeypatch.setattr(
		attachment_service,
		"sync_resource_refs_vector_acl",
		record_sync,
	)
	await refresh_attachment_access(refs, db_session)

	assert set(refs) == {
		(ResourceType.FILE, file_id),
		(ResourceType.NOTE, note_id),
	}
	assert invalidated == refs
	assert synced == refs


@pytest.mark.asyncio
async def test_owner_transfer_refreshes_attachment_vector_acl(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	old_owner = await create_user(db_session, f"oto_{uuid4().hex[:12]}")
	new_owner = await create_user(db_session, f"otn_{uuid4().hex[:12]}")
	file_owner = await create_user(db_session, f"otf_{uuid4().hex[:12]}")
	thread = Thread(owner_id=old_owner.id, title="owner transfer attachment")
	resource = await _file(db_session, file_owner.id, "owner-transfer-attachment")
	db_session.add(thread)
	await db_session.flush()
	message = UserMessage(thread_id=thread.id, sender_user_id=old_owner.id)
	db_session.add(message)
	await db_session.flush()
	db_session.add(
		MessageAttachment(message_id=message.id, position=0, file_id=resource.id)
	)
	await db_session.flush()
	sync_vector_acl = AsyncMock()
	monkeypatch.setattr(
		thread_service, "sync_resource_refs_vector_acl", sync_vector_acl
	)
	monkeypatch.setattr(thread_service, "vectorize_resource", AsyncMock())

	await thread_service.update_thread(
		thread.id,
		ThreadUpdate(owner_id=new_owner.id),
		db_session,
		principal_for(old_owner),
		create_event=False,
		update_activity=False,
	)

	metadata = await fetch_bulk_acl_metadata(
		[str(resource.id)],
		ResourceType.FILE,
		db_session,
	)
	assert str(new_owner.id) in metadata[str(resource.id)]["allowed_user_ids"]
	assert str(old_owner.id) not in metadata[str(resource.id)]["allowed_user_ids"]
	assert (
		await get_effective_access_level(
			db_session,
			principal_for(new_owner),
			ResourceType.FILE,
			resource.id,
		)
		== AccessLevel.READER
	)
	assert (
		await get_effective_access_level(
			db_session,
			principal_for(old_owner),
			ResourceType.FILE,
			resource.id,
		)
		is None
	)
	# root only: the attachment's own payload is repaired by the ACL sweep
	sync_vector_acl.assert_awaited_once_with(
		[(ResourceType.THREAD, thread.id)],
		db_session,
	)


@pytest.mark.asyncio
async def test_replacing_attachments_revokes_removed_resource_access(
	db_session: AsyncSession,
) -> None:
	owner = await create_user(db_session, f"rao_{uuid4().hex[:12]}")
	member = await create_user(db_session, f"ram_{uuid4().hex[:12]}")
	thread = Thread(owner_id=owner.id, title="replace attachments")
	db_session.add(thread)
	await db_session.flush()
	message = UserMessage(
		thread_id=thread.id,
		type=MessageType.USER,
		sender_user_id=owner.id,
	)
	db_session.add(message)
	first_file = await _file(db_session, owner.id, "first-attachment")
	second_file = await _file(db_session, owner.id, "second-attachment")
	db_session.add(
		AccessRule(
			thread_id=thread.id,
			subject_user_id=member.id,
			level=AccessLevel.EDITOR,
		)
	)
	await db_session.flush()
	owner_principal = principal_for(owner)
	member_principal = principal_for(member)
	await create_message_attachments(
		message.id,
		[ResourceAttachment(type=ResourceType.FILE, id=first_file.id)],
		db_session,
		owner_principal,
	)

	assert (
		await get_effective_access_level(
			db_session,
			member_principal,
			ResourceType.FILE,
			first_file.id,
		)
		== AccessLevel.READER
	)
	assert (
		await get_effective_access_level(
			db_session,
			owner_principal,
			ResourceType.FILE,
			first_file.id,
		)
		== AccessLevel.ADMIN
	)

	await replace_message_attachments(
		message.id,
		[ResourceAttachment(type=ResourceType.FILE, id=second_file.id)],
		db_session,
		owner_principal,
	)

	assert (
		await get_effective_access_level(
			db_session,
			member_principal,
			ResourceType.FILE,
			first_file.id,
		)
		is None
	)
	assert (
		await get_effective_access_level(
			db_session,
			member_principal,
			ResourceType.FILE,
			second_file.id,
		)
		== AccessLevel.READER
	)
	assert (
		await get_effective_access_level(
			db_session,
			owner_principal,
			ResourceType.FILE,
			first_file.id,
		)
		== AccessLevel.ADMIN
	)
	assert (
		await get_effective_access_level(
			db_session,
			owner_principal,
			ResourceType.FILE,
			second_file.id,
		)
		== AccessLevel.ADMIN
	)


@pytest.mark.asyncio
async def test_deleting_message_revokes_attachment_access(
	db_session: AsyncSession,
) -> None:
	owner = await create_user(db_session, f"dmo_{uuid4().hex[:12]}")
	member = await create_user(db_session, f"dmm_{uuid4().hex[:12]}")
	thread = Thread(owner_id=owner.id, title="delete attached message")
	db_session.add(thread)
	await db_session.flush()
	message = UserMessage(
		thread_id=thread.id,
		type=MessageType.USER,
		sender_user_id=owner.id,
	)
	db_session.add(message)
	resource = await _file(db_session, owner.id, "delete-message-attachment")
	db_session.add(
		AccessRule(
			thread_id=thread.id,
			subject_user_id=member.id,
			level=AccessLevel.READER,
		)
	)
	await db_session.flush()
	await create_message_attachments(
		message.id,
		[ResourceAttachment(type=ResourceType.FILE, id=resource.id)],
		db_session,
		principal_for(owner),
	)
	assert (
		await get_effective_access_level(
			db_session,
			principal_for(member),
			ResourceType.FILE,
			resource.id,
		)
		== AccessLevel.READER
	)

	await delete_user_message_turn(
		thread.id,
		message.id,
		db_session,
		principal=principal_for(owner),
	)

	assert (
		await get_effective_access_level(
			db_session,
			principal_for(member),
			ResourceType.FILE,
			resource.id,
		)
		is None
	)
	assert (
		await get_effective_access_level(
			db_session,
			principal_for(owner),
			ResourceType.FILE,
			resource.id,
		)
		== AccessLevel.ADMIN
	)


@pytest.mark.asyncio
async def test_deleting_thread_revokes_attachment_access(
	db_session: AsyncSession,
) -> None:
	owner = await create_user(db_session, f"dto_{uuid4().hex[:12]}")
	member = await create_user(db_session, f"dtm_{uuid4().hex[:12]}")
	thread = Thread(owner_id=owner.id, title="delete attachment thread")
	db_session.add(thread)
	await db_session.flush()
	message = UserMessage(thread_id=thread.id, sender_user_id=owner.id)
	db_session.add(message)
	resource = await _file(db_session, owner.id, "delete-thread-attachment")
	db_session.add(
		AccessRule(
			thread_id=thread.id,
			subject_user_id=member.id,
			level=AccessLevel.READER,
		)
	)
	await db_session.flush()
	await create_message_attachments(
		message.id,
		[ResourceAttachment(type=ResourceType.FILE, id=resource.id)],
		db_session,
		principal_for(owner),
	)
	assert (
		await get_effective_access_level(
			db_session,
			principal_for(member),
			ResourceType.FILE,
			resource.id,
		)
		== AccessLevel.READER
	)

	with patch(
		"api.v1.service.threads.core.remove_vectorized_resource",
		new=AsyncMock(),
	):
		await delete_thread(
			thread.id,
			db_session,
			principal=principal_for(owner),
		)

	assert (
		await get_effective_access_level(
			db_session,
			principal_for(member),
			ResourceType.FILE,
			resource.id,
		)
		is None
	)
	assert (
		await get_effective_access_level(
			db_session,
			principal_for(owner),
			ResourceType.FILE,
			resource.id,
		)
		== AccessLevel.ADMIN
	)


@pytest.mark.asyncio
async def test_detaching_one_of_two_message_links_keeps_access(
	db_session: AsyncSession,
) -> None:
	owner = await create_user(db_session, f"sao_{uuid4().hex[:12]}")
	member = await create_user(db_session, f"sam_{uuid4().hex[:12]}")
	thread = Thread(owner_id=owner.id, title="shared attachment")
	db_session.add(thread)
	await db_session.flush()
	first_message = UserMessage(thread_id=thread.id, sender_user_id=owner.id)
	second_message = UserMessage(thread_id=thread.id, sender_user_id=owner.id)
	db_session.add_all([first_message, second_message])
	resource = await _file(db_session, owner.id, "shared-attachment")
	db_session.add(
		AccessRule(
			thread_id=thread.id,
			subject_user_id=member.id,
			level=AccessLevel.READER,
		)
	)
	await db_session.flush()
	attachment = ResourceAttachment(type=ResourceType.FILE, id=resource.id)
	owner_principal = principal_for(owner)
	await create_message_attachments(
		first_message.id,
		[attachment],
		db_session,
		owner_principal,
	)
	await create_message_attachments(
		second_message.id,
		[attachment],
		db_session,
		owner_principal,
	)

	await replace_message_attachments(
		first_message.id,
		[],
		db_session,
		owner_principal,
	)

	assert (
		await get_effective_access_level(
			db_session,
			principal_for(member),
			ResourceType.FILE,
			resource.id,
		)
		== AccessLevel.READER
	)


@pytest.mark.asyncio
async def test_reader_cannot_reshare_attachment(
	db_session: AsyncSession,
) -> None:
	owner = await create_user(db_session, f"rso_{uuid4().hex[:12]}")
	reader = await create_user(db_session, f"rsr_{uuid4().hex[:12]}")
	thread = Thread(owner_id=reader.id, title="reshare destination")
	db_session.add(thread)
	await db_session.flush()
	message = UserMessage(thread_id=thread.id, sender_user_id=reader.id)
	resource = await _file(db_session, owner.id, "reader-reshare")
	db_session.add_all(
		[
			message,
			AccessRule(
				file_id=resource.id,
				subject_user_id=reader.id,
				level=AccessLevel.READER,
			),
		]
	)
	await db_session.flush()

	with pytest.raises(HTTPException) as forbidden:
		await create_message_attachments(
			message.id,
			[ResourceAttachment(type=ResourceType.FILE, id=resource.id)],
			db_session,
			principal_for(reader),
		)
	assert forbidden.value.status_code == 403
	assert forbidden.value.detail == {
		"code": "attachment_admin_required",
		"message": "admin access is required to share this resource",
	}


@pytest.mark.asyncio
async def test_thread_cannot_attach_itself(
	db_session: AsyncSession,
) -> None:
	owner = await create_user(db_session, f"sso_{uuid4().hex[:12]}")
	thread = Thread(owner_id=owner.id, title="self attachment")
	db_session.add(thread)
	await db_session.flush()
	message = UserMessage(thread_id=thread.id, sender_user_id=owner.id)
	db_session.add(message)
	await db_session.flush()

	with pytest.raises(HTTPException) as conflict:
		await create_message_attachments(
			message.id,
			[ResourceAttachment(type=ResourceType.THREAD, id=thread.id)],
			db_session,
			principal_for(owner),
		)
	assert conflict.value.status_code == 409
	assert conflict.value.detail == {
		"code": "thread_self_attachment",
		"message": "a thread cannot be attached to one of its own messages",
	}


@pytest.mark.asyncio
async def test_attachment_access_does_not_cross_second_attachment_edge(
	db_session: AsyncSession,
) -> None:
	owner = await create_user(db_session, f"nto_{uuid4().hex[:12]}")
	reader = await create_user(db_session, f"ntr_{uuid4().hex[:12]}")
	inner = Thread(owner_id=owner.id, title="inner shared thread")
	outer = Thread(owner_id=owner.id, title="outer shared thread")
	db_session.add_all([inner, outer])
	await db_session.flush()
	inner_message = UserMessage(thread_id=inner.id, sender_user_id=owner.id)
	outer_message = UserMessage(thread_id=outer.id, sender_user_id=owner.id)
	resource = await _file(db_session, owner.id, "nested-attachment")
	db_session.add_all(
		[
			inner_message,
			outer_message,
			AccessRule(
				thread_id=outer.id,
				subject_user_id=reader.id,
				level=AccessLevel.READER,
			),
		]
	)
	await db_session.flush()
	owner_principal = principal_for(owner)
	await create_message_attachments(
		inner_message.id,
		[ResourceAttachment(type=ResourceType.FILE, id=resource.id)],
		db_session,
		owner_principal,
	)
	await create_message_attachments(
		outer_message.id,
		[ResourceAttachment(type=ResourceType.THREAD, id=inner.id)],
		db_session,
		owner_principal,
	)

	assert (
		await get_effective_access_level(
			db_session,
			principal_for(reader),
			ResourceType.THREAD,
			inner.id,
		)
		== AccessLevel.READER
	)
	assert (
		await get_effective_access_level(
			db_session,
			principal_for(reader),
			ResourceType.FILE,
			resource.id,
		)
		is None
	)
