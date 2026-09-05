"""property tests: the SQL predicate and the python resolver must agree.

both engines answer the same question - can this principal reach this resource
at this level - through independent code paths. these tests build randomized
rule sets and inheritance graphs and assert the two answers match on every one,
which is the only check that catches a divergence introduced on one side only.
"""

import random
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.access_rule import AccessLevel, AccessRule
from api.models.agent import Agent
from api.models.file import File
from api.models.group import Group, GroupMembership
from api.models.message import UserMessage
from api.models.message_attachment import MessageAttachment
from api.models.project import Project
from api.models.reminder import Reminder, ReminderList
from api.models.thread import Thread
from api.models.thread_participant import ThreadParticipant
from api.models.user import User
from api.permissions import ResourceType
from api.v1.service.authentication import Principal
from api.v1.service.authorization import (
	RESOURCE_CONFIG,
	get_effective_access_level,
	level_satisfies,
	resource_access_predicate,
)
from api.v1.service.authorization.config import MAX_INHERITANCE_DEPTH
from api.v1.service.authorization.inheritance import PARENT_LINKS_BY_CHILD
from nokodo_ai.utils.typeid import TypeID


_LEVELS = (AccessLevel.READER, AccessLevel.EDITOR, AccessLevel.ADMIN)
_SEEDS = tuple(range(12))


async def _sql_admits(
	session: AsyncSession,
	principal: Principal,
	resource_type: ResourceType,
	resource_id: TypeID,
	required_level: AccessLevel,
) -> bool:
	"""whether the SQL predicate admits the principal at the required level."""
	id_col = RESOURCE_CONFIG[resource_type].id_col
	return (
		await session.scalar(
			select(id_col).where(
				id_col == resource_id,
				resource_access_predicate(
					principal,
					resource_type,
					required_level,
				),
			)
		)
	) is not None


async def _python_admits(
	session: AsyncSession,
	principal: Principal,
	resource_type: ResourceType,
	resource_id: TypeID,
	required_level: AccessLevel,
) -> bool:
	"""whether the python resolver admits the principal at the required level."""
	level = await get_effective_access_level(
		session,
		principal,
		resource_type,
		resource_id,
	)
	return level is not None and level_satisfies(level, required_level)


async def _make_user(session: AsyncSession, slug: str) -> User:
	user = User(
		email=f"{slug}-{uuid4().hex}@example.com",
		username=f"{slug}_{uuid4().hex[:12]}",
		hashed_password="x",
		is_active=True,
	)
	session.add(user)
	await session.flush()
	return user


@pytest.mark.parametrize("seed", _SEEDS)
@pytest.mark.asyncio
async def test_highest_wins_agrees_between_sql_and_python(
	db_session: AsyncSession,
	seed: int,
) -> None:
	"""random rule sets resolve identically in both engines.

	rules deliberately collide on one subject at conflicting levels, which is
	exactly where last-match-wins and highest-wins disagree.
	"""
	rng = random.Random(seed)
	owner = await _make_user(db_session, "prop-owner")
	subject = await _make_user(db_session, "prop-subject")
	group = Group(name=f"prop group {uuid4().hex[:8]}", owner_id=owner.id)
	db_session.add(group)
	await db_session.flush()
	in_group = rng.random() < 0.5
	if in_group:
		db_session.add(GroupMembership(group_id=group.id, user_id=subject.id))
		await db_session.flush()
	group_ids = (group.id,) if in_group else ()

	thread = Thread(owner_id=owner.id, title=f"prop thread {seed}")
	db_session.add(thread)
	await db_session.flush()

	# uniqueness allows one rule per subject, so conflicting levels can only
	# collide ACROSS subject kinds - which is exactly where last-match-wins and
	# highest-wins give different answers.
	kinds = [kind for kind in ("user", "group", "link", "other") if rng.random() < 0.7]
	rng.shuffle(kinds)
	for order_index, kind in enumerate(kinds):
		if kind == "user":
			subject_user_id, subject_group_id = subject.id, None
		elif kind == "group":
			subject_user_id, subject_group_id = None, group.id
		elif kind == "other":
			subject_user_id, subject_group_id = owner.id, None
		else:
			subject_user_id, subject_group_id = None, None
		level = AccessLevel.READER if kind == "link" else rng.choice(_LEVELS)
		db_session.add(
			AccessRule(
				thread_id=thread.id,
				subject_user_id=subject_user_id,
				subject_group_id=subject_group_id,
				level=level,
				order_index=order_index,
			)
		)
	await db_session.flush()

	principal = Principal.for_user(subject, group_ids=group_ids)
	for required_level in _LEVELS:
		sql_answer = await _sql_admits(
			db_session, principal, ResourceType.THREAD, thread.id, required_level
		)
		python_answer = await _python_admits(
			db_session, principal, ResourceType.THREAD, thread.id, required_level
		)
		assert sql_answer == python_answer, (
			f"seed={seed} level={required_level.value} "
			f"sql={sql_answer} python={python_answer}"
		)


