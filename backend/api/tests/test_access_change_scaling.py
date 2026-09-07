"""the finding-4 decision: ACL changes cost O(1) in subtree size.

sharing a thread must not get more expensive because the thread has more
attachments. these tests pin the four properties the decision names: constant
redis writes, constant advisory locks, no collateral invalidation, and
convergence whichever order attach and share happen in.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import advisory_locks
from api.database.post_commit import run_post_commit_actions
from api.models.event import Event
from api.models.event_types import EventType
from api.models.file import File
from api.models.message import UserMessage
from api.models.message_attachment import MessageAttachment
from api.models.thread import Thread
from api.models.user import User
from api.permissions import AccessLevel, ResourceType
from api.schemas.access_rule import AccessRuleCreate
from api.tests.factories import create_user, principal_for
from api.v1.service import access_rules as access_rule_service
from api.v1.service.authorization import cache as authorization_cache
from api.v1.service.authorization import list_accessible_user_ids_for_resources
from nokodo_ai.utils.typeid import TypeID


async def _thread_with_attachments(
	session: AsyncSession,
	owner: User,
	count: int,
	label: str,
) -> tuple[Thread, list[File]]:
	"""build a thread whose message attaches `count` files."""
	thread = Thread(owner_id=owner.id, title=f"{label} thread")
	session.add(thread)
	await session.flush()
	message = UserMessage(thread_id=thread.id, sender_user_id=owner.id)
	session.add(message)
	await session.flush()
	files: list[File] = []
	for index in range(count):
		file = File(
			owner_id=owner.id,
			storage_backend="local",
			storage_key=f"{label}-{index}-{uuid4().hex}",
			filename=f"{label}-{index}.txt",
		)
		session.add(file)
		await session.flush()
		session.add(
			MessageAttachment(
				message_id=message.id,
				position=index,
				file_id=file.id,
			)
		)
		files.append(file)
	await session.flush()
	return thread, files


async def _share(
	session: AsyncSession,
	thread: Thread,
	owner: User,
	member: User,
) -> None:
	await access_rule_service.set_access_rules(
		ResourceType.THREAD,
		thread.id,
		[AccessRuleCreate(subject_user_id=member.id, level=AccessLevel.EDITOR)],
		session,
		principal_for(owner),
	)
	await session.commit()
	await run_post_commit_actions(session)


@pytest.mark.parametrize("attachment_count", [0, 6, 25])
@pytest.mark.asyncio
async def test_sharing_costs_the_same_at_any_attachment_count(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
	attachment_count: int,
) -> None:
	"""redis writes and advisory locks are O(1) in the size of the subtree."""
	owner = await create_user(db_session, f"sco_{uuid4().hex[:12]}")
	member = await create_user(db_session, f"scm_{uuid4().hex[:12]}")
	thread, _ = await _thread_with_attachments(
		db_session, owner, attachment_count, f"scale-{attachment_count}"
	)
	await db_session.commit()

	incremented: list[str] = []
	locked: list[tuple[str, TypeID]] = []

	# the invalidation path issues ONE pipelined multi-increment for the whole
	# ref set, so round-trips are observed here, not at the per-key `increment`.
	async def record_increment_many(keys: list[str]) -> bool:
		incremented.extend(keys)
		return True

	original_lock = advisory_locks.acquire_resource_write_lock

	async def record_lock(
		session: AsyncSession,
		namespace: str,
		resource_id: TypeID,
	) -> None:
		locked.append((namespace, resource_id))
		await original_lock(session, namespace, resource_id)

	monkeypatch.setattr(
		authorization_cache.cache, "increment_many", record_increment_many
	)
	monkeypatch.setattr(
		"api.v1.service.authorization.changes.acquire_resource_write_lock",
		record_lock,
	)

	await _share(db_session, thread, owner, member)

	# exactly one lock and one version bump: the thread itself
	assert locked == [("thread", thread.id)]
	assert incremented == [
		authorization_cache._accessible_users_version_key(
			ResourceType.THREAD, thread.id
		)
	]


@pytest.mark.asyncio
async def test_sharing_emits_one_subtree_marked_event(
	db_session: AsyncSession,
) -> None:
	"""one root event carries `subtree`, standing in for every descendant."""
	owner = await create_user(db_session, f"sto_{uuid4().hex[:12]}")
	member = await create_user(db_session, f"stm_{uuid4().hex[:12]}")
	thread, _ = await _thread_with_attachments(db_session, owner, 3, "subtree")
	await db_session.commit()

	await _share(db_session, thread, owner, member)

	events = list(
		await db_session.scalars(
			select(Event).where(
				Event.type == EventType.ACCESS_UPDATED,
				Event.scope_id == thread.id,
			)
		)
	)
	assert len(events) == 1
	assert events[0].data["subtree"] is True
	assert events[0].data["resource_id"] == str(thread.id)


@pytest.mark.asyncio
async def test_attached_file_reader_sees_the_new_answer_after_sharing(
	db_session: AsyncSession,
) -> None:
	"""a descendant's cached answer expires itself on its next read."""
	owner = await create_user(db_session, f"afo_{uuid4().hex[:12]}")
	member = await create_user(db_session, f"afm_{uuid4().hex[:12]}")
	thread, files = await _thread_with_attachments(db_session, owner, 1, "attached")
	file_ref = [(ResourceType.FILE, files[0].id)]
	await db_session.commit()

	# fill the file's cache entry before the share
	assert member.id not in await list_accessible_user_ids_for_resources(
		file_ref, db_session
	)

	await _share(db_session, thread, owner, member)

	assert member.id in await list_accessible_user_ids_for_resources(
		file_ref, db_session
	)


