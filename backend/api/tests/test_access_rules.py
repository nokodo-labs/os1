"""access-rule visibility and mutation authorization coverage."""

from __future__ import annotations

import asyncio
import runpy
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.database.post_commit import (
	pending_post_commit_action_count,
	run_post_commit_actions,
)
from api.models.access_rule import AccessLevel, AccessRule
from api.models.agent import Agent
from api.models.event import Event
from api.models.event_types import EventType
from api.models.note import Note
from api.models.role import Role
from api.models.thread import Thread
from api.permissions import ResourceType
from api.schemas.access_rule import (
	AccessRuleCreate,
	AccessRuleUpdate,
)
from api.tests.factories import create_user, principal_for
from api.v1.service import access_rules as access_rule_service
from api.v1.service.authentication import Principal
from api.v1.service.authorization import ACL_RESOURCE_TYPES
from nokodo_ai.utils.typeid import TypeID, new_typeid


DEDUPE_ACCESS_RULES_SQL = str(
	runpy.run_path(
		str(
			Path(__file__).parents[1]
			/ "migrations"
			/ "versions"
			/ "20260903_1629-417c7d54364d_access_rule_uniqueness.py"
		)
	)["DEDUPE_ACCESS_RULES_SQL"]
)


_ACL_RESOURCE_TYPES = sorted(
	ACL_RESOURCE_TYPES, key=lambda resource_type: resource_type.value
)


@pytest.mark.asyncio
async def test_note_rule_list_is_admin_visible_and_never_level_filtered(
	db_session: AsyncSession,
) -> None:
	owner = await create_user(db_session, f"nao_{uuid4().hex[:12]}")
	reader = await create_user(db_session, f"nar_{uuid4().hex[:12]}")
	editor = await create_user(db_session, f"nae_{uuid4().hex[:12]}")
	note = Note(user_id=owner.id, title="ACL visibility", content="private")
	db_session.add(note)
	await db_session.flush()
	db_session.add_all(
		[
			AccessRule(
				note_id=note.id,
				level=AccessLevel.READER,
				order_index=0,
			),
			AccessRule(
				note_id=note.id,
				subject_user_id=reader.id,
				level=AccessLevel.READER,
				order_index=1,
			),
			AccessRule(
				note_id=note.id,
				subject_user_id=editor.id,
				level=AccessLevel.EDITOR,
				order_index=2,
			),
		]
	)
	await db_session.flush()

	for principal in (principal_for(reader), principal_for(editor)):
		with pytest.raises(HTTPException) as exc:
			await access_rule_service.list_access_rules(
				ResourceType.NOTE,
				note.id,
				db_session,
				principal,
			)
		assert exc.value.status_code == 404

	rules = await access_rule_service.list_access_rules(
		ResourceType.NOTE,
		note.id,
		db_session,
		principal_for(owner),
	)
	assert [(rule.subject_user_id, rule.level) for rule in rules] == [
		(None, AccessLevel.READER),
		(reader.id, AccessLevel.READER),
		(editor.id, AccessLevel.EDITOR),
	]


@pytest.mark.asyncio
@pytest.mark.parametrize("resource_type", [ResourceType.THREAD, ResourceType.NOTE])
async def test_rule_mutation_requires_admin_regardless_of_list_visibility(
	db_session: AsyncSession,
	resource_type: ResourceType,
) -> None:
	owner = await create_user(db_session, f"amo_{uuid4().hex[:12]}")
	member = await create_user(db_session, f"amm_{uuid4().hex[:12]}")
	if resource_type == ResourceType.THREAD:
		resource = Thread(owner_id=owner.id, title="mutation boundary")
	else:
		resource = Note(user_id=owner.id, title="mutation boundary", content="private")
	db_session.add(resource)
	await db_session.flush()
	if resource_type == ResourceType.THREAD:
		db_session.add(
			AccessRule(
				thread_id=resource.id,
				subject_user_id=member.id,
				level=AccessLevel.READER,
			)
		)
	else:
		db_session.add(
			AccessRule(
				note_id=resource.id,
				subject_user_id=member.id,
				level=AccessLevel.EDITOR,
			)
		)
	await db_session.flush()

	with pytest.raises(HTTPException) as exc:
		await access_rule_service.set_access_rules(
			resource_type,
			resource.id,
			[
				AccessRuleCreate(
					subject_user_id=member.id,
					level=AccessLevel.ADMIN,
				)
			],
			db_session,
			principal_for(member),
		)
	assert exc.value.status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("resource_type", _ACL_RESOURCE_TYPES)
