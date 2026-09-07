"""validation and mutation for message-tree splices."""

from dataclasses import dataclass

from fastapi import HTTPException, status
from sqlalchemy import delete, exists, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import set_committed_value

from api.models.access_rule import AccessLevel
from api.models.message import Message, MessageType
from api.models.message_attachment import MessageAttachment
from api.models.thread import Thread
from api.permissions import ActionPermission, ResourceType
from api.schemas.message import (
	BranchLeaf,
	MessageRange,
	MessageSplice,
	ReplacementTarget,
	RunBlockRef,
	ThreadLeaf,
)
from api.v1.service.authentication import Principal
from api.v1.service.authorization import require_permission, require_resource_access
from api.v1.service.threads.common import is_multi_writer_thread
from api.v1.service.threads.summaries import delete_stale_summaries_for_thread
from api.v1.service.threads.tree import (
	branch_depths_cte,
	canon_message_ids,
	deepest_leaf_from,
	message_is_visible,
	messages_between,
	resolve_message_branch,
	resolve_message_branch_from_head,
	selected_message_ids_cte,
	walk_to_root,
)
from nokodo_ai.types.sentinels import MissingType
from nokodo_ai.utils.typeid import TypeID


async def _run_block_messages(
	session: AsyncSession,
	thread_id: TypeID,
	target: RunBlockRef,
) -> list[Message]:
	"""derive one contiguous generated run block from its visible head."""
	thread = await session.get(Thread, thread_id)
	root = await session.get(Message, target.run_head_message_id)
	if thread is None or root is None or root.thread_id != thread_id:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="run block not found in this thread",
		)
	run_id = root.public_metadata.get("run_id")
	if (
		not isinstance(run_id, str)
		or run_id != str(target.run_id)
		or root.type == MessageType.USER
	):
		raise HTTPException(
			status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
			detail="run_head_message_id does not name output from this run",
		)

	canon_ids = await canon_message_ids(session, thread_id)
	if str(root.id) in canon_ids:
		container_leaf_id = thread.current_message_id
	else:
		branch = await resolve_message_branch(
			session, target.run_head_message_id, canon_ids
		)
		if branch is None:
			raise HTTPException(
				status_code=status.HTTP_404_NOT_FOUND,
				detail="run block not found in this thread",
			)
		container_leaf_id = branch.leaf_id
	if container_leaf_id is None:
		raise HTTPException(
			status_code=status.HTTP_409_CONFLICT,
			detail="run block has no active conversation container",
		)
	selected_ids = {
		str(message_id)
		for message_id, _parent_id, _branch_current_id in await walk_to_root(
			session, container_leaf_id
		)
	}
	if str(root.id) not in selected_ids:
		raise HTTPException(
			status_code=status.HTTP_409_CONFLICT,
			detail="run block is no longer on the active container path",
		)
	parent = await session.get(Message, root.parent_id) if root.parent_id else None
	if (
		parent is not None
		and parent.public_metadata.get("run_id") == run_id
		and parent.type != MessageType.USER
	):
		raise HTTPException(
			status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
			detail="run_head_message_id is not the first message of its run block",
		)

	block = [root]
	current = root
	while True:
		children = list(
			(
				await session.scalars(
					select(Message)
					.where(Message.parent_id == current.id)
					.order_by(Message.created_at, Message.id)
				)
			).all()
		)
		selected = [child for child in children if str(child.id) in selected_ids]
		if len(selected) > 1:
			raise HTTPException(
				status_code=status.HTTP_409_CONFLICT,
				detail="run block has an external child or nested branch",
			)
		if not selected:
			break
		next_message = selected[0]
		if (
			next_message.public_metadata.get("run_id") == run_id
			and next_message.type != MessageType.USER
		):
			block.append(next_message)
			current = next_message
			continue
		break

	return block


async def _message_range_messages(
	session: AsyncSession,
	thread_id: TypeID,
	target: MessageRange,
) -> list[Message]:
	"""load one contiguous parent-linked message range."""
	head = await session.get(Message, target.head_id)
	tail = await session.get(Message, target.tail_id)
	if (
		head is None
		or tail is None
		or head.thread_id != thread_id
		or tail.thread_id != thread_id
	):
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="message range not found in this thread",
		)
	try:
		messages = await messages_between(
			session,
			thread_id,
			head.parent_id,
			target.tail_id,
		)
	except ValueError as exc:
		raise HTTPException(
			status_code=status.HTTP_409_CONFLICT,
			detail=str(exc),
		) from exc
	if not messages or messages[0].id != target.head_id:
		raise HTTPException(
			status_code=status.HTTP_409_CONFLICT,
			detail="message range is not contiguous",
		)
	return messages


