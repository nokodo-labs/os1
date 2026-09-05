"""transcript passages: build them from a message tree, then persist them.

turns a thread's full message tree into deterministic, branch-independent
transcript passages. segments are maximal linear runs between branch points;
passages pack consecutive user/assistant turns within one segment, so a
passage is always entirely on or entirely off any root-to-leaf branch and
active-branch filtering reduces to an anchor membership check at query time.
"""

import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from fastapi import HTTPException, status
from sqlalchemy import Select, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.access_rule import AccessLevel
from api.models.message import Message, MessageType
from api.models.thread_passage import ThreadPassage
from api.schemas.thread import ThreadPassageUpdate
from api.v1.service.authentication import Principal
from api.v1.service.authorization import require_thread_access
from nokodo_ai.utils.tokens import CHARS_PER_TOKEN, estimate_tokens
from nokodo_ai.utils.typeid import TypeID


class TranscriptMessage(Protocol):
	"""minimal message surface the passage engine reads."""

	@property
	def id(self) -> object: ...
	@property
	def parent_id(self) -> object | None: ...
	@property
	def type(self) -> MessageType: ...
	@property
	def text_content(self) -> str: ...
	@property
	def created_at(self) -> datetime: ...


@dataclass(frozen=True, slots=True)
class TranscriptPassage:
	"""one embeddable slice of a thread's transcript."""

	first_message_id: str
	last_message_id: str
	part_index: int
	content_hash: str
	anchor_message_id: str
	text: str


@dataclass(frozen=True, slots=True)
class _Unit:
	"""one indexable message turn within a segment."""

	message_id: str
	text: str
	tokens: int
	is_user: bool


# fraction of target_tokens after which a new user turn starts a new passage,
# biasing passage boundaries toward topic starts.
_USER_BOUNDARY_FILL = 0.6


def _content_hash(text: str) -> str:
	return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _segments[T: TranscriptMessage](messages: list[T]) -> list[list[T]]:
	"""split the message tree into maximal linear runs between branch points."""
	by_id: dict[str, T] = {str(m.id): m for m in messages}
	children: dict[str | None, list[T]] = {}
	for message in messages:
		parent_key = str(message.parent_id) if message.parent_id is not None else None
		if parent_key is not None and parent_key not in by_id:
			parent_key = None
		children.setdefault(parent_key, []).append(message)
	for siblings in children.values():
		siblings.sort(key=lambda m: (m.created_at, str(m.id)))

	segments: list[list[T]] = []
	stack: list[T] = list(reversed(children.get(None, [])))
	while stack:
		current = stack.pop()
		segment: list[T] = []
		while True:
			segment.append(current)
			kids = children.get(str(current.id), [])
			if len(kids) != 1:
				stack.extend(reversed(kids))
				break
			current = kids[0]
		segments.append(segment)
	return segments


