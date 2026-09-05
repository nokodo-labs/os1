"""read-only traversal and visibility for native message trees."""

from dataclasses import dataclass

from fastapi import HTTPException, status
from sqlalchemy import exists, literal, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.database.recursive_cte import cycle_safe_cte
from api.models.access_rule import AccessLevel
from api.models.message import Message
from api.models.thread import Thread
from api.permissions import ResourceType
from api.schemas.common import MISSING, unwrap_missing
from api.v1.service.authentication import Principal
from api.v1.service.authorization import resource_access_predicate
from api.v1.service.threads.common import (
	is_multi_writer_thread,
	load_thread,
	message_load_options,
	multi_writer_thread_ids,
)
from nokodo_ai.types.sentinels import MissingType
from nokodo_ai.utils.typeid import TypeID


@dataclass(frozen=True, slots=True)
class MessageBranch:
	"""off-canon branch containing a message."""

	root_id: TypeID
	leaf_id: TypeID


def branch_depths_cte(leaf_id: TypeID, root_id: TypeID | None = None):
	"""recursive CTE of the leaf-to-root path with depth 0 at the leaf."""
	msg_t = Message.__table__
	anchor = (
		select(
			msg_t.c.id.label("msg_id"),
			msg_t.c.parent_id.label("msg_parent_id"),
			msg_t.c.branch_current_message_id.label("msg_branch_current_message_id"),
			literal(0).label("depth"),
		)
		.where(msg_t.c.id == leaf_id)
		.cte(name="branch", recursive=True)
	)
	recursive = select(
		msg_t.c.id.label("msg_id"),
		msg_t.c.parent_id.label("msg_parent_id"),
		msg_t.c.branch_current_message_id.label("msg_branch_current_message_id"),
		(anchor.c.depth + 1).label("depth"),
	).where(msg_t.c.id == anchor.c.msg_parent_id)
	if root_id is not None:
		recursive = recursive.where(anchor.c.msg_id != root_id)
	return cycle_safe_cte(
		anchor.union_all(recursive),
		["msg_id"],
		"branch_safe",
	)


def selected_message_ids_cte(thread_ids: list[str | TypeID]):
	"""selected canon and off-canon message paths for shared threads."""
	thread_t = Thread.__table__
	msg_t = Message.__table__
	anchors = (
		select(
			thread_t.c.id.label("t_id"),
			thread_t.c.current_message_id.label("m_id"),
		)
		.where(
			thread_t.c.id.in_(thread_ids),
			thread_t.c.current_message_id.is_not(None),
		)
		.union(
			select(
				msg_t.c.thread_id.label("t_id"),
				msg_t.c.branch_current_message_id.label("m_id"),
			).where(
				msg_t.c.thread_id.in_(thread_ids),
				msg_t.c.branch_current_message_id.is_not(None),
			)
		)
	)
	anchors_subquery = anchors.subquery()
	selected = select(
		anchors_subquery.c.t_id,
		anchors_subquery.c.m_id,
	).cte(name="selected_messages", recursive=True)
	ascend = select(
		selected.c.t_id,
		msg_t.c.parent_id.label("m_id"),
	).where(
		msg_t.c.id == selected.c.m_id,
		msg_t.c.parent_id.is_not(None),
	)
	return cycle_safe_cte(
		selected.union_all(ascend),
		["t_id", "m_id"],
		"selected_messages_safe",
	)


async def active_branch_message_ids(
	session: AsyncSession,
	thread_ids: list[str | TypeID],
) -> dict[str, set[str]]:
	"""map each thread to the message ids on its canon branch."""
	ids = list(thread_ids)
	if not ids:
		return {}
	thread_t = Thread.__table__
	msg_t = Message.__table__
	anchor = (
		select(
			thread_t.c.id.label("t_id"),
			thread_t.c.current_message_id.label("m_id"),
		)
		.where(
			thread_t.c.id.in_(ids),
			thread_t.c.current_message_id.is_not(None),
		)
		.cte(name="active_branches", recursive=True)
	)
	recursive = select(anchor.c.t_id, msg_t.c.parent_id.label("m_id")).where(
		msg_t.c.id == anchor.c.m_id,
		msg_t.c.parent_id.is_not(None),
	)
	branch_cte = cycle_safe_cte(
		anchor.union_all(recursive),
		["t_id", "m_id"],
		"active_branches_safe",
	)
	rows = await session.execute(select(branch_cte.c.t_id, branch_cte.c.m_id))
	branches: dict[str, set[str]] = {}
	for thread_id, message_id in rows:
		branches.setdefault(str(thread_id), set()).add(str(message_id))
	return branches


async def canon_message_ids(session: AsyncSession, thread_id: TypeID) -> set[str]:
	"""every message id on a thread's canon path."""
	branches = await active_branch_message_ids(session, [thread_id])
	return branches.get(str(thread_id), set())