async def replacement_messages(
	session: AsyncSession,
	thread_id: TypeID,
	target: ReplacementTarget,
	reparent_message_ids: list[TypeID] | None = None,
) -> list[Message]:
	"""resolve the messages selected by one replacement target."""
	if isinstance(target, RunBlockRef):
		replaced = await _run_block_messages(session, thread_id, target)
	else:
		replaced = await _message_range_messages(session, thread_id, target)
	await _validate_replacement_isolation(
		session,
		replaced,
		reparent_message_ids,
	)
	return replaced


async def _validate_replacement_isolation(
	session: AsyncSession,
	replaced: list[Message],
	reparent_message_ids: list[TypeID] | None,
) -> None:
	"""reject side conversations that a range deletion would mutate."""
	replaced_ids = {message.id for message in replaced}
	tail_id = replaced[-1].id
	external_children = list(
		await session.execute(
			select(Message.id, Message.parent_id).where(
				Message.parent_id.in_(replaced_ids),
				Message.id.notin_(replaced_ids),
			)
		)
	)
	allowed_children = set(reparent_message_ids or [])
	if any(
		child_id not in allowed_children or parent_id != tail_id
		for child_id, parent_id in external_children
	):
		raise HTTPException(
			status_code=status.HTTP_409_CONFLICT,
			detail="replacement range has an external child or nested branch",
		)
	external_reply = await session.scalar(
		select(Message.id).where(
			Message.reply_to_message_id.in_(replaced_ids),
			Message.id.notin_(replaced_ids),
		)
	)
	if external_reply is not None:
		raise HTTPException(
			status_code=status.HTTP_409_CONFLICT,
			detail="replacement range has an external reply",
		)


async def _validate_existing_references(
	session: AsyncSession,
	thread: Thread,
	splice: MessageSplice,
	message_id: TypeID,
) -> None:
	"""validate splice references that do not require replacement resolution."""
	thread_id = thread.id
	if splice.parent_id is not None:
		parent = await session.get(Message, splice.parent_id)
		if parent is None or parent.thread_id != thread_id:
			raise HTTPException(
				status_code=status.HTTP_404_NOT_FOUND,
				detail="parent message not found in this thread",
			)
	for reparent_message_id in splice.reparent_message_ids:
		reparented = await session.get(Message, reparent_message_id)
		if reparented is None or reparented.thread_id != thread_id:
			raise HTTPException(
				status_code=status.HTTP_404_NOT_FOUND,
				detail="reparent message not found in this thread",
			)
	if isinstance(splice.leaf, BranchLeaf) and splice.leaf.root_id != message_id:
		root = await session.get(Message, splice.leaf.root_id)
		if root is None or root.thread_id != thread_id:
			raise HTTPException(
				status_code=status.HTTP_404_NOT_FOUND,
				detail="branch root not found in this thread",
			)


@dataclass(frozen=True, slots=True)
class PreparedPlacement:
	"""where one message will land, derived once under the thread write lock.

	a message has one placement, so whoever needs to know it before the write
	(to claim the agent slot for the right conversation) resolves it here and
	hands the same answer to the write.
	"""

	splice: MessageSplice
	multi_writer: bool

	@property
	def container_root_id(self) -> TypeID | None:
		"""the conversation container this placement selects."""
		if isinstance(self.splice.leaf, BranchLeaf):
			return self.splice.leaf.root_id
		return None


async def prepare_message_placement(
	session: AsyncSession,
	thread: Thread,
	requested: MessageSplice | MissingType,
	message_id: TypeID,
	principal: Principal,
	advances_head: bool = True,
) -> PreparedPlacement:
	"""resolve the writer model and the splice one message will be written with.

	call this with the thread write lock held: the head is refreshed here, so a
	caller that loaded the thread before the lock still places against the head
	that survived the wait.
	"""
	await session.refresh(thread, attribute_names=["current_message_id"])
	multi_writer = await is_multi_writer_thread(session, thread.id)
	return PreparedPlacement(
		splice=await prepare_message_splice(
			session,
			thread,
			requested,
			message_id,
			multi_writer=multi_writer,
			principal=principal,
			advances_head=advances_head,
		),
		multi_writer=multi_writer,
	)


