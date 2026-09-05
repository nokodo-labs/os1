"""message lifecycle writes: create, in-place edit, and turn deletion."""

import logging
from collections.abc import Awaitable
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.database.advisory_locks import acquire_resource_write_lock
from api.database.post_commit import (
	enqueue_post_commit_action,
	run_post_commit_actions,
	run_post_commit_actions_safely,
)
from api.models.access_rule import AccessLevel
from api.models.event import Event, EventScope
from api.models.event_types import EventType
from api.models.message import Message, MessageType
from api.models.message_attachment import MessageAttachment
from api.models.message_mention import MessageMention
from api.models.notification import Notification
from api.models.thread import Thread
from api.permissions import ResourceType
from api.schemas.common import unwrap_missing
from api.schemas.message import (
	BranchLeaf,
	MessageSplice,
	MessageUpdate,
	ResourceAttachment,
)
from api.schemas.notification import NotificationPayload
from api.v1.service.authentication import Principal
from api.v1.service.authorization import (
	apply_metadata_write,
	list_accessible_user_ids_for_resources,
	require_resource_access,
)
from api.v1.service.events import fanout_event, persist_and_fanout_event
from api.v1.service.notifications import deliver_notification, stage_notifications
from api.v1.service.resource_origins import (
	assign_resource_origins,
)
from api.v1.service.resource_payload_cache import invalidate_resource_payload_cache
from api.v1.service.threads.addressing import (
	build_mention_links,
	resolve_invoked_agents,
	resolve_reply_anchor,
)
from api.v1.service.threads.attachments import (
	attachment_resource_refs,
	create_message_attachments,
	refresh_attachment_access,
	replace_message_attachments,
)
from api.v1.service.threads.common import (
	emit_thread_updated,
	is_multi_writer_thread,
	load_thread,
	message_event_data,
)
from api.v1.service.threads.drafts import MessageDraft
from api.v1.service.threads.splices import (
	PreparedPlacement,
	apply_message_splice,
	branch_roots_losing_current_message,
	clear_pointers_on_canon,
	prepare_message_placement,
	repair_branch_pointers,
	resolve_run_tail_splice,
)
from api.v1.service.threads.summaries import delete_stale_summaries_for_thread
from api.v1.service.threads.tree import deepest_leaf_from
from api.v1.service.threads.user_state import ensure_participant
from nokodo_ai.utils.typeid import TypeID, new_typeid


logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class WrittenMessage:
	"""a persisted message, and what it asks the server to do next."""

	message: Message
	"""the committed row."""
	splice: MessageSplice
	"""tree splice applied under the thread write lock."""
	invoked_agent_ids: list[TypeID]
	"""agents this message runs, resolved under the thread write lock."""

	@property
	def container_root_id(self) -> TypeID | None:
		"""the conversation container the message landed in."""
		if isinstance(self.splice.leaf, BranchLeaf):
			return self.splice.leaf.root_id
		return None


class CommittedMessageWriteError(RuntimeError):
	"""a message and its durable events committed but delivery work failed."""

	def __init__(self, written: WrittenMessage, cause: Exception) -> None:
		"""carry the committed result out past the failure that followed it."""
		super().__init__("message committed but post-commit work failed")
		self.written = written
		self.cause = cause


class _CommittedSplicedMessageError(RuntimeError):
	"""internal committed result awaiting its invocation decision."""

	def __init__(
		self,
		message: Message,
		splice: MessageSplice,
		cause: Exception,
	) -> None:
		"""carry the committed row out before its invocations are resolved."""
		super().__init__("spliced message committed but post-commit work failed")
		self.message = message
		self.splice = splice
		self.cause = cause


def _delivery_failure(error: Exception) -> Exception:
	"""the one failure a caller re-raises, unwrapped from its group.

	post-commit actions run as a group and report as one, but ``create_message``
	re-raises this at its caller - and a caller matching on ``HTTPException``
	stops matching once the real error is wrapped in an ``ExceptionGroup``.
	"""
	while isinstance(error, ExceptionGroup) and len(error.exceptions) == 1:
		inner = error.exceptions[0]
		if not isinstance(inner, Exception):
			break
		error = inner
	return error