async def walk_to_root(
	session: AsyncSession,
	leaf_id: TypeID,
) -> list[tuple[TypeID, TypeID | None, TypeID | None]]:
	"""message, parent, and branch pointer from a leaf up to the root."""
	branch = branch_depths_cte(leaf_id)
	rows = (
		await session.execute(
			select(
				branch.c.msg_id,
				branch.c.msg_parent_id,
				branch.c.msg_branch_current_message_id,
			).order_by(branch.c.depth)
		)
	).all()
	return [
		(message_id, parent_id, branch_current_id)
		for message_id, parent_id, branch_current_id in rows
	]


def container_from_walk(
	walk: list[tuple[TypeID, TypeID | None, TypeID | None]],
	canon_ids: set[str],
) -> tuple[TypeID | None, TypeID | None]:
	"""root and current message of the innermost off-canon branch."""
	for message_id, _parent_id, branch_current_id in walk:
		if str(message_id) in canon_ids:
			break
		if branch_current_id is not None:
			return message_id, branch_current_id
	return None, None


async def resolve_message_branch(
	session: AsyncSession,
	message_id: TypeID,
	canon_ids: set[str],
) -> MessageBranch | None:
	"""the innermost selected off-canon branch containing a message."""
	if str(message_id) in canon_ids:
		return None
	message = await session.get(Message, message_id)
	if message is None:
		return None
	if await is_multi_writer_thread(session, message.thread_id):
		selected = selected_message_ids_cte([message.thread_id])
		membership = exists(
			select(selected.c.m_id).where(selected.c.m_id == message_id)
		)
		if not await session.scalar(select(membership)):
			return None
	root_id, leaf_id = container_from_walk(
		await walk_to_root(session, message_id), canon_ids
	)
	if root_id is None or leaf_id is None:
		return None
	return MessageBranch(root_id=root_id, leaf_id=leaf_id)


async def resolve_message_branch_from_head(
	session: AsyncSession,
	message_id: TypeID,
	head_id: TypeID | None,
) -> MessageBranch | None:
	"""resolve a message against one canon head without materializing canon."""
	if head_id is None:
		return None
	walk = await walk_to_root(session, message_id)
	if not walk:
		return None
	canon = branch_depths_cte(head_id)
	walk_ids = [row[0] for row in walk]
	canon_ids = {
		str(message_id)
		for message_id in await session.scalars(
			select(canon.c.msg_id).where(canon.c.msg_id.in_(walk_ids))
		)
	}
	if str(message_id) in canon_ids:
		return None
	root_id, leaf_id = container_from_walk(walk, canon_ids)
	if root_id is None or leaf_id is None:
		return None
	return MessageBranch(root_id=root_id, leaf_id=leaf_id)


async def branch_root_id(
	session: AsyncSession,
	thread_id: TypeID,
	message_id: TypeID,
) -> TypeID | None:
	"""root of the innermost off-canon branch containing a message."""
	canon_ids = await canon_message_ids(session, thread_id)
	if str(message_id) in canon_ids:
		return None
	root_id, _leaf_id = container_from_walk(
		await walk_to_root(session, message_id), canon_ids
	)
	return root_id


async def messages_between(
	session: AsyncSession,
	thread_id: TypeID,
	after_message_id: TypeID | None,
	through_message_id: TypeID,
) -> list[Message]:
	"""the chain segment `(after, through]`, root-first."""
	branch = branch_depths_cte(through_message_id, root_id=after_message_id)
	stmt = (
		select(Message)
		.join(branch, Message.id == branch.c.msg_id)
		.where(Message.thread_id == thread_id)
		.options(*message_load_options())
		.order_by(branch.c.depth.desc())
	)
	rows = list((await session.execute(stmt)).scalars().all())
	if after_message_id is None:
		return rows
	if not rows or rows[0].id != after_message_id:
		raise ValueError("messages are not on the same conversation chain")
	return rows[1:]


async def load_message_branch(
	session: AsyncSession,
	thread_id: TypeID,
	leaf_id: TypeID,
) -> list[Message]:
	"""agent context for a run inside an off-canon branch, root-first."""
	canon_ids = await canon_message_ids(session, thread_id)
	if str(leaf_id) in canon_ids:
		return []
	own_ids: list[TypeID] = []
	anchor_id: TypeID | None = None
	for message_id, parent_id, branch_current_id in await walk_to_root(
		session, leaf_id
	):
		if str(message_id) in canon_ids:
			break
		own_ids.append(message_id)
		anchor_id = parent_id
		if branch_current_id is not None:
			break
	if not own_ids:
		return []
	branch = branch_depths_cte(leaf_id)
	stmt = (
		select(Message)
		.join(branch, Message.id == branch.c.msg_id)
		.where(
			Message.thread_id == thread_id,
			Message.id.in_([*own_ids, anchor_id] if anchor_id else own_ids),
		)
		.options(selectinload(Message.attachment_links))
		.order_by(branch.c.depth.desc())
	)
	return list((await session.execute(stmt)).scalars().all())