async def prepare_message_splice(
	session: AsyncSession,
	thread: Thread,
	requested: MessageSplice | MissingType,
	message_id: TypeID,
	multi_writer: bool,
	principal: Principal,
	advances_head: bool = True,
) -> MessageSplice:
	"""validate a requested splice and derive ordinary branch selection."""
	if not isinstance(requested, MessageSplice):
		return await resolve_message_splice(
			session,
			thread,
			None,
			message_id,
			explicit_parent=False,
			multi_writer=multi_writer,
			advances_head=advances_head,
		)
	await _validate_existing_references(session, thread, requested, message_id)
	if requested.leaf is not None:
		if multi_writer:
			require_permission(principal, ActionPermission.THREADS_MANAGE)
		else:
			await require_resource_access(
				thread.id,
				session,
				principal,
				ResourceType.THREAD,
				required_level=AccessLevel.ADMIN,
			)
		if requested.replaces is None:
			expected = await resolve_message_splice(
				session,
				thread,
				requested.parent_id,
				message_id,
				explicit_parent=True,
				multi_writer=multi_writer,
				advances_head=advances_head,
			)
			expected_leaf = expected.leaf
			if requested.leaf != expected_leaf:
				raise HTTPException(
					status_code=status.HTTP_409_CONFLICT,
					detail="leaf does not match the derived splice",
				)
	if requested.reparent_message_ids:
		reparented = list(
			await session.scalars(
				select(Message).where(Message.id.in_(requested.reparent_message_ids))
			)
		)
		if len(reparented) != len(requested.reparent_message_ids):
			raise HTTPException(
				status_code=status.HTTP_404_NOT_FOUND,
				detail="reparent message not found in this thread",
			)
		if requested.replaces is None and any(
			message.parent_id != requested.parent_id for message in reparented
		):
			raise HTTPException(
				status_code=status.HTTP_409_CONFLICT,
				detail="reparent message is not the splice successor",
			)
		if requested.parent_id is not None:
			ancestry = branch_depths_cte(requested.parent_id)
			ancestor = await session.scalar(
				select(ancestry.c.msg_id).where(
					ancestry.c.msg_id.in_(requested.reparent_message_ids)
				)
			)
			if ancestor is not None:
				raise HTTPException(
					status_code=status.HTTP_409_CONFLICT,
					detail=(
						"reparent message cannot be an ancestor of the splice parent"
					),
				)
	if requested.replaces is not None or requested.leaf is not None:
		return requested
	if requested.reparent_message_ids:
		return requested
	ordinary = await resolve_message_splice(
		session,
		thread,
		requested.parent_id,
		message_id,
		explicit_parent=True,
		multi_writer=multi_writer,
		advances_head=advances_head,
	)
	return requested.model_copy(update={"leaf": ordinary.leaf})


async def _resolve_replacement_splice(
	session: AsyncSession,
	thread: Thread,
	splice: MessageSplice,
	message_id: TypeID,
) -> tuple[MessageSplice, list[Message]]:
	"""validate replacement topology and derive pointer selection."""
	if splice.replaces is None:
		return splice, []
	requested_leaf = splice.leaf
	applied = splice.model_copy(update={"leaf": None})
	replaced = await replacement_messages(
		session,
		thread.id,
		splice.replaces,
		splice.reparent_message_ids,
	)
	head = replaced[0]
	tail = replaced[-1]
	if head.parent_id != splice.parent_id:
		raise HTTPException(
			status_code=status.HTTP_409_CONFLICT,
			detail="splice parent does not precede the replacement range",
		)
	children = list(
		(
			await session.scalars(
				select(Message)
				.where(Message.parent_id == tail.id)
				.order_by(Message.created_at, Message.id)
			)
		).all()
	)
	replaced_ids = {message.id for message in replaced}
	successors = [message for message in children if message.id not in replaced_ids]
	if len(successors) > 1:
		raise HTTPException(
			status_code=status.HTTP_409_CONFLICT,
			detail="replacement range has multiple successors",
		)
	expected_successor_ids = [message.id for message in successors]
	if expected_successor_ids != splice.reparent_message_ids:
		raise HTTPException(
			status_code=status.HTTP_409_CONFLICT,
			detail="splice reparent message does not follow the replacement range",
		)

	canon_ids = await canon_message_ids(session, thread.id)
	if str(head.id) in canon_ids:
		if thread.current_message_id in replaced_ids:
			applied = applied.model_copy(update={"leaf": ThreadLeaf(kind="thread")})
	else:
		branch = await resolve_message_branch(session, head.id, canon_ids)
		if branch is not None and branch.leaf_id in replaced_ids:
			applied = applied.model_copy(
				update={
					"leaf": BranchLeaf(kind="branch", root_id=branch.root_id),
				}
			)
	if isinstance(applied.leaf, BranchLeaf) and applied.leaf.root_id in replaced_ids:
		applied = applied.model_copy(
			update={"leaf": BranchLeaf(kind="branch", root_id=message_id)}
		)
	if requested_leaf is not None and requested_leaf != applied.leaf:
		raise HTTPException(
			status_code=status.HTTP_409_CONFLICT,
			detail="leaf does not match the derived splice",
		)
	return applied, replaced