async def _invalidate_cache_best_effort(
	invalidation: Awaitable[None],
	thread_id: TypeID,
) -> None:
	"""drop a cache entry without letting the failure reach the writer.

	the row is already committed and every cached projection of it expires on
	its own, so a cache that refused to be dropped is stale for a TTL - not a
	reason to report a written message as failed.
	"""
	try:
		await invalidation
	except Exception:
		logger.exception(
			"failed to invalidate cached thread state after a message write",
			extra={"thread_id": str(thread_id)},
		)


@dataclass(slots=True)
class PreparedUserMessageTurnDeletion:
	"""authorized state required to delete a user message turn."""

	thread: Thread
	"""the thread the turn is being removed from."""
	message_id: TypeID
	"""the user message whose turn this deletes."""
	principal: Principal
	"""who authorized the deletion."""
	parent_id: TypeID | None
	"""what the thread head falls back to once the turn is gone."""
	deleted_ids: list[str]
	"""every row in the subtree, resolved before the delete runs."""


async def create_message(
	thread_id: TypeID,
	draft: MessageDraft,
	session: AsyncSession,
	principal: Principal,
	message_id: TypeID | None = None,
	origin_session_id: str | None = None,
	advances_head: bool = True,
	originated_resources: list[ResourceAttachment] | None = None,
	placement: PreparedPlacement | None = None,
) -> WrittenMessage:
	"""persist one message and return decisions made under the write lock."""
	try:
		return await create_message_with_commit_outcome(
			thread_id,
			draft,
			session,
			principal,
			placement=placement,
			message_id=message_id,
			origin_session_id=origin_session_id,
			advances_head=advances_head,
			originated_resources=originated_resources,
		)
	except CommittedMessageWriteError as error:
		raise error.cause.with_traceback(error.cause.__traceback__) from None


async def create_message_with_commit_outcome(
	thread_id: TypeID,
	draft: MessageDraft,
	session: AsyncSession,
	principal: Principal,
	message_id: TypeID | None = None,
	origin_session_id: str | None = None,
	advances_head: bool = True,
	originated_resources: list[ResourceAttachment] | None = None,
	placement: PreparedPlacement | None = None,
) -> WrittenMessage:
	"""persist one message and report a committed delivery failure."""
	thread, notify_recipient_ids = await _begin_message_write(
		thread_id,
		session,
		principal,
		notifies=draft.type == MessageType.USER,
	)
	resolved_message_id = message_id or TypeID(new_typeid("msg"))
	if placement is None:
		placement = await prepare_message_placement(
			session,
			thread,
			draft.splice,
			resolved_message_id,
			principal=principal,
			advances_head=advances_head,
		)
	multi_writer = placement.multi_writer
	splice = placement.splice
	mention_links, agent_participants = await build_mention_links(
		session,
		thread_id,
		draft.mentions,
		principal,
	)
	invoked_agent_ids = await resolve_invoked_agents(
		session,
		draft.mentions,
		agent_participants,
	)
	if len(invoked_agent_ids) > 1:
		raise HTTPException(
			status_code=status.HTTP_501_NOT_IMPLEMENTED,
			detail="invoking multiple agents is not implemented",
		)
	try:
		message, applied_splice = await _persist_spliced_message(
			thread,
			draft,
			session,
			principal,
			splice=splice,
			notify_recipient_ids=notify_recipient_ids,
			message_id=resolved_message_id,
			origin_session_id=origin_session_id,
			originated_resources=originated_resources,
			mention_links=mention_links,
			multi_writer=multi_writer,
		)
	except _CommittedSplicedMessageError as error:
		raise CommittedMessageWriteError(
			WrittenMessage(
				message=error.message,
				splice=error.splice,
				invoked_agent_ids=invoked_agent_ids,
			),
			error.cause,
		) from error.cause
	return WrittenMessage(
		message=message,
		splice=applied_splice,
		invoked_agent_ids=invoked_agent_ids,
	)