async def test_every_acl_resource_mutation_requires_admin(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
	resource_type: ResourceType,
) -> None:
	principal = principal_for(await create_user(db_session, f"aat_{uuid4().hex[:12]}"))
	resource_id = new_typeid(resource_type.value)
	require_access = AsyncMock()
	set_rules = AsyncMock(return_value=[])
	monkeypatch.setattr(access_rule_service, "require_resource_access", require_access)
	monkeypatch.setattr(access_rule_service, "_set_rules_impl", set_rules)

	assert (
		await access_rule_service.set_access_rules(
			resource_type,
			resource_id,
			[],
			db_session,
			principal,
		)
		== []
	)
	require_access.assert_awaited_once_with(
		resource_id,
		db_session,
		principal,
		resource_type,
		required_level=AccessLevel.ADMIN,
	)


@pytest.mark.asyncio
async def test_thread_readers_can_list_rules_but_note_readers_cannot(
	db_session: AsyncSession,
) -> None:
	owner = await create_user(db_session, f"avo_{uuid4().hex[:12]}")
	reader = await create_user(db_session, f"avr_{uuid4().hex[:12]}")
	thread = Thread(owner_id=owner.id, title="visible ACL")
	note = Note(user_id=owner.id, title="hidden ACL", content="private")
	db_session.add_all([thread, note])
	await db_session.flush()
	db_session.add_all(
		[
			AccessRule(
				thread_id=thread.id,
				subject_user_id=reader.id,
				level=AccessLevel.READER,
			),
			AccessRule(
				note_id=note.id,
				subject_user_id=reader.id,
				level=AccessLevel.READER,
			),
		]
	)
	await db_session.flush()
	assert await access_rule_service.list_access_rules(
		ResourceType.THREAD,
		thread.id,
		db_session,
		principal_for(reader),
	)
	with pytest.raises(HTTPException) as hidden:
		await access_rule_service.list_access_rules(
			ResourceType.NOTE,
			note.id,
			db_session,
			principal_for(reader),
		)
	assert hidden.value.status_code == 404