def _split_oversize(text: str, target_tokens: int, overlap_tokens: int) -> list[str]:
	"""split one oversized message text into deterministic character slices."""
	step_chars = max(int(target_tokens * CHARS_PER_TOKEN), 1)
	overlap_chars = min(int(overlap_tokens * CHARS_PER_TOKEN), step_chars // 2)
	parts: list[str] = []
	start = 0
	while start < len(text):
		end = min(start + step_chars, len(text))
		part = text[start:end].strip()
		if part:
			parts.append(part)
		if end >= len(text):
			break
		start = end - overlap_chars
	return parts


def build_transcript_passages[T: TranscriptMessage](
	messages: list[T],
	target_tokens: int,
	overlap_tokens: int,
) -> list[TranscriptPassage]:
	"""build deterministic transcript passages over the full message tree."""
	passages: list[TranscriptPassage] = []
	for segment in _segments(messages):
		units: list[_Unit] = []
		for message in segment:
			if message.type not in (MessageType.USER, MessageType.ASSISTANT):
				continue
			text = message.text_content
			if not text:
				continue
			line = f"{message.type.value}: {text}"
			units.append(
				_Unit(
					message_id=str(message.id),
					text=line,
					tokens=estimate_tokens(line),
					is_user=message.type == MessageType.USER,
				)
			)
		passages.extend(_pack_units(units, target_tokens, overlap_tokens))
	return passages


def _pack_units(
	units: list[_Unit],
	target_tokens: int,
	overlap_tokens: int,
) -> list[TranscriptPassage]:
	passages: list[TranscriptPassage] = []
	current: list[_Unit] = []
	carried = 0
	current_tokens = 0

	def flush() -> None:
		nonlocal current, carried, current_tokens
		anchored = current[carried:]
		if anchored:
			text = "\n".join(u.text for u in current)
			passages.append(
				TranscriptPassage(
					first_message_id=current[0].message_id,
					last_message_id=current[-1].message_id,
					part_index=0,
					content_hash=_content_hash(text),
					anchor_message_id=anchored[0].message_id,
					text=text,
				)
			)
		current = []
		carried = 0
		current_tokens = 0

	def carry_overlap(previous: list[_Unit]) -> None:
		nonlocal current, carried, current_tokens
		kept: list[_Unit] = []
		total = 0
		for unit in reversed(previous):
			if total + unit.tokens > overlap_tokens or len(kept) >= len(previous) - 1:
				break
			kept.append(unit)
			total += unit.tokens
		current = list(reversed(kept))
		carried = len(current)
		current_tokens = total

	for unit in units:
		if unit.tokens > target_tokens:
			flush()
			for part_index, part in enumerate(
				_split_oversize(unit.text, target_tokens, overlap_tokens)
			):
				passages.append(
					TranscriptPassage(
						first_message_id=unit.message_id,
						last_message_id=unit.message_id,
						part_index=part_index,
						content_hash=_content_hash(part),
						anchor_message_id=unit.message_id,
						text=part,
					)
				)
			continue
		would_overflow = current_tokens + unit.tokens > target_tokens
		user_boundary = (
			unit.is_user
			and len(current) > carried
			and current_tokens >= target_tokens * _USER_BOUNDARY_FILL
		)
		if current and (would_overflow or user_boundary):
			previous = list(current)
			flush()
			carry_overlap(previous)
		current.append(unit)
		current_tokens += unit.tokens
	flush()
	return passages


# persisted passages


def _passages_for_thread_stmt(thread_id: TypeID | str) -> Select[tuple[ThreadPassage]]:
	"""select the passages owned by one thread through their first message."""
	return (
		select(ThreadPassage)
		.join(Message, Message.id == ThreadPassage.first_message_id)
		.where(Message.thread_id == str(thread_id))
	)


async def list_passages(
	thread_id: TypeID,
	session: AsyncSession,
) -> list[ThreadPassage]:
	"""list stored passages for a thread in transcript order."""
	stmt = _passages_for_thread_stmt(thread_id).order_by(
		Message.created_at.asc(),
		ThreadPassage.part_index.asc(),
	)
	return list((await session.execute(stmt)).scalars().all())


async def list_unenriched_passages(
	thread_id: TypeID,
	session: AsyncSession,
	limit: int,
) -> list[ThreadPassage]:
	"""list passages still missing enrichment, newest first."""
	stmt = (
		_passages_for_thread_stmt(thread_id)
		.where(ThreadPassage.enrichment.is_(None))
		.order_by(ThreadPassage.created_at.desc())
		.limit(limit)
	)
	return list((await session.execute(stmt)).scalars().all())


async def delete_passages(
	session: AsyncSession,
	thread_ids: list[TypeID | str] | None = None,
) -> None:
	"""delete stored passages; thread_ids=None means every persisted passage."""
	if thread_ids is None:
		await session.execute(delete(ThreadPassage))
		return
	if not thread_ids:
		return
	owned = (
		select(ThreadPassage.id)
		.join(Message, Message.id == ThreadPassage.first_message_id)
		.where(Message.thread_id.in_([str(tid) for tid in thread_ids]))
	)
	await session.execute(
		delete(ThreadPassage).where(
			ThreadPassage.id.in_(owned.scalar_subquery()),
		)
	)


async def load_passage_for_thread(
	thread_id: TypeID,
	passage_id: TypeID,
	session: AsyncSession,
) -> ThreadPassage:
	"""load a passage scoped to a thread or raise a 404."""
	stmt = _passages_for_thread_stmt(thread_id).where(
		ThreadPassage.id == str(passage_id)
	)
	passage = (await session.execute(stmt)).scalars().one_or_none()
	if passage is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="passage not found",
		)
	return passage


async def list_thread_passages(
	thread_id: TypeID,
	session: AsyncSession,
	principal: Principal,
) -> list[ThreadPassage]:
	"""list stored passages for a thread. requires thread admin access."""
	await require_thread_access(
		thread_id, session, principal, required_level=AccessLevel.ADMIN
	)
	return await list_passages(thread_id, session)


async def get_thread_passage(
	thread_id: TypeID,
	passage_id: TypeID,
	session: AsyncSession,
	principal: Principal,
) -> ThreadPassage:
	"""get one stored passage. requires thread admin access."""
	await require_thread_access(
		thread_id, session, principal, required_level=AccessLevel.ADMIN
	)
	return await load_passage_for_thread(thread_id, passage_id, session)


async def update_thread_passage_enrichment(
	thread_id: TypeID,
	passage_id: TypeID,
	passage_in: ThreadPassageUpdate,
	session: AsyncSession,
	principal: Principal,
) -> ThreadPassage:
	"""override or clear a passage enrichment. requires thread admin access.

	span identity, transcript content, and hashes stay read-only: they are
	derived by reconciliation, not authored.
	"""
	await require_thread_access(
		thread_id, session, principal, required_level=AccessLevel.ADMIN
	)
	passage = await load_passage_for_thread(thread_id, passage_id, session)
	updates = passage_in.model_dump(exclude_unset=True)
	if "enrichment" in updates:
		passage.enrichment = updates["enrichment"]
		passage.enrichment_model_id = None
		passage.enriched_at = None
		passage.enrichment_pipeline_v = None
	await session.flush()
	await session.refresh(passage)
	return passage