async def create_message_at_run_tail(
	thread_id: TypeID,
	draft: MessageDraft,
	run_tail_id: TypeID,
	run_id: TypeID,
	session: AsyncSession,
	principal: Principal,
	message_id: TypeID | None = None,
	origin_session_id: str | None = None,
	read_through_message_id: TypeID | None = None,
	originated_resources: list[ResourceAttachment] | None = None,
) -> WrittenMessage:
	"""persist one message a run generated, at that run's own tail.

	the run answers the snapshot it last read, so its output goes in after its
	own tail rather than appended to a conversation it never read.
	"""
	try:
		return await create_message_at_run_tail_with_commit_outcome(
			thread_id,
			draft,
			run_tail_id,
			run_id,
			session,
			principal,
			message_id=message_id,
			origin_session_id=origin_session_id,
			read_through_message_id=read_through_message_id,
			originated_resources=originated_resources,
		)
	except CommittedMessageWriteError as error:
		raise error.cause.with_traceback(error.cause.__traceback__) from None


async def create_message_at_run_tail_with_commit_outcome(
	thread_id: TypeID,
	draft: MessageDraft,
	run_tail_id: TypeID,
	run_id: TypeID,
	session: AsyncSession,
	principal: Principal,
	message_id: TypeID | None = None,
	origin_session_id: str | None = None,
	read_through_message_id: TypeID | None = None,
	originated_resources: list[ResourceAttachment] | None = None,
) -> WrittenMessage:
	"""persist run-tail output and report a committed delivery failure."""
	thread, notify_recipient_ids = await _begin_message_write(
		thread_id,
		session,
		principal,
		notifies=draft.type == MessageType.USER,
	)
	resolved_message_id = message_id or TypeID(new_typeid("msg"))
	multi_writer = await is_multi_writer_thread(session, thread_id)
	splice = await resolve_run_tail_splice(
		session,
		thread,
		run_tail_id,
		resolved_message_id,
		run_id,
		multi_writer,
		read_through_message_id,
	)
	try:
		message, applied_splice = await _persist_spliced_message(
			thread,
			draft,
			session,
			principal,
			splice=splice,
			notify_recipient_ids=notify_recipient_ids,
			message_id=resolved_message_id,
			origin_session_id=origin_session_id,
			originated_resources=originated_resources,
			mention_links=[],
			multi_writer=multi_writer,
		)
	except _CommittedSplicedMessageError as error:
		raise CommittedMessageWriteError(
			WrittenMessage(
				message=error.message,
				splice=error.splice,
				invoked_agent_ids=[],
			),
			error.cause,
		) from error.cause
	return WrittenMessage(
		message=message,
		splice=applied_splice,
		invoked_agent_ids=[],
	)


async def _begin_message_write(
	thread_id: TypeID,
	session: AsyncSession,
	principal: Principal,
	notifies: bool,
) -> tuple[Thread, list[TypeID]]:
	"""take the thread write lock and resolve notification recipients.

	only a human's message notifies anyone, and a run writes one row per
	streamed assistant and tool message - so the ACL read is skipped unless
	the draft can actually produce a notification.
	"""
	thread = await load_thread(
		thread_id,
		session,
		principal,
		required_level=AccessLevel.EDITOR,
	)
	await acquire_resource_write_lock(session, "thread", thread_id)
	# the head was read before the lock; a writer that committed while we
	# queued would leave us placing against a stale one.
	await session.refresh(thread, attribute_names=["current_message_id"])
	if not notifies:
		return thread, []
	# resolved before the participant relationship can change
	accessible_ids = await list_accessible_user_ids_for_resources(
		[(ResourceType.THREAD, thread_id)], session
	)
	excluded: set[TypeID] = {principal.user.id}
	for part in thread.participants:
		if part.user_id is None:
			continue
		if part.muted or (part.metadata_ or {}).get("invite_status") == "pending":
			excluded.add(part.user_id)
	return thread, [uid for uid in accessible_ids if uid not in excluded]