async def walk_message_branch(
	session: AsyncSession,
	thread_id: TypeID,
	leaf_id: TypeID,
) -> list[Message]:
	"""walk from root to the given leaf without access checks."""
	branch = branch_depths_cte(leaf_id)
	stmt = (
		select(Message)
		.join(branch, Message.id == branch.c.msg_id)
		.where(Message.thread_id == thread_id)
		.options(selectinload(Message.attachment_links))
		.order_by(branch.c.depth.desc())
	)
	return list((await session.execute(stmt)).scalars().all())


async def get_current_branch(
	thread_id: TypeID,
	session: AsyncSession,
	principal: Principal,
) -> list[Message]:
	"""return the root-leaf path ending at the thread's current message."""
	thread = await load_thread(
		thread_id,
		session,
		principal,
		required_level=AccessLevel.READER,
	)
	if thread.current_message_id is None:
		return []
	return await walk_message_branch(session, thread_id, thread.current_message_id)


async def load_thread_with_branch(
	thread_id: TypeID,
	session: AsyncSession,
	principal: Principal,
	parent_id: TypeID | None | MissingType = MISSING,
) -> tuple[Thread, list[Message]]:
	"""load a thread and its selected message branch for agent execution."""
	stmt = select(Thread).where(
		Thread.id == thread_id,
		resource_access_predicate(
			principal,
			ResourceType.THREAD,
			required_level=AccessLevel.READER,
			include_link_access=True,
		),
	)
	thread = (await session.execute(stmt)).scalars().one_or_none()
	if thread is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="thread not found",
		)
	explicit_parent = parent_id is not MISSING
	requested_parent_id = unwrap_missing(parent_id)
	head_id = requested_parent_id if explicit_parent else thread.current_message_id
	if head_id is None:
		return thread, []
	if (
		explicit_parent
		and requested_parent_id is not None
		and requested_parent_id != thread.current_message_id
	):
		message_branch = await load_message_branch(
			session,
			thread_id,
			requested_parent_id,
		)
		if message_branch:
			return thread, message_branch
	return thread, await walk_message_branch(session, thread_id, head_id)


async def require_run_context_message(
	session: AsyncSession,
	thread_id: TypeID,
	message_id: TypeID,
) -> None:
	"""require a message that can anchor a run context in one thread."""
	message_thread_id = await session.scalar(
		select(Message.thread_id).where(Message.id == message_id)
	)
	if message_thread_id != thread_id:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="message not found in this thread",
		)


async def deepest_leaf_from(
	session: AsyncSession,
	thread_id: TypeID,
	start_id: TypeID | None,
	exclude: set[str] | None = None,
) -> TypeID | None:
	"""follow newest children to the deepest remaining leaf."""
	excluded = list(exclude) if exclude else []

	def children_of(parent_id: TypeID | None):
		stmt = select(Message.id).where(Message.thread_id == thread_id)
		stmt = stmt.where(
			Message.parent_id.is_(None)
			if parent_id is None
			else Message.parent_id == parent_id
		)
		if excluded:
			stmt = stmt.where(Message.id.notin_(excluded))
		return stmt.order_by(Message.created_at, Message.id)

	leaf_id = start_id
	if leaf_id is None:
		roots = (await session.scalars(children_of(None))).all()
		if not roots:
			return None
		leaf_id = roots[-1]
	while True:
		children = (await session.scalars(children_of(leaf_id))).all()
		if not children:
			return leaf_id
		leaf_id = children[-1]


async def visible_message_ids(
	session: AsyncSession,
	thread_ids: list[str | TypeID],
) -> dict[str, set[str]]:
	"""map each thread to the message ids visible in its conversation model."""
	ids = list(thread_ids)
	if not ids:
		return {}
	shared = await multi_writer_thread_ids(session, ids)
	visible: dict[str, set[str]] = {}
	solo_ids = [thread_id for thread_id in ids if str(thread_id) not in shared]
	if solo_ids:
		rows = await session.execute(
			select(Message.thread_id, Message.id).where(Message.thread_id.in_(solo_ids))
		)
		for thread_id, message_id in rows:
			visible.setdefault(str(thread_id), set()).add(str(message_id))
	if not shared:
		return visible
	shared_ids = list(shared)
	selected = selected_message_ids_cte(shared_ids)
	for thread_id, message_id in await session.execute(
		select(selected.c.t_id, selected.c.m_id)
	):
		visible.setdefault(str(thread_id), set()).add(str(message_id))
	return visible


async def message_is_visible(
	session: AsyncSession,
	thread_id: TypeID,
	message_id: TypeID,
) -> bool:
	"""whether one message belongs to the thread's visible conversation."""
	message = await session.get(Message, message_id)
	if message is None or message.thread_id != thread_id:
		return False
	if not await is_multi_writer_thread(session, thread_id):
		return True
	selected = selected_message_ids_cte([thread_id])
	membership = exists(select(selected.c.m_id).where(selected.c.m_id == message_id))
	return bool(await session.scalar(select(membership)))