@pytest.mark.asyncio
async def test_sharing_one_thread_leaves_another_threads_entries_valid(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""an unrelated thread is never invalidated by someone else's ACL change."""
	owner = await create_user(db_session, f"uto_{uuid4().hex[:12]}")
	member = await create_user(db_session, f"utm_{uuid4().hex[:12]}")
	shared, _ = await _thread_with_attachments(db_session, owner, 1, "shared")
	unrelated, _ = await _thread_with_attachments(db_session, owner, 1, "unrelated")
	unrelated_ref = [(ResourceType.THREAD, unrelated.id)]
	await db_session.commit()

	before = await list_accessible_user_ids_for_resources(unrelated_ref, db_session)

	# what "stays valid" means concretely: nothing bumps the unrelated
	# resource's version, so entries keyed on it remain addressable.
	incremented: list[str] = []

	async def record_increment_many(keys: list[str]) -> bool:
		incremented.extend(keys)
		return True

	monkeypatch.setattr(
		authorization_cache.cache, "increment_many", record_increment_many
	)
	await _share(db_session, shared, owner, member)

	unrelated_key = authorization_cache._accessible_users_version_key(
		ResourceType.THREAD, unrelated.id
	)
	assert unrelated_key not in incremented, "unrelated entry was invalidated"
	assert incremented == [
		authorization_cache._accessible_users_version_key(
			ResourceType.THREAD, shared.id
		)
	]

	after = await list_accessible_user_ids_for_resources(unrelated_ref, db_session)
	assert set(after) == set(before)


@pytest.mark.asyncio
async def test_attach_then_share_and_share_then_attach_converge(
	db_session: AsyncSession,
) -> None:
	"""order does not matter: both sequences end with the same answer."""
	owner = await create_user(db_session, f"cvo_{uuid4().hex[:12]}")
	member = await create_user(db_session, f"cvm_{uuid4().hex[:12]}")

	# attach, then share
	first, first_files = await _thread_with_attachments(db_session, owner, 1, "attach1")
	await db_session.commit()
	await _share(db_session, first, owner, member)
	attach_then_share = await list_accessible_user_ids_for_resources(
		[(ResourceType.FILE, first_files[0].id)], db_session
	)

	# share, then attach
	second, _ = await _thread_with_attachments(db_session, owner, 0, "attach2")
	await db_session.commit()
	await _share(db_session, second, owner, member)
	message = UserMessage(thread_id=second.id, sender_user_id=owner.id)
	db_session.add(message)
	await db_session.flush()
	late_file = File(
		owner_id=owner.id,
		storage_backend="local",
		storage_key=f"late-{uuid4().hex}",
		filename="late.txt",
	)
	db_session.add(late_file)
	await db_session.flush()
	db_session.add(
		MessageAttachment(message_id=message.id, position=0, file_id=late_file.id)
	)
	await db_session.commit()
	share_then_attach = await list_accessible_user_ids_for_resources(
		[(ResourceType.FILE, late_file.id)], db_session
	)

	# convergence means the SAME answer, not merely that the member appears
	assert set(attach_then_share) == set(share_then_attach)
	assert member.id in attach_then_share


@pytest.mark.asyncio
async def test_ancestor_bumped_mid_resolve_is_not_cached(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""an answer racing an ancestor's ACL change is never stored.

	the stamp is read before the ancestor's rows, so a bump landing during the
	resolve makes the post-resolve re-read disagree. storing the entry then
	would publish data computed from the OLD acl under the NEW version, and it
	would validate as fresh until the next bump.
	"""
	owner = await create_user(db_session, f"rco_{uuid4().hex[:12]}")
	thread, files = await _thread_with_attachments(db_session, owner, 1, "race")
	file_ref = [(ResourceType.FILE, files[0].id)]
	await db_session.commit()

	thread_version_key = authorization_cache._accessible_users_version_key(
		ResourceType.THREAD, thread.id
	)
	stored: list[str] = []
	original_set = authorization_cache.cache.set
	original_resolve = authorization_cache.resolve_accessible_user_ids

	async def racing_resolve(
		resource_type: ResourceType,
		resource_id: TypeID,
		session: AsyncSession,
		required_level: AccessLevel = AccessLevel.READER,
		consulted_refs: dict[tuple[ResourceType, TypeID], int] | None = None,
	) -> list[TypeID]:
		result = await original_resolve(
			resource_type,
			resource_id,
			session,
			required_level,
			consulted_refs=consulted_refs,
		)
		# the ancestor changes after its version was stamped, before the store
		await authorization_cache.cache.increment(thread_version_key)
		return result

	async def record_set(
		key: str,
		value: object,
		ttl: int = 60,
		tags: list[str] | None = None,
		nx: bool = False,
	) -> bool:
		stored.append(key)
		return await original_set(key, value, ttl, tags, nx)

	monkeypatch.setattr(
		authorization_cache, "resolve_accessible_user_ids", racing_resolve
	)
	monkeypatch.setattr(authorization_cache.cache, "set", record_set)

	await list_accessible_user_ids_for_resources(file_ref, db_session)

	assert not stored, "an entry racing an ancestor bump was cached"