async def _persist_spliced_message(
	thread: Thread,
	draft: MessageDraft,
	session: AsyncSession,
	principal: Principal,
	splice: MessageSplice,
	notify_recipient_ids: list[TypeID],
	message_id: TypeID | None,
	origin_session_id: str | None,
	originated_resources: list[ResourceAttachment] | None,
	mention_links: list[MessageMention],
	multi_writer: bool,
) -> tuple[Message, MessageSplice]:
	"""persist one message and apply its validated tree splice."""
	message, attachment_links = await _create_message_row(
		thread,
		draft,
		session,
		principal,
		splice,
		message_id,
		originated_resources,
		mention_links,
	)
	thread_id = thread.id
	applied_splice, old_attachment_links = await apply_message_splice(
		session,
		thread,
		splice,
		message,
		principal,
		multi_writer,
	)

	# ensure sender is tracked as a participant
	await ensure_participant(thread_id, session, user_id=principal.user.id)
	await session.flush()
	await session.refresh(thread, attribute_names=["last_activity_at", "updated_at"])

	message_data = message_event_data(message)
	message_data["splice"] = applied_splice.model_dump(mode="json")
	events = [
		Event(
			scope=EventScope.THREAD,
			scope_id=str(thread_id),
			type=EventType.MESSAGE_CREATED,
			data=message_data,
			user_id=principal.user.id,
			thread_id=str(thread_id),
			message_id=str(message.id),
		)
	]

	if applied_splice.reparent_message_ids:
		successors = list(
			await session.scalars(
				select(Message).where(
					Message.id.in_(applied_splice.reparent_message_ids)
				)
			)
		)
		if len(successors) != len(applied_splice.reparent_message_ids):
			logger.warning(
				"reparented message disappeared before update fanout",
				extra={
					"thread_id": str(thread_id),
					"message_id": str(message.id),
				},
			)
		for successor in successors:
			await session.refresh(
				successor,
				attribute_names=["parent_id", "attachment_links", "mention_links"],
			)
			events.append(
				Event(
					scope=EventScope.THREAD,
					scope_id=str(thread_id),
					type=EventType.MESSAGE_UPDATED,
					data=message_event_data(successor),
					user_id=principal.user.id,
					thread_id=str(thread_id),
					message_id=str(successor.id),
				)
			)

	events.append(
		Event(
			scope=EventScope.THREAD,
			scope_id=str(thread_id),
			type=EventType.THREAD_UPDATED,
			data={
				"id": str(thread_id),
				"last_activity_at": thread.last_activity_at.isoformat(),
				"updated_at": thread.updated_at.isoformat(),
			},
			user_id=principal.user.id,
			thread_id=str(thread_id),
		)
	)
	session.add_all(events)
	notifications = await _stage_message_notifications(
		session,
		message,
		thread_id,
		notify_recipient_ids,
		principal,
	)
	attachment_refs = attachment_resource_refs(
		[*old_attachment_links, *attachment_links]
	)

	async def fanout_events(db: AsyncSession) -> None:
		"""deliver what the transaction already made durable."""
		_ = db
		for event in events:
			await fanout_event(event, origin_session_id=origin_session_id)
		for notification in notifications:
			await deliver_notification(notification)

	async def invalidate_attachments(db: AsyncSession) -> None:
		"""drop cached access for resources this write shared or unshared."""
		await _invalidate_cache_best_effort(
			refresh_attachment_access(attachment_refs, db),
			thread_id,
		)

	async def invalidate_thread_payload(db: AsyncSession) -> None:
		"""drop the thread payload this write just made stale."""
		_ = db
		await _invalidate_cache_best_effort(
			invalidate_resource_payload_cache(ResourceType.THREAD, thread_id),
			thread_id,
		)

	enqueue_post_commit_action(session, fanout_events)
	enqueue_post_commit_action(session, invalidate_attachments)
	enqueue_post_commit_action(session, invalidate_thread_payload)
	await session.commit()

	try:
		await run_post_commit_actions(session)
	except Exception as error:
		raise _CommittedSplicedMessageError(
			message,
			applied_splice,
			_delivery_failure(error),
		) from error
	return message, applied_splice