def _pointer_values(current_id: TypeID | None) -> dict[str, object]:
	"""a branch pointer write that leaves `updated_at` unchanged."""
	return {
		"branch_current_message_id": current_id,
		"updated_at": Message.updated_at,
	}


async def clear_pointers_on_canon(
	session: AsyncSession,
	head_id: TypeID | None,
) -> None:
	"""drop branch pointers from messages now on the canon path."""
	if head_id is None:
		return
	on_canon = select(branch_depths_cte(head_id).c.msg_id)
	await session.execute(
		update(Message)
		.where(Message.id.in_(on_canon), Message.branch_current_message_id.is_not(None))
		.values(**_pointer_values(None))
	)


async def _apply_leaf(
	session: AsyncSession,
	thread: Thread,
	splice: MessageSplice,
	message: Message,
) -> None:
	"""select the spliced message for its thread or off-canon branch."""
	if isinstance(splice.leaf, BranchLeaf):
		await session.execute(
			update(Message)
			.where(Message.id == splice.leaf.root_id)
			.values(**_pointer_values(message.id))
		)
		if splice.leaf.root_id == message.id:
			set_committed_value(message, "branch_current_message_id", message.id)
	elif isinstance(splice.leaf, ThreadLeaf):
		thread.current_message_id = message.id
		await clear_pointers_on_canon(session, message.id)


async def _transfer_replaced_branch_pointer(
	session: AsyncSession,
	replaced: list[Message],
	replacement: Message,
) -> None:
	"""transfer branch-root selection through a replacement."""
	replaced_ids = {message.id for message in replaced}
	for message in replaced:
		current_id = message.branch_current_message_id
		if current_id is None:
			continue
		leaf_id = replacement.id if current_id in replaced_ids else current_id
		await session.execute(
			update(Message)
			.where(Message.id == replacement.id)
			.values(**_pointer_values(leaf_id))
		)
		set_committed_value(replacement, "branch_current_message_id", leaf_id)
		return


async def apply_message_splice(
	session: AsyncSession,
	thread: Thread,
	splice: MessageSplice,
	message: Message,
	principal: Principal,
	multi_writer: bool,
) -> tuple[MessageSplice, list[MessageAttachment]]:
	"""validate and atomically apply one message's structural tree mutation."""
	applied, replaced = await _resolve_replacement_splice(
		session, thread, splice, message.id
	)
	for replaced_message in replaced:
		await require_resource_access(
			replaced_message.id,
			session,
			principal,
			ResourceType.MESSAGE,
			required_level=AccessLevel.EDITOR,
		)
	replaced_ids = [old.id for old in replaced]
	old_attachment_links = list(
		(
			await session.scalars(
				select(MessageAttachment).where(
					MessageAttachment.message_id.in_(replaced_ids)
				)
			)
		).all()
	)
	if replaced and message.reply_to_message_id is None:
		message.reply_to_message_id = replaced[0].reply_to_message_id
	if applied.reparent_message_ids:
		await session.execute(
			update(Message)
			.where(Message.id.in_(applied.reparent_message_ids))
			.values(parent_id=message.id, updated_at=Message.updated_at)
		)
	if replaced:
		await _transfer_replaced_branch_pointer(session, replaced, message)
	await _apply_leaf(session, thread, applied, message)
	if applied.reparent_message_ids and multi_writer:
		await session.flush()
		for reparented_id in applied.reparent_message_ids:
			if await message_is_visible(session, thread.id, reparented_id):
				continue
			leaf_id = await deepest_leaf_from(session, thread.id, reparented_id)
			await session.execute(
				update(Message)
				.where(Message.id == reparented_id)
				.values(**_pointer_values(leaf_id))
			)
	if replaced_ids:
		await session.execute(delete(Message).where(Message.id.in_(replaced_ids)))
		await delete_stale_summaries_for_thread(
			thread.id,
			session,
			changed_message_ids=[*replaced_ids, message.id],
		)
	return applied, old_attachment_links