@pytest.mark.parametrize("seed", _SEEDS)
@pytest.mark.asyncio
async def test_inheritance_agrees_between_sql_and_python_multi_hop(
	db_session: AsyncSession,
	seed: int,
) -> None:
	"""random multi-hop graphs resolve identically in both engines.

	the shapes a single edge cannot produce are the ones that matter. all four
	link classes are built - the project/thread many-to-many, leaf containment
	(message under thread, reminder under reminder list), the thread ->
	attached-resource edge, and the column-join thread -> agent edge - so a
	traversal policy one engine applies and the other does not surfaces as a
	mismatch. containment nests as deep as the schema allows: a reminder sits
	under a reminder list under a project attached to a thread, which is the
	longest path `RESOURCE_PARENT_LINKS` can produce (see the depth test
	below), so paths that both cross the non-transitive edge AND keep walking
	transitive parents afterwards are generated rather than assumed.
	"""
	rng = random.Random(1_000 + seed)
	owner = await _make_user(db_session, "graph-owner")
	subject = await _make_user(db_session, "graph-subject")

	projects: list[Project] = []
	for index in range(rng.randint(1, 3)):
		project = Project(owner_id=owner.id, name=f"graph {seed}-{index}")
		db_session.add(project)
		projects.append(project)
	await db_session.flush()

	threads: list[Thread] = []
	for index in range(rng.randint(1, 3)):
		thread = Thread(owner_id=owner.id, title=f"graph thread {seed}-{index}")
		# project -> thread is the m2m edge
		thread.projects = [project for project in projects if rng.random() < 0.6]
		db_session.add(thread)
		threads.append(thread)
	await db_session.flush()

	# thread -> agent is the column-join edge, read-only by construction
	agents: list[Agent] = []
	for index, thread in enumerate(threads):
		if rng.random() < 0.6:
			agent = Agent(name=f"graph agent {seed}-{index}-{uuid4().hex[:8]}")
			db_session.add(agent)
			await db_session.flush()
			db_session.add(ThreadParticipant(thread_id=thread.id, agent_id=agent.id))
			agents.append(agent)
	await db_session.flush()

	# thread -> message is leaf containment; a FILE attached to that message
	# reaches the thread through the NON-TRANSITIVE attachment edge, so it
	# inherits at most READER. the walk does NOT stop there: it keeps following
	# the thread's TRANSITIVE parents (its projects) and only refuses to cross a
	# second non-transitive edge. attaching projects to messages exercises that
	# continuation from the other side.
	attached_files: list[File] = []
	for index, thread in enumerate(threads):
		message = UserMessage(thread_id=thread.id, sender_user_id=owner.id)
		db_session.add(message)
		await db_session.flush()
		if rng.random() < 0.75:
			file = File(
				owner_id=owner.id,
				storage_backend="local",
				storage_key=f"graph-{seed}-{index}-{uuid4().hex}",
				filename=f"graph-{seed}-{index}.txt",
			)
			db_session.add(file)
			await db_session.flush()
			db_session.add(
				MessageAttachment(
					message_id=message.id,
					position=0,
					file_id=file.id,
				)
			)
			attached_files.append(file)
		for project in projects:
			if rng.random() < 0.4:
				db_session.add(
					MessageAttachment(
						message_id=message.id,
						position=1 + projects.index(project),
						project_id=project.id,
					)
				)
	await db_session.flush()

	# reminder list -> project is the m2m edge again, reminder -> list is leaf
	# containment: stacked on the project's own attachment parent this is the
	# longest chain the link table admits, so the deepest generated paths are
	# real rather than a flat graph the docstring merely claims is deep.
	reminder_lists: list[ReminderList] = []
	reminders: list[Reminder] = []
	for index in range(rng.randint(1, 2)):
		reminder_list = ReminderList(
			owner_id=owner.id, name=f"graph list {seed}-{index}"
		)
		reminder_list.projects = [project for project in projects if rng.random() < 0.7]
		db_session.add(reminder_list)
		await db_session.flush()
		reminder_lists.append(reminder_list)
		for sub_index in range(rng.randint(1, 2)):
			reminder = Reminder(
				owner_id=owner.id,
				list_id=reminder_list.id,
				title=f"graph reminder {seed}-{index}-{sub_index}",
			)
			db_session.add(reminder)
			reminders.append(reminder)
	await db_session.flush()

	for project in projects:
		if rng.random() < 0.6:
			db_session.add(
				AccessRule(
					project_id=project.id,
					subject_user_id=subject.id,
					level=rng.choice(_LEVELS),
					order_index=0,
				)
			)
	for thread in threads:
		if rng.random() < 0.4:
			db_session.add(
				AccessRule(
					thread_id=thread.id,
					subject_user_id=subject.id,
					level=rng.choice(_LEVELS),
					order_index=0,
				)
			)
	for file in attached_files:
		if rng.random() < 0.3:
			db_session.add(
				AccessRule(
					file_id=file.id,
					subject_user_id=subject.id,
					level=rng.choice(_LEVELS),
					order_index=0,
				)
			)
	for reminder_list in reminder_lists:
		if rng.random() < 0.3:
			db_session.add(
				AccessRule(
					reminder_list_id=reminder_list.id,
					subject_user_id=subject.id,
					level=rng.choice(_LEVELS),
					order_index=0,
				)
			)
	await db_session.flush()

	principal = Principal.for_user(subject)
	targets: list[tuple[ResourceType, TypeID]] = [
		*((ResourceType.THREAD, thread.id) for thread in threads),
		*((ResourceType.FILE, file.id) for file in attached_files),
		*((ResourceType.AGENT, agent.id) for agent in agents),
		*(
			(ResourceType.REMINDER_LIST, reminder_list.id)
			for reminder_list in reminder_lists
		),
		*((ResourceType.REMINDER, reminder.id) for reminder in reminders),
	]
	for resource_type, resource_id in targets:
		for required_level in _LEVELS:
			sql_answer = await _sql_admits(
				db_session, principal, resource_type, resource_id, required_level
			)
			python_answer = await _python_admits(
				db_session, principal, resource_type, resource_id, required_level
			)
			assert sql_answer == python_answer, (
				f"seed={seed} {resource_type.value} level={required_level.value} "
				f"sql={sql_answer} python={python_answer}"
			)