async def _create_message_row(
	thread: Thread,
	draft: MessageDraft,
	session: AsyncSession,
	principal: Principal,
	splice: MessageSplice,
	message_id: TypeID | None,
	originated_resources: list[ResourceAttachment] | None,
	mention_links: list[MessageMention],
) -> tuple[Message, list[MessageAttachment]]:
	"""create one message row and its related rows without committing."""
	thread_id = thread.id
	sender_user_id = draft.sender_user_id
	if (
		sender_user_id is not None
		and not principal.user.is_superuser
		and str(sender_user_id) != str(principal.user.id)
	):
		raise HTTPException(
			status_code=status.HTTP_403_FORBIDDEN,
			detail="forbidden",
		)
	if draft.type == MessageType.USER and sender_user_id is None:
		sender_user_id = principal.user.id
	parent_id = splice.parent_id
	# semantic, and deliberately resolved apart from placement: a reply anchor
	# names what the message answers, never where it sits.
	reply_to_message_id = await resolve_reply_anchor(
		session,
		thread_id,
		draft.reply_to_message_id,
	)
	pk: dict[str, object] = {"id": message_id} if message_id is not None else {}

	polymorphic_entry = Message.__mapper__.polymorphic_map.get(draft.type)
	if polymorphic_entry is None:
		raise RuntimeError(f"unmapped message type: {draft.type}")
	message_cls = polymorphic_entry.class_

	message: Message = message_cls(
		thread_id=thread_id,
		parent_id=parent_id,
		reply_to_message_id=reply_to_message_id,
		mention_links=mention_links,
		sender_user_id=sender_user_id,
		sender_agent_id=draft.sender_agent_id,
		task_id=draft.task_id,
		content=[part.model_dump(mode="json") for part in draft.content],
		tool_call_id=draft.tool_call_id,
		is_error=draft.is_error,
		tool_calls=draft.tool_calls,
		finish_reason=draft.finish_reason,
		usage=draft.usage,
		citations=[citation.model_dump(mode="json") for citation in draft.citations],
		**pk,
	)
	message.set_metadata(public=draft.metadata, private=draft.private_metadata)

	thread.last_activity_at = datetime.now(tz=UTC)
	session.add(message)
	await session.flush()
	attachment_links = await create_message_attachments(
		message.id,
		draft.attachments,
		session,
		principal,
	)
	await assign_resource_origins(
		message.id,
		originated_resources or [],
		session,
		principal,
	)
	await session.refresh(
		message,
		attribute_names=["attachment_links", "mention_links"],
	)
	return message, attachment_links


async def _stage_message_notifications(
	session: AsyncSession,
	message: Message,
	thread_id: TypeID,
	recipient_ids: list[TypeID],
	principal: Principal,
) -> list[Notification]:
	"""stage durable notifications for a human message before commit."""
	if message.type != MessageType.USER or not recipient_ids:
		return []
	sender_name = principal.subject.display_name or principal.subject.username
	preview = (message.text_content or "").strip()
	return await stage_notifications(
		session,
		NotificationPayload(
			title=sender_name,
			body=preview[:120] or "sent a message",
			tag=str(thread_id),
			action_url=f"/c/{thread_id}",
			data={
				"thread_id": str(thread_id),
				"message_id": str(message.id),
			},
		),
		recipient_ids,
	)