async def apply_existing_message_splice(
	session: AsyncSession,
	thread: Thread,
	message: Message,
	parent_id: TypeID | None,
	principal: Principal,
	multi_writer: bool,
) -> MessageSplice:
	"""move an existing message through the standard splice machinery."""
	splice = await resolve_message_splice(
		session,
		thread,
		parent_id,
		message.id,
		explicit_parent=True,
		multi_writer=multi_writer,
	)
	await _validate_existing_references(session, thread, splice, message.id)
	message.parent_id = splice.parent_id
	applied, _old_attachment_links = await apply_message_splice(
		session,
		thread,
		splice,
		message,
		principal,
		multi_writer,
	)
	return applied


async def _displaced_successor_ids(
	session: AsyncSession,
	run_tail: Message,
	run_id: TypeID,
	read_through_message_id: TypeID | None,
) -> tuple[list[TypeID], bool]:
	"""the successors to move, and whether any blocks leaf advancement."""
	successors = list(
		await session.scalars(
			select(Message)
			.where(Message.parent_id == run_tail.id)
			.order_by(Message.created_at, Message.id)
		)
	)
	if not successors:
		return [], False
	seen_ids: set[TypeID] = set()
	if read_through_message_id is not None:
		seen = branch_depths_cte(read_through_message_id)
		seen_ids = set(
			await session.scalars(
				select(seen.c.msg_id).where(
					seen.c.msg_id.in_([message.id for message in successors])
				)
			)
		)
	tail_run_id = run_tail.public_metadata.get("run_id")
	blocks_leaf = False
	for successor in successors:
		if successor.id in seen_ids:
			blocks_leaf = True
			continue
		if tail_run_id != run_id and successor.public_metadata.get("run_id"):
			continue
		blocks_leaf = True
	return [successor.id for successor in successors], blocks_leaf


async def resolve_run_tail_splice(
	session: AsyncSession,
	thread: Thread,
	run_tail_id: TypeID,
	message_id: TypeID,
	run_id: TypeID,
	multi_writer: bool,
	read_through_message_id: TypeID | None = None,
) -> MessageSplice:
	"""place generated output at its run tail and preserve unseen traffic.

	call this with the thread write lock held: the head is refreshed here, so a
	caller that loaded the thread before the lock still places against the head
	that survived the wait.
	"""
	await session.refresh(thread, attribute_names=["current_message_id"])
	tail = await session.get(Message, run_tail_id)
	if tail is None or tail.thread_id != thread.id:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="message not found in this thread",
		)
	if thread.current_message_id == run_tail_id:
		return MessageSplice(
			parent_id=run_tail_id,
			leaf=ThreadLeaf(kind="thread"),
		)
	successor_ids, blocks_leaf = await _displaced_successor_ids(
		session, tail, run_id, read_through_message_id
	)
	branch = await resolve_message_branch_from_head(
		session,
		run_tail_id,
		thread.current_message_id,
	)
	if branch is None:
		if multi_writer:
			selected = selected_message_ids_cte([thread.id])
			membership = select(selected.c.m_id).where(selected.c.m_id == run_tail_id)
			if not await session.scalar(select(exists(membership))):
				raise HTTPException(
					status_code=status.HTTP_409_CONFLICT,
					detail="run tail is not on a selected conversation branch",
				)
		return MessageSplice(
			parent_id=run_tail_id,
			reparent_message_ids=successor_ids,
			leaf=ThreadLeaf(kind="thread") if not blocks_leaf else None,
		)
	return MessageSplice(
		parent_id=run_tail_id,
		reparent_message_ids=successor_ids,
		leaf=(
			BranchLeaf(
				kind="branch",
				root_id=branch.root_id,
			)
			if not blocks_leaf
			else None
		),
	)