def _longest_schema_path(
	resource_type: ResourceType,
	non_transitive_used: bool,
	on_path: frozenset[ResourceType],
) -> int:
	"""longest parent chain the link table admits from one resource type.

	walks `RESOURCE_PARENT_LINKS` the way both engines do - refusing a second
	non-transitive hop - so the bound this returns is what the schema can
	actually build, not what `MAX_INHERITANCE_DEPTH` permits.
	"""
	best = 0
	for link in PARENT_LINKS_BY_CHILD[resource_type]:
		if not link.transitive and non_transitive_used:
			continue
		if link.parent_type in on_path:
			continue
		best = max(
			best,
			1
			+ _longest_schema_path(
				link.parent_type,
				non_transitive_used or not link.transitive,
				on_path | {resource_type},
			),
		)
	return best


def test_the_depth_bound_is_slack_not_a_live_limit() -> None:
	"""no schema path can reach `MAX_INHERITANCE_DEPTH`, so nothing truncates.

	this is the honest version of a claim the multi-hop test used to make in
	its docstring: project links do NOT chain, so the deepest path any data can
	build is a few hops. the bound is a guard against a cyclic or future graph,
	not a limit reached in practice - and the test below covers that deepest
	real path instead of a fictional one. if a new link class ever makes the
	schema deep enough to truncate, this assertion fails and the truncation
	agreement needs its own test.
	"""
	deepest = max(
		_longest_schema_path(resource_type, False, frozenset())
		for resource_type in ResourceType
	)
	assert deepest >= 3, "the schema lost its multi-hop paths"
	assert deepest < MAX_INHERITANCE_DEPTH, (
		f"a schema path now reaches {deepest} hops against a bound of "
		f"{MAX_INHERITANCE_DEPTH}: truncation is reachable and needs a test"
	)