async def update_user_message(
	thread_id: TypeID,
	message_id: TypeID,
	message_in: MessageUpdate,
	session: AsyncSession,
	principal: Principal,
	origin_session_id: str | None = None,
) -> Message:
	"""edit one user message in place, recording what it used to say.

	only user messages are editable: a generated row is the record of what a
	model actually produced, and rewriting it would make the transcript a
	claim rather than evidence.
	"""
	thread = await load_thread(
		thread_id,
		session,
		principal,
		required_level=AccessLevel.EDITOR,
	)
	message = await session.get(Message, message_id)
	if not message or message.thread_id != thread_id:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="message not found",
		)
	if message.type != MessageType.USER:
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="only user messages can be edited",
		)
	await require_resource_access(
		message_id,
		session,
		principal,
		ResourceType.MESSAGE,
		required_level=AccessLevel.EDITOR,
	)
	# snapshot for the MESSAGE_UPDATED payload: the event log is the edit history.
	previous_content = [dict(part) for part in message.content or []]
	content_update = unwrap_missing(message_in.content)
	if content_update is not None:
		message.content = (
			([{"type": "text", "text": content_update}] if content_update else [])
			if isinstance(content_update, str)
			else [part.model_dump(mode="json") for part in content_update]
		)
	apply_metadata_write(message, message_in.metadata)
	previous_attachments: list[MessageAttachment] = []
	current_attachments: list[MessageAttachment] = []
	attachments_update = unwrap_missing(message_in.attachments)
	if attachments_update is not None:
		previous_attachments, current_attachments = await replace_message_attachments(
			message.id,
			attachments_update,
			session,
			principal,
		)
	now = datetime.now(tz=UTC)
	message.updated_at = now
	thread.last_activity_at = now
	thread.updated_at = now
	await delete_stale_summaries_for_thread(
		thread_id,
		session,
		changed_message_ids=[message.id],
	)
	await session.flush()
	# mentions are a relation, not content, so an edit leaves them intact.
	await session.refresh(
		message,
		attribute_names=["attachment_links", "mention_links"],
	)

	message_data = message_event_data(message)
	if content_update is not None and message.content != previous_content:
		message_data["previous_content"] = previous_content
	# the event log IS the edit history, so it commits with the edit it
	# describes: writing it afterwards leaves a window where the message is
	# changed and what it used to say is gone.
	events = [
		Event(
			scope=EventScope.THREAD,
			scope_id=str(thread_id),
			type=EventType.MESSAGE_UPDATED,
			data=message_data,
			user_id=principal.user.id,
			thread_id=str(thread_id),
			message_id=str(message.id),
		),
		Event(
			scope=EventScope.THREAD,
			scope_id=str(thread_id),
			type=EventType.THREAD_UPDATED,
			data={
				"id": str(thread_id),
				"last_activity_at": thread.last_activity_at.isoformat(),
				"updated_at": thread.updated_at.isoformat(),
			},
			user_id=principal.user.id,
			thread_id=str(thread_id),
		),
	]
	session.add_all(events)
	attachment_refs = attachment_resource_refs(
		[*previous_attachments, *current_attachments]
	)

	async def fanout_events(db: AsyncSession) -> None:
		"""deliver the edit and its history record, both already durable."""
		_ = db
		for event in events:
			await fanout_event(event, origin_session_id=origin_session_id)

	async def invalidate_attachments(db: AsyncSession) -> None:
		"""drop cached access for resources this edit attached or removed."""
		await _invalidate_cache_best_effort(
			refresh_attachment_access(attachment_refs, db),
			thread_id,
		)

	async def invalidate_thread_payload(db: AsyncSession) -> None:
		"""drop the thread payload this edit just made stale."""
		_ = db
		await _invalidate_cache_best_effort(
			invalidate_resource_payload_cache(ResourceType.THREAD, thread_id),
			thread_id,
		)

	enqueue_post_commit_action(session, fanout_events)
	enqueue_post_commit_action(session, invalidate_attachments)
	enqueue_post_commit_action(session, invalidate_thread_payload)
	await session.commit()
	await run_post_commit_actions_safely(session)

	return message


async def delete_user_message_turn(
	thread_id: TypeID,
	message_id: TypeID,
	session: AsyncSession,
	principal: Principal,
	origin_session_id: str | None = None,
) -> None:
	"""delete a user message and its entire descendant subtree.

	all children (assistant responses, follow-up messages, tool messages,
	alternate regeneration branches) are recursively deleted.
	"""
	prepared = await prepare_user_message_turn_deletion(
		thread_id,
		message_id,
		session,
		principal,
	)
	await execute_user_message_turn_deletion(
		prepared,
		session,
		origin_session_id=origin_session_id,
	)


async def prepare_user_message_turn_deletion(
	thread_id: TypeID,
	message_id: TypeID,
	session: AsyncSession,
	principal: Principal,
) -> PreparedUserMessageTurnDeletion:
	"""authorize a message-turn deletion and collect its subtree."""
	thread = await load_thread(
		thread_id,
		session,
		principal,
		required_level=AccessLevel.EDITOR,
	)
	await acquire_resource_write_lock(session, "thread", thread_id)
	await session.refresh(thread, attribute_names=["current_message_id"])

	target = await session.get(Message, str(message_id))
	if not target or target.thread_id != thread_id:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="message not found",
		)
	if target.type != MessageType.USER:
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="only user messages can be deleted",
		)
	await require_resource_access(
		message_id,
		session,
		principal,
		ResourceType.MESSAGE,
		required_level=AccessLevel.EDITOR,
	)

	parent_id = target.parent_id

	# collect the entire subtree via BFS (level-by-level for efficiency)
	deleted_ids: list[str] = [str(message_id)]
	frontier: list[str] = [str(message_id)]
	while frontier:
		result = await session.execute(
			select(Message.id).where(Message.parent_id.in_(frontier))
		)
		children = [str(row[0]) for row in result]
		deleted_ids.extend(children)
		frontier = children
	return PreparedUserMessageTurnDeletion(
		thread=thread,
		message_id=message_id,
		principal=principal,
		parent_id=parent_id,
		deleted_ids=deleted_ids,
	)