@pytest.mark.asyncio
async def test_bulk_acl_update_persists_one_canonical_event(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	owner = await create_user(db_session, f"aeo_{uuid4().hex[:12]}")
	first = await create_user(db_session, f"aef_{uuid4().hex[:12]}")
	second = await create_user(db_session, f"aes_{uuid4().hex[:12]}")
	thread = Thread(owner_id=owner.id, title="event ACL")
	db_session.add(thread)
	await db_session.flush()
	existing = AccessRule(
		thread_id=thread.id,
		subject_user_id=first.id,
		level=AccessLevel.READER,
		order_index=0,
	)
	db_session.add(existing)
	await db_session.commit()
	fanout = AsyncMock()
	monkeypatch.setattr(access_rule_service, "fanout_event", fanout)

	await access_rule_service.set_access_rules(
		ResourceType.THREAD,
		thread.id,
		[
			AccessRuleCreate(
				subject_user_id=first.id,
				level=AccessLevel.ADMIN,
				order_index=0,
			),
			AccessRuleCreate(
				subject_user_id=second.id,
				level=AccessLevel.EDITOR,
				order_index=1,
			),
		],
		db_session,
		principal_for(owner),
	)
	await db_session.commit()
	await run_post_commit_actions(db_session)

	events = list(
		await db_session.scalars(
			select(Event).where(
				Event.type == EventType.ACCESS_UPDATED,
				Event.scope_id == thread.id,
			)
		)
	)
	assert len(events) == 1
	data = events[0].data
	assert data["resource_type"] == "thread"
	assert data["resource_id"] == str(thread.id)
	assert data["actor_user_id"] == str(owner.id)
	assert data["owner_user_id"] == str(owner.id)
	assert data["revision"] == 1
	assert len(data["changes"]) == 2
	assert "rules_before" not in data
	assert "rules_after" not in data
	assert all(
		"metadata" not in snapshot
		for change in data["changes"]
		for snapshot in change.values()
		if snapshot is not None
	)
	assert events[0].resource_revision == 1
	fanout.assert_awaited_once()


@pytest.mark.asyncio
async def test_acl_mutation_is_flush_only_and_runs_effects_after_commit(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	owner = await create_user(db_session, f"afo_{uuid4().hex[:12]}")
	member = await create_user(db_session, f"afm_{uuid4().hex[:12]}")
	thread = Thread(owner_id=owner.id, title="flush-only ACL")
	db_session.add(thread)
	await db_session.commit()
	fanout = AsyncMock()
	monkeypatch.setattr(access_rule_service, "fanout_event", fanout)

	await access_rule_service.grant_user_access_unchecked(
		ResourceType.THREAD,
		thread.id,
		member.id,
		db_session,
		level=AccessLevel.READER,
		actor_user_id=owner.id,
	)
	assert db_session.in_transaction()
	fanout.assert_not_awaited()

	await db_session.commit()
	fanout.assert_not_awaited()
	await run_post_commit_actions(db_session)
	fanout.assert_awaited_once()


@pytest.mark.asyncio
async def test_duplicate_subject_resource_is_rejected_by_database(
	db_session: AsyncSession,
) -> None:
	owner = await create_user(db_session, f"ado_{uuid4().hex[:12]}")
	member = await create_user(db_session, f"adm_{uuid4().hex[:12]}")
	thread = Thread(owner_id=owner.id, title="duplicate ACL constraint")
	db_session.add(thread)
	await db_session.flush()
	db_session.add(
		AccessRule(
			thread_id=thread.id,
			subject_user_id=member.id,
			level=AccessLevel.READER,
		)
	)
	await db_session.flush()
	savepoint = await db_session.begin_nested()
	db_session.add(
		AccessRule(
			thread_id=thread.id,
			subject_user_id=member.id,
			level=AccessLevel.ADMIN,
		)
	)
	with pytest.raises(IntegrityError) as duplicate:
		await db_session.flush()
	await savepoint.rollback()
	assert "uq_access_rule_subject_resource" in str(duplicate.value.orig)


@pytest.mark.asyncio
async def test_duplicate_subjectless_resource_is_rejected_by_database(
	db_session: AsyncSession,
) -> None:
	owner = await create_user(db_session, f"aso_{uuid4().hex[:12]}")
	thread = Thread(owner_id=owner.id, title="duplicate subjectless constraint")
	db_session.add(thread)
	await db_session.flush()
	db_session.add(AccessRule(thread_id=thread.id, level=AccessLevel.READER))
	await db_session.flush()
	savepoint = await db_session.begin_nested()
	db_session.add(AccessRule(thread_id=thread.id, level=AccessLevel.EDITOR))
	with pytest.raises(IntegrityError) as duplicate:
		await db_session.flush()
	await savepoint.rollback()
	assert "uq_access_rule_subject_resource" in str(duplicate.value.orig)


@pytest.mark.asyncio
async def test_same_subject_on_different_resources_is_allowed(
	db_session: AsyncSession,
) -> None:
	owner = await create_user(db_session, f"sro_{uuid4().hex[:12]}")
	member = await create_user(db_session, f"srm_{uuid4().hex[:12]}")
	first = Thread(owner_id=owner.id, title="first resource")
	second = Thread(owner_id=owner.id, title="second resource")
	db_session.add_all([first, second])
	await db_session.flush()
	db_session.add_all(
		[
			AccessRule(thread_id=first.id, subject_user_id=member.id),
			AccessRule(thread_id=second.id, subject_user_id=member.id),
		]
	)
	await db_session.flush()
	assert (
		len(
			list(
				await db_session.scalars(
					select(AccessRule).where(AccessRule.subject_user_id == member.id)
				)
			)
		)
		== 2
	)


@pytest.mark.asyncio
async def test_access_rule_requires_exactly_one_resource(
	db_session: AsyncSession,
) -> None:
	owner = await create_user(db_session, f"iro_{uuid4().hex[:12]}")
	thread = Thread(owner_id=owner.id, title="resource invariant")
	note = Note(user_id=owner.id, title="resource invariant", content="")
	db_session.add_all([thread, note])
	await db_session.flush()

	for rule in (
		AccessRule(level=AccessLevel.READER),
		AccessRule(
			thread_id=thread.id,
			note_id=note.id,
			level=AccessLevel.READER,
		),
	):
		savepoint = await db_session.begin_nested()
		db_session.add(rule)
		with pytest.raises(IntegrityError) as invalid:
			await db_session.flush()
		await savepoint.rollback()
		assert "ck_access_rules_single_resource" in str(invalid.value.orig)


@pytest.mark.asyncio
async def test_migration_dedupe_keeps_current_ordering_winner(
	db_session: AsyncSession,
) -> None:
	owner = await create_user(db_session, f"mdo_{uuid4().hex[:12]}")
	member = await create_user(db_session, f"mdm_{uuid4().hex[:12]}")
	thread = Thread(owner_id=owner.id, title="migration dedupe")
	db_session.add(thread)
	await db_session.flush()
	await db_session.execute(
		text("ALTER TABLE access_rules DROP CONSTRAINT uq_access_rule_subject_resource")
	)
	tied_ids = sorted((new_typeid("arule"), new_typeid("arule")))
	rules = [
		AccessRule(
			id=new_typeid("arule"),
			thread_id=thread.id,
			subject_user_id=member.id,
			level=AccessLevel.READER,
			order_index=1,
		),
		AccessRule(
			id=tied_ids[0],
			thread_id=thread.id,
			subject_user_id=member.id,
			level=AccessLevel.EDITOR,
			order_index=2,
		),
		AccessRule(
			id=tied_ids[1],
			thread_id=thread.id,
			subject_user_id=member.id,
			level=AccessLevel.ADMIN,
			order_index=2,
		),
	]
	db_session.add_all(rules)
	await db_session.flush()
	await db_session.execute(text(DEDUPE_ACCESS_RULES_SQL))
	remaining = list(
		await db_session.scalars(
			select(AccessRule).where(AccessRule.thread_id == thread.id)
		)
	)
	assert [rule.id for rule in remaining] == [tied_ids[1]]


@pytest.mark.asyncio
async def test_agent_access_rejects_role_subject_without_roles_manage(
	db_session: AsyncSession,
) -> None:
	manager = await create_user(db_session, f"aro_{uuid4().hex[:12]}")
	agent = Agent(name="role subject agent")
	db_session.add(agent)
	await db_session.flush()
	principal = Principal.for_user(
		user=manager,
		group_ids=(),
		permissions=frozenset({"agents:manage"}),
	)
	with pytest.raises(HTTPException) as forbidden:
		await access_rule_service.set_access_rules(
			ResourceType.AGENT,
			agent.id,
			[AccessRuleCreate(subject_role_id=new_typeid("role"))],
			db_session,
			principal,
		)
	assert forbidden.value.status_code == 403


@pytest.mark.asyncio
async def test_role_subject_update_requires_roles_manage(
	db_session: AsyncSession,
) -> None:
	owner = await create_user(db_session, f"ruo_{uuid4().hex[:12]}")
	role = Role(name=f"role-update-{uuid4().hex[:12]}")
	note = Note(user_id=owner.id, title="role update", content="private")
	db_session.add_all([role, note])
	await db_session.flush()
	rule = AccessRule(
		note_id=note.id,
		subject_role_id=role.id,
		level=AccessLevel.READER,
	)
	db_session.add(rule)
	await db_session.flush()

	with pytest.raises(HTTPException) as forbidden:
		await access_rule_service.update_access_rule(
			ResourceType.NOTE,
			note.id,
			rule.id,
			AccessRuleUpdate(level=AccessLevel.ADMIN),
			db_session,
			principal_for(owner),
		)
	assert forbidden.value.status_code == 403


@pytest.mark.asyncio
async def test_role_subject_delete_requires_roles_manage(
	db_session: AsyncSession,
) -> None:
	owner = await create_user(db_session, f"rdo_{uuid4().hex[:12]}")
	role = Role(name=f"role-delete-{uuid4().hex[:12]}")
	note = Note(user_id=owner.id, title="role delete", content="private")
	db_session.add_all([role, note])
	await db_session.flush()
	rule = AccessRule(
		note_id=note.id,
		subject_role_id=role.id,
		level=AccessLevel.READER,
	)
	db_session.add(rule)
	await db_session.flush()

	with pytest.raises(HTTPException) as forbidden:
		await access_rule_service.delete_access_rule(
			ResourceType.NOTE,
			note.id,
			rule.id,
			db_session,
			principal_for(owner),
		)
	assert forbidden.value.status_code == 403


@pytest.mark.asyncio
async def test_role_subject_replace_removal_requires_roles_manage(
	db_session: AsyncSession,
) -> None:
	owner = await create_user(db_session, f"rro_{uuid4().hex[:12]}")
	role = Role(name=f"role-replace-{uuid4().hex[:12]}")
	note = Note(user_id=owner.id, title="role replace", content="private")
	db_session.add_all([role, note])
	await db_session.flush()
	db_session.add(
		AccessRule(
			note_id=note.id,
			subject_role_id=role.id,
			level=AccessLevel.READER,
		)
	)
	await db_session.flush()

	with pytest.raises(HTTPException) as forbidden:
		await access_rule_service.set_access_rules(
			ResourceType.NOTE,
			note.id,
			[],
			db_session,
			principal_for(owner),
		)
	assert forbidden.value.status_code == 403


@pytest.mark.asyncio
async def test_access_rule_create_preserves_explicit_zero_order(
	db_session: AsyncSession,
) -> None:
	owner = await create_user(db_session, f"azo_{uuid4().hex[:12]}")
	member = await create_user(db_session, f"azm_{uuid4().hex[:12]}")
	thread = Thread(owner_id=owner.id, title="zero order")
	db_session.add(thread)
	await db_session.flush()
	db_session.add(
		AccessRule(
			thread_id=thread.id,
			level=AccessLevel.READER,
			order_index=5,
		)
	)
	await db_session.commit()
	rule = await access_rule_service.create_access_rule(
		ResourceType.THREAD,
		thread.id,
		AccessRuleCreate(
			subject_user_id=member.id,
			level=AccessLevel.READER,
			order_index=0,
		),
		db_session,
		principal_for(owner),
	)
	assert rule.order_index == 0


@pytest.mark.asyncio
async def test_bulk_acl_update_preserves_omitted_metadata(
	db_session: AsyncSession,
) -> None:
	owner = await create_user(db_session, f"amo_{uuid4().hex[:12]}")
	member = await create_user(db_session, f"amm_{uuid4().hex[:12]}")
	thread = Thread(owner_id=owner.id, title="metadata")
	db_session.add(thread)
	await db_session.flush()
	rule = AccessRule(
		thread_id=thread.id,
		subject_user_id=member.id,
		level=AccessLevel.READER,
		order_index=0,
	)
	rule.set_metadata(public={"label": "keep"})
	db_session.add(rule)
	await db_session.commit()
	updated = await access_rule_service.set_access_rules(
		ResourceType.THREAD,
		thread.id,
		[
			AccessRuleCreate(
				subject_user_id=member.id,
				level=AccessLevel.EDITOR,
				order_index=0,
			)
		],
		db_session,
		principal_for(owner),
	)
	assert updated[0].public_metadata == {"label": "keep"}


@pytest.mark.asyncio
async def test_noop_acl_update_enqueues_no_post_commit_actions(
	db_session: AsyncSession,
) -> None:
	owner = await create_user(db_session, f"noo_{uuid4().hex[:12]}")
	member = await create_user(db_session, f"nom_{uuid4().hex[:12]}")
	thread = Thread(owner_id=owner.id, title="no-op ACL")
	db_session.add(thread)
	await db_session.flush()
	rule = AccessRule(
		thread_id=thread.id,
		subject_user_id=member.id,
		level=AccessLevel.READER,
		order_index=0,
	)
	rule.set_metadata(public={"label": "keep"})
	db_session.add(rule)
	await db_session.commit()
	pending_before = pending_post_commit_action_count(db_session)

	await access_rule_service.set_access_rules(
		ResourceType.THREAD,
		thread.id,
		[
			AccessRuleCreate(
				subject_user_id=member.id,
				level=AccessLevel.READER,
				order_index=0,
			)
		],
		db_session,
		principal_for(owner),
	)

	assert pending_post_commit_action_count(db_session) == pending_before


@pytest.mark.asyncio
async def test_metadata_only_acl_update_emits_no_access_event(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	owner = await create_user(db_session, f"ano_{uuid4().hex[:12]}")
	member = await create_user(db_session, f"anm_{uuid4().hex[:12]}")
	thread = Thread(owner_id=owner.id, title="metadata only")
	db_session.add(thread)
	await db_session.flush()
	rule = AccessRule(
		thread_id=thread.id,
		subject_user_id=member.id,
		level=AccessLevel.READER,
		order_index=0,
	)
	db_session.add(rule)
	await db_session.commit()
	fanout = AsyncMock()
	monkeypatch.setattr(access_rule_service, "fanout_event", fanout)
	await access_rule_service.update_access_rule(
		ResourceType.THREAD,
		thread.id,
		rule.id,
		AccessRuleUpdate(metadata={"label": "private detail"}),
		db_session,
		principal_for(owner),
	)
	assert not await db_session.scalar(
		select(Event.id).where(
			Event.type == EventType.ACCESS_UPDATED,
			Event.scope_id == thread.id,
		)
	)
	fanout.assert_not_awaited()


@pytest.mark.asyncio
async def test_concurrent_acl_events_have_serialized_revisions(
	db_session: AsyncSession,
) -> None:
	from api.database.main import async_session_local

	owner = await create_user(db_session, f"aco_{uuid4().hex[:12]}")
	first = await create_user(db_session, f"acf_{uuid4().hex[:12]}")
	second = await create_user(db_session, f"acs_{uuid4().hex[:12]}")
	thread = Thread(owner_id=owner.id, title="concurrent ACL")
	db_session.add(thread)
	await db_session.commit()

	async def grant(user_id: TypeID) -> None:
		async with async_session_local() as session:
			await access_rule_service.grant_user_access_unchecked(
				ResourceType.THREAD,
				thread.id,
				user_id,
				session,
				level=AccessLevel.READER,
				actor_user_id=owner.id,
			)
			await session.commit()
			await run_post_commit_actions(session)

	await asyncio.gather(grant(first.id), grant(second.id))
	events = list(
		await db_session.scalars(
			select(Event)
			.where(
				Event.type == EventType.ACCESS_UPDATED,
				Event.scope_id == thread.id,
			)
			.order_by(Event.created_at, Event.id)
		)
	)
	assert len(events) == 2
	assert sorted(event.data["revision"] for event in events) == [1, 2]
	assert sorted(
		revision
		for event in events
		if (revision := event.resource_revision) is not None
	) == [1, 2]
	assert all(len(event.data["changes"]) == 1 for event in events)
	assert all("rules_before" not in event.data for event in events)
	assert all("rules_after" not in event.data for event in events)