async def _require_free_canon_anchor(
	session: AsyncSession,
	thread_id: TypeID,
	anchor_id: TypeID,
	canon_ids: set[str],
) -> None:
	"""ensure a canon message has no selected off-canon child."""
	siblings = (
		await session.scalars(
			select(Message.id).where(
				Message.thread_id == thread_id,
				Message.parent_id == anchor_id,
				Message.branch_current_message_id.is_not(None),
			)
		)
	).all()
	if any(str(sibling) not in canon_ids for sibling in siblings):
		raise HTTPException(
			status_code=status.HTTP_409_CONFLICT,
			detail="this message already has an off-canon branch",
		)


async def _require_free_branch_anchor(
	session: AsyncSession,
	anchor_id: TypeID,
) -> None:
	"""ensure a branch message has no selected nested branch."""
	occupied = select(Message.id).where(
		Message.parent_id == anchor_id,
		Message.branch_current_message_id.is_not(None),
	)
	if await session.scalar(select(exists(occupied))):
		raise HTTPException(
			status_code=status.HTTP_409_CONFLICT,
			detail="this message already has a nested branch",
		)


async def resolve_message_splice(
	session: AsyncSession,
	thread: Thread,
	parent_id: TypeID | None,
	message_id: TypeID,
	explicit_parent: bool,
	multi_writer: bool,
	advances_head: bool = True,
) -> MessageSplice:
	"""derive ordinary placement from the current native-tree topology."""
	head_id = thread.current_message_id
	if not explicit_parent:
		return MessageSplice(
			parent_id=head_id,
			leaf=ThreadLeaf(kind="thread") if advances_head else None,
		)
	if parent_id is not None and parent_id == head_id:
		return MessageSplice(
			parent_id=parent_id,
			leaf=ThreadLeaf(kind="thread") if advances_head else None,
		)
	if not multi_writer:
		return MessageSplice(
			parent_id=parent_id,
			leaf=ThreadLeaf(kind="thread") if advances_head else None,
		)
	if parent_id is None:
		if head_id is None:
			return MessageSplice(
				parent_id=None,
				leaf=ThreadLeaf(kind="thread") if advances_head else None,
			)
		return MessageSplice(
			parent_id=None,
			leaf=(
				BranchLeaf(kind="branch", root_id=message_id) if advances_head else None
			),
		)

	canon_ids = await canon_message_ids(session, thread.id)
	if str(parent_id) in canon_ids:
		await _require_free_canon_anchor(session, thread.id, parent_id, canon_ids)
		return MessageSplice(
			parent_id=parent_id,
			leaf=(
				BranchLeaf(kind="branch", root_id=message_id) if advances_head else None
			),
		)
	branch = await resolve_message_branch(session, parent_id, canon_ids)
	if branch is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="message not found in this thread",
		)
	if parent_id == branch.leaf_id:
		return MessageSplice(
			parent_id=parent_id,
			leaf=(
				BranchLeaf(kind="branch", root_id=branch.root_id)
				if advances_head
				else None
			),
		)
	await _require_free_branch_anchor(session, parent_id)
	return MessageSplice(
		parent_id=parent_id,
		leaf=(BranchLeaf(kind="branch", root_id=message_id) if advances_head else None),
	)


async def branch_roots_losing_current_message(
	session: AsyncSession,
	deleted_ids: list[str],
) -> list[TypeID]:
	"""surviving branch roots whose current message is being deleted."""
	rows = await session.scalars(
		select(Message.id).where(
			Message.branch_current_message_id.in_(deleted_ids),
			Message.id.notin_(deleted_ids),
		)
	)
	return list(rows)


async def repair_branch_pointers(
	session: AsyncSession,
	thread_id: TypeID,
	root_ids: list[TypeID],
) -> None:
	"""re-point branch roots at their deepest surviving message."""
	for root_id in root_ids:
		leaf_id = await deepest_leaf_from(session, thread_id, root_id)
		await session.execute(
			update(Message)
			.where(Message.id == root_id)
			.values(**_pointer_values(leaf_id))
		)