async def execute_user_message_turn_deletion(
	prepared: PreparedUserMessageTurnDeletion,
	session: AsyncSession,
	origin_session_id: str | None = None,
) -> None:
	"""execute an authorized user message-turn deletion."""
	thread = prepared.thread
	thread_id = thread.id
	message_id = prepared.message_id
	principal = prepared.principal
	parent_id = prepared.parent_id
	deleted_ids = prepared.deleted_ids

	deleted_set = set(deleted_ids)
	attachment_resource_types = (
		ResourceType.FILE,
		ResourceType.NOTE,
		ResourceType.THREAD,
		ResourceType.PROJECT,
		ResourceType.REMINDER,
		ResourceType.REMINDER_LIST,
		ResourceType.CALENDAR_EVENT,
		ResourceType.CALENDAR,
	)
	attachment_rows = (
		await session.execute(
			select(
				MessageAttachment.file_id,
				MessageAttachment.note_id,
				MessageAttachment.thread_id,
				MessageAttachment.project_id,
				MessageAttachment.reminder_id,
				MessageAttachment.reminder_list_id,
				MessageAttachment.calendar_event_id,
				MessageAttachment.calendar_id,
			).where(MessageAttachment.message_id.in_(deleted_ids))
		)
	).all()
	attachment_refs: list[tuple[ResourceType, TypeID]] = []

	# compute new current_message_id before deleting
	head_moved = False
	if thread.current_message_id and str(thread.current_message_id) in deleted_set:
		thread.current_message_id = await deepest_leaf_from(
			session, thread_id, parent_id, exclude=deleted_set
		)
		head_moved = True

	thread.last_activity_at = datetime.now(tz=UTC)

	# collected first: the fk nulls these pointers as the subtree goes away.
	orphaned_roots = await branch_roots_losing_current_message(session, deleted_ids)

	# bulk-delete subtree; DB CASCADE on event FKs handles cleanup
	await session.execute(sa_delete(Message).where(Message.id.in_(deleted_ids)))
	await repair_branch_pointers(session, thread_id, orphaned_roots)
	if head_moved:
		await clear_pointers_on_canon(session, thread.current_message_id)
	for attachment_row in attachment_rows:
		for resource_type, resource_id in zip(
			attachment_resource_types,
			attachment_row,
			strict=True,
		):
			if resource_id is not None:
				attachment_refs.append((resource_type, TypeID(str(resource_id))))
	attachment_refs = list(dict.fromkeys(attachment_refs))

	async def refresh_attachments(db: AsyncSession) -> None:
		"""drop cached access for resources the deleted turn had shared."""
		await _invalidate_cache_best_effort(
			refresh_attachment_access(attachment_refs, db),
			thread_id,
		)

	if attachment_refs:
		enqueue_post_commit_action(session, refresh_attachments)
	await delete_stale_summaries_for_thread(
		thread_id,
		session,
		changed_message_ids=deleted_ids,
	)

	# emit message.deleted event
	await persist_and_fanout_event(
		session,
		event=Event(
			scope=EventScope.THREAD,
			scope_id=str(thread_id),
			type=EventType.MESSAGE_DELETED,
			data={
				"thread_id": str(thread_id),
				"message_id": str(message_id),
				"parent_id": parent_id,
				"deleted_ids": deleted_ids,
			},
			user_id=principal.user.id,
			thread_id=str(thread_id),
		),
		origin_session_id=origin_session_id,
	)
	await invalidate_resource_payload_cache(ResourceType.THREAD, thread_id)

	# persist_and_fanout_event commits; refresh thread to get server-side updated_at
	await session.refresh(thread, attribute_names=["last_activity_at", "updated_at"])

	# emit thread.updated so all sessions reorder the sidebar
	await emit_thread_updated(
		session,
		thread_id,
		principal,
		data={
			"last_activity_at": thread.last_activity_at.isoformat(),
			"updated_at": thread.updated_at.isoformat(),
		},
		origin_session_id=origin_session_id,
	)