@pytest.mark.asyncio
async def test_engines_agree_on_the_deepest_schema_path(
	db_session: AsyncSession,
) -> None:
	"""the longest chain real data can build resolves identically in both.

	reminder -> reminder list -> project -> (attachment) thread is the deepest
	path `RESOURCE_PARENT_LINKS` admits. a grant is placed at every level so
	each hop is exercised on its own: the two engines must agree about which
	ones reach, including the READER cap the non-transitive attachment edge
	imposes and the transitive hops that continue past it.
	"""
	owner = await _make_user(db_session, "depth-owner")
	subject = await _make_user(db_session, "depth-subject")

	thread = Thread(owner_id=owner.id, title="depth thread")
	db_session.add(thread)
	await db_session.flush()
	message = UserMessage(thread_id=thread.id, sender_user_id=owner.id)
	db_session.add(message)
	await db_session.flush()
	project = Project(owner_id=owner.id, name=f"depth {uuid4().hex[:8]}")
	db_session.add(project)
	await db_session.flush()
	# project attached to the thread's message: the non-transitive hop, capped
	# at READER, and the only way a project earns a parent at all
	db_session.add(
		MessageAttachment(message_id=message.id, position=0, project_id=project.id)
	)
	reminder_list = ReminderList(owner_id=owner.id, name="depth list")
	reminder_list.projects = [project]
	db_session.add(reminder_list)
	await db_session.flush()
	reminder = Reminder(
		owner_id=owner.id, list_id=reminder_list.id, title="depth reminder"
	)
	db_session.add(reminder)
	# a file attached to the same message, so the leaf/attachment shape is
	# covered next to the containment chain
	file = File(
		owner_id=owner.id,
		storage_backend="local",
		storage_key=f"depth-{uuid4().hex}",
		filename="depth.txt",
	)
	db_session.add(file)
	await db_session.flush()
	db_session.add(
		MessageAttachment(message_id=message.id, position=1, file_id=file.id)
	)
	await db_session.flush()

	principal = Principal.for_user(subject)
	targets = (
		(ResourceType.THREAD, thread.id),
		(ResourceType.MESSAGE, message.id),
		(ResourceType.PROJECT, project.id),
		(ResourceType.REMINDER_LIST, reminder_list.id),
		(ResourceType.REMINDER, reminder.id),
		(ResourceType.FILE, file.id),
	)
	# one grant at a time: a single fixture with every rule at once would let a
	# short path mask a long one that never resolves.
	grants: tuple[tuple[str, TypeID], ...] = (
		("thread_id", thread.id),
		("project_id", project.id),
		("reminder_list_id", reminder_list.id),
	)
	for column, granted_id in grants:
		rule = AccessRule(
			subject_user_id=subject.id,
			level=AccessLevel.ADMIN,
			order_index=0,
			**{column: granted_id},
		)
		db_session.add(rule)
		await db_session.flush()
		for resource_type, resource_id in targets:
			for required_level in _LEVELS:
				sql_answer = await _sql_admits(
					db_session, principal, resource_type, resource_id, required_level
				)
				python_answer = await _python_admits(
					db_session, principal, resource_type, resource_id, required_level
				)
				assert sql_answer == python_answer, (
					f"grant={column} {resource_type.value} "
					f"level={required_level.value} "
					f"sql={sql_answer} python={python_answer}"
				)
		await db_session.delete(rule)
		await db_session.flush()
