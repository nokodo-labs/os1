"""service layer for memory operations."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable, Coroutine
from typing import Literal

from fastapi import HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from api.database import build_cursor_page, decode_cursor
from api.models.event import Event, EventScope
from api.models.event_types import EventType
from api.models.memory import Memory
from api.permissions import ResourceType
from api.schemas.memory import MemoryCreate, MemoryListFilters, MemoryUpdate
from api.schemas.search import (
	CursorPage,
	SearchMode,
	SearchParams,
	SearchResultItem,
	SearchResultType,
)
from api.v1.service import events as event_service
from api.v1.service import vectorstores as vectorstore_service
from api.v1.service.auth import Principal
from api.v1.service.authorization import list_accessible_user_ids, require_permission
from api.v1.service.chat.models import (
	resolve_task_chat_model,
	run_chat_model_json_schema,
)
from api.v1.service.embeddings import embed_text, embed_texts
from api.v1.service.listing import SortDir, apply_sort
from api.v1.service.vectorize import (
	VectorSpec,
	build_chunk,
	remove_vectorized_resource,
	vectorize_resource,
)
from api.v1.service.vectorstores import VectorChunkResourceType
from nokodo_ai.messages import SystemMessage, UserMessage
from nokodo_ai.threads import Thread as SDKThread
from nokodo_ai.types.json import JSONObject, JSONValue
from nokodo_ai.utils.search import contains_pattern
from nokodo_ai.utils.typeid import TypeID


logger = logging.getLogger(__name__)

MEMORY_POST_PROCESSING_QUERY_MAX_CHARS = 4000
MEMORY_POST_PROCESSING_MEMORY_MAX_CHARS = 1200
MEMORY_POST_PROCESSING_EMBED_TIMEOUT_SECONDS = 45
MEMORY_POST_PROCESSING_SEARCH_TIMEOUT_SECONDS = 20
MEMORY_POST_PROCESSING_MODEL_TIMEOUT_SECONDS = 60

type MemoryPostProcessingProgress = Callable[[int, str], Awaitable[None]]


_POST_PROCESSING_PROMPT = """\
You maintain a collection of Memories - individual facts about a user, each
automatically timestamped on creation or update.

You will be provided with:
1. The most recent conversation turns (negative indices; -1 is the most
   recent overall message).
2. Existing memories semantically related to that conversation, ordered by
   relevance (most relevant first).

Determine what actions to take on the memory collection based on the user's
**latest** message.

<key_instructions>
1. Focus on the user's most **recent** message. Older messages provide
   context but should not generate new memories unless explicitly referenced
   in the latest message.
2. Each memory must represent **a single fact**. Never combine multiple
   unrelated facts into one memory.
3. When the latest message contradicts an existing memory, **update** that
   memory rather than creating a conflicting new one.
4. If memories are exact duplicates or direct conflicts about the same topic,
   **consolidate** them by updating or deleting as appropriate.
5. Capture anything valuable for **personalizing future interactions**.
6. Always **honor memory requests**, whether direct from the user ("remember
   this", "forget that") or implicit through the assistant ("I'll remember
   that"). Treat these as strong signals to store, update, or delete.
7. Each memory must be **self-contained and understandable without external
   context**. Avoid ambiguous references like "it" or "that" - include the
   specific subject. Prefer "User's new TV broke" over "It broke".
8. Be alert to **sarcasm, jokes, and non-literal language**. Do not store
   hyperbole or jokes as factual memories.
9. **Always refer to the user in the third person as "user"**, never by name.
   Normalize the subject of every memory: rewrite "joe loves chocolate" to
   "user loves chocolate". When an existing memory uses a proper name for the
   user, UPDATE it to use "user".
10. Use the `created_at` / `updated_at` timestamps to decide which memory is
    most recent when resolving conflicts.
</key_instructions>

<what_to_extract>
- Personal preferences, opinions, and feelings
- Long-term personal information (likely true for months/years)
- Future-oriented statements ("from now on", "going forward")
- Direct memory requests ("remember that", "forget that")
- Hobbies, interests, skills
- Important life details (job, education, relationships, location)
- Long-term goals, plans, aspirations
- Recurring patterns or habits
- Strong likes/dislikes affecting future conversations
</what_to_extract>

<what_not_to_extract>
- The user's own name, gender, age, birthdate (already in profile)
- Short-term or ephemeral information unlikely to matter later
- Content from translation/rewrite/summarization tasks
- Trivial observations, fleeting thoughts, temporary activities
- Sarcastic remarks, obvious jokes, hyperbole
</what_not_to_extract>

<actions>
Return a list of actions. Use only memory IDs from the related memories list.

**ADD**: create a new memory for new information not already covered, distinct
facts, or explicit memory requests. Provide `content` and optional `tags`.
**UPDATE**: modify an existing memory when information changed, to consolidate
inseparable facts, to honor an update request, or to normalize phrasing.
Provide `id` and `new_content`.
**DELETE**: remove a memory the user asks to forget, that is directly
contradicted, an exact duplicate (keep the oldest), or obsolete. Provide `id`.

If no maintenance is needed, return an empty actions list.
</actions>

<consolidation_rules>
Default to keeping memories granular for precise retrieval. Only consolidate
when it meaningfully improves quality:
- **Exact duplicates**: delete the newer, keep the oldest.
- **Direct conflicts**: update the older memory to the latest information, or
  delete if obsolete.
- **Inseparable facts**: merge into the oldest memory as one self-contained
  statement, then delete the redundant ones. Test: would retrieving one
  without the other create confusion? ("User's cat is named Luna" + "User's
  cat is a Siamese" -> "User has a Siamese cat named Luna").
Keep facts SEPARATE when independently meaningful ("User works at Google" vs
"User got promoted to team lead"). If an existing memory wrongly combines
separable facts, UPDATE it to keep one fact (preserves the timestamp) and ADD
the others.
</consolidation_rules>

<examples>
**Example 1 - Add new, distinct facts**
Conversation:
-2. user: I work as a senior data scientist at Tesla and I love Rust
-1. assistant: That's impressive! Rust is great for systems programming.
Related Memories: []
Output:
{
  "actions": [
    {"action": "add", "content": "User works as a senior data scientist at \
Tesla", "tags": ["work"]},
    {"action": "add", "content": "User's favorite programming language is \
Rust", "tags": ["preferences"]}
  ]
}

**Example 2 - Update on changed preference**
Conversation:
-2. user: Actually I prefer TypeScript over JavaScript these days
-1. assistant: TypeScript's type safety makes frontend more maintainable!
Related Memories:
[{"id": "memory_abc", "created_at": "2024-02-20T14:30:00",
  "content": "User prefers JavaScript for frontend projects"}]
Output:
{
  "actions": [
    {"action": "update", "id": "memory_abc",
     "new_content": "User prefers TypeScript for frontend work"}
  ]
}

**Example 3 - Delete on negation / sarcasm**
Conversation:
-2. user: I'm joking! I didn't actually buy the iPhone!
-1. assistant: Ahh, you got me! No worries.
Related Memories:
[{"id": "memory_xyz", "created_at": "2024-03-01T09:00:00",
  "content": "User just bought a new iPhone"}]
Output:
{"actions": [{"action": "delete", "id": "memory_xyz"}]}

**Example 4 - Normalize a name reference**
Conversation:
-2. user: just call me joe by the way
-1. assistant: Got it, Joe!
Related Memories:
[{"id": "memory_111", "created_at": "2024-01-10T11:00:00",
  "content": "joe loves chocolate"}]
Output:
{
  "actions": [
    {"action": "update", "id": "memory_111",
     "new_content": "User loves chocolate"}
  ]
}

**Example 5 - Passive maintenance: dedupe and merge**
Conversation:
-2. user: Can you help me write a Python function to sort a list?
-1. assistant: Of course! Here's an example using sorted()...
Related Memories:
[
  {"id": "memory_a", "created_at": "2024-02-10T09:00:00",
   "content": "User prefers Python for scripting"},
  {"id": "memory_b", "created_at": "2024-03-15T14:30:00",
   "content": "User likes Python for scripting tasks"},
  {"id": "memory_c", "created_at": "2024-01-15T08:00:00",
   "content": "User's cat is named Luna"},
  {"id": "memory_d", "created_at": "2024-02-20T10:00:00",
   "content": "User's cat is a Siamese"}
]
Output:
{
  "actions": [
    {"action": "delete", "id": "memory_b"},
    {"action": "update", "id": "memory_c",
     "new_content": "User has a Siamese cat named Luna"},
    {"action": "delete", "id": "memory_d"}
  ]
}
</examples>
"""


class _MemoryPostProcessingAction(BaseModel):
	"""a single memory maintenance action."""

	action: Literal["add", "update", "delete"]
	id: str | None = Field(
		default=None,
		description="memory id to act on; required for update and delete",
	)
	content: str | None = Field(
		default=None,
		description="content for a new memory; required for add",
	)
	new_content: str | None = Field(
		default=None,
		description="updated content; required for update",
	)
	tags: list[str] | None = Field(
		default=None,
		description="optional tags for a new memory (add only)",
	)


class _MemoryPostProcessingResponse(BaseModel):
	"""structured response from the post-processing model."""

	actions: list[_MemoryPostProcessingAction] = Field(default_factory=list)


class _MemoryPostProcessingTimeoutError(Exception):
	def __init__(self, stage: str, cause: BaseException) -> None:
		super().__init__(str(cause))
		self.stage = stage
		self.cause_type = type(cause).__name__
		self.cause_message = str(cause)

	def to_result(self) -> JSONObject:
		return {
			"skipped": True,
			"reason": "provider_timeout",
			"stage": self.stage,
			"error": self.cause_type,
			"message": self.cause_message[:500],
		}


def _is_timeout_exception(exc: BaseException) -> bool:
	name = type(exc).__name__
	return (
		isinstance(exc, TimeoutError)
		or name.endswith("TimeoutError")
		or name.endswith("Timeout")
	)


async def _run_memory_stage[ResultT](
	stage: str,
	timeout_seconds: float,
	operation: Awaitable[ResultT],
) -> ResultT:
	try:
		async with asyncio.timeout(timeout_seconds):
			return await operation
	except Exception as exc:
		if _is_timeout_exception(exc):
			raise _MemoryPostProcessingTimeoutError(stage, exc) from exc
		raise


async def _notify_memory_post_processing_progress(
	progress_callback: MemoryPostProcessingProgress | None,
	progress: int,
	stage: str,
) -> None:
	if progress_callback is not None:
		await progress_callback(progress, stage)


def _truncate_post_processing_text(value: str, max_chars: int) -> str:
	trimmed = value.strip()
	if len(trimmed) <= max_chars:
		return trimmed
	return trimmed[:max_chars].rstrip()


async def _get_memory(
	memory_id: TypeID,
	session: AsyncSession,
	principal: Principal,
) -> Memory:
	stmt = select(Memory).where(Memory.id == memory_id)
	if not principal.is_admin:
		stmt = stmt.where(Memory.user_id == principal.user.id)
	result = await session.execute(stmt)
	memory = result.scalars().one_or_none()
	if not memory:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Memory not found",
		)
	return memory


async def create_memory(
	memory_in: MemoryCreate,
	session: AsyncSession,
	principal: Principal,
	origin_session_id: str | None = None,
) -> Memory:
	require_permission(principal, "memories:create")
	data = memory_in.model_dump(by_alias=True)
	if not principal.is_admin:
		data["user_id"] = principal.user.id
	memory = Memory(**data)
	session.add(memory)
	await session.flush()
	await session.refresh(memory)
	memory_id = TypeID(memory.id)
	event = Event(
		scope=EventScope.USER,
		scope_id=principal.user_id,
		type=EventType.MEMORY_CREATED,
		data={"id": str(memory_id)},
		user_id=principal.user_id,
	)
	await event_service.persist_and_fanout_event(
		session,
		event=event,
		origin_session_id=origin_session_id,
	)

	await vectorize_resource(spec=MEMORY_SPEC, resource=memory, session=session)

	return await _get_memory(memory_id, session, principal)


async def list_memories(
	session: AsyncSession,
	principal: Principal,
	filters: MemoryListFilters,
	skip: int = 0,
	limit: int = 50,
	sort_by: str = "updated_at",
	sort_dir: SortDir = "desc",
) -> list[Memory]:
	base = _apply_memory_filters(select(Memory), filters, principal)

	stmt = (
		apply_sort(
			base,
			sort_by=sort_by,
			sort_dir=sort_dir,
			columns={
				"updated_at": Memory.updated_at,
				"created_at": Memory.created_at,
				"content_length": func.length(Memory.content),
				"tags": Memory.tags,
				"last_accessed_at": Memory.last_accessed_at,
				"confidence": Memory.confidence,
			},
			tie_breaker=Memory.id,
		)
		.offset(skip)
		.limit(limit)
	)
	result = await session.execute(stmt)
	return list(result.scalars().all())


async def count_memories(
	session: AsyncSession,
	principal: Principal,
	filters: MemoryListFilters,
) -> int:
	"""count memories matching the list filters."""
	stmt = _apply_memory_filters(
		select(func.count()).select_from(Memory),
		filters,
		principal,
	)
	return await session.scalar(stmt) or 0


def _apply_memory_filters(
	stmt: Select,
	filters: MemoryListFilters,
	principal: Principal,
) -> Select:
	"""apply memory list filters."""
	if not principal.is_admin and filters.owner_id != principal.user.id:
		raise HTTPException(
			status_code=status.HTTP_403_FORBIDDEN,
			detail="forbidden",
		)
	stmt = stmt.where(Memory.user_id == filters.owner_id)
	if filters.search:
		stmt = stmt.where(
			Memory.content.ilike(contains_pattern(filters.search), escape="\\")
		)
	return stmt


async def get_memory(
	memory_id: TypeID,
	session: AsyncSession,
	principal: Principal,
) -> Memory:
	return await _get_memory(memory_id, session, principal)


async def update_memory(
	memory_id: TypeID,
	memory_in: MemoryUpdate,
	session: AsyncSession,
	principal: Principal,
	origin_session_id: str | None = None,
) -> Memory:
	"""update a memory and sync with vectorstore if content changed."""
	memory = await _get_memory(memory_id, session, principal)

	update_data = memory_in.model_dump(exclude_unset=True, by_alias=True)
	for key, value in update_data.items():
		setattr(memory, key, value)

	event = Event(
		scope=EventScope.USER,
		scope_id=principal.user_id,
		type=EventType.MEMORY_UPDATED,
		data={"id": str(memory_id)},
		user_id=principal.user_id,
	)
	await event_service.persist_and_fanout_event(
		session,
		event=event,
		origin_session_id=origin_session_id,
	)

	if await MEMORY_SPEC.should_revectorize(memory, memory_in, session):
		await vectorize_resource(spec=MEMORY_SPEC, resource=memory, session=session)
	return await _get_memory(memory_id, session, principal)


async def delete_memory(
	memory_id: TypeID,
	session: AsyncSession,
	principal: Principal,
	origin_session_id: str | None = None,
) -> None:
	"""delete a memory and remove from the search index."""
	memory = await _get_memory(memory_id, session, principal)
	delete_recipients = await list_accessible_user_ids(
		ResourceType.MEMORY,
		memory_id,
		session,
	)

	await session.delete(memory)

	event = Event(
		scope=EventScope.USER,
		scope_id=principal.user_id,
		type=EventType.MEMORY_DELETED,
		data={"id": str(memory_id)},
		user_id=principal.user_id,
	)
	await event_service.persist_and_fanout_event(
		session,
		event=event,
		origin_session_id=origin_session_id,
		recipient_ids=delete_recipients,
	)

	await remove_vectorized_resource(
		spec=MEMORY_SPEC, resource_id=str(memory_id), session=session
	)


async def delete_all_memories(
	session: AsyncSession,
	principal: Principal,
	origin_session_id: str | None = None,
) -> None:
	"""delete all memories for the current user and remove from search index."""
	user_id = TypeID(principal.user.id)

	result = await session.execute(
		select(func.count()).select_from(Memory).where(Memory.user_id == user_id)
	)
	count = result.scalar_one()
	if count == 0:
		return

	await session.execute(delete(Memory).where(Memory.user_id == user_id))
	event = Event(
		scope=EventScope.USER,
		scope_id=principal.user_id,
		type=EventType.MEMORY_DELETED,
		data={"all": True, "user_id": str(user_id)},
		user_id=principal.user_id,
	)
	await event_service.persist_and_fanout_event(
		session,
		event=event,
		origin_session_id=origin_session_id,
	)

	await vectorstore_service.delete(
		target=vectorstore_service.resource_types_filter(
			[VectorChunkResourceType.MEMORY],
			owner_id=str(user_id),
		),
		session=session,
	)


def _memory_dense_text(memory: Memory) -> str:
	return (memory.content or "").strip()


def _memory_metadata(memory: Memory) -> JSONObject:
	tags: list[JSONValue] = list(memory.tags) if memory.tags else []
	return {
		"resource_type": VectorChunkResourceType.MEMORY.value,
		"owner_id": str(memory.user_id),
		"tags": tags,
	}


async def _memory_should_revectorize(
	memory: Memory,
	memory_in: MemoryUpdate,
	session: AsyncSession,
) -> bool:
	_fields = {"content", "tags"}
	update_data = memory_in.model_dump(exclude_unset=True, mode="python")
	return bool(_fields & update_data.keys())


MEMORY_SPEC: VectorSpec[Memory] = VectorSpec(
	resource_type=VectorChunkResourceType.MEMORY,
	resource_id=lambda m: str(m.id),
	dense_text=_memory_dense_text,
	bm25_text=_memory_dense_text,
	metadata=_memory_metadata,
	should_revectorize=_memory_should_revectorize,
	sort_key="updated_at",
)


async def vectorize_all_memories(session: AsyncSession) -> int:
	"""vectorize all memories in bulk. returns count."""
	stmt = select(Memory)
	result = await session.execute(stmt)
	valid: list[tuple[Memory, str]] = []
	for m in result.scalars().all():
		text = _memory_dense_text(m)
		if text.strip():
			valid.append((m, text))
	if not valid:
		return 0
	embeddings = await embed_texts([text for _, text in valid], session)
	chunks = []
	for (memory, _), emb in zip(valid, embeddings):
		await remove_vectorized_resource(
			spec=MEMORY_SPEC, resource_id=str(memory.id), session=session
		)
		chunks.append(build_chunk(MEMORY_SPEC, memory, emb))
	await vectorstore_service.upsert_chunks(chunks=chunks, session=session)
	return len(valid)


async def _autocomplete_memories(
	q: str,
	db: AsyncSession,
	principal: Principal,
	limit: int = 5,
) -> list[SearchResultItem]:
	"""pg_trgm autocomplete for memories on content."""
	pattern = contains_pattern(q)
	stmt = (
		select(Memory)
		.where(
			or_(
				func.similarity(Memory.content, q) > 0.1,
				Memory.content.ilike(pattern, escape="\\"),
			),
		)
		.order_by(func.similarity(Memory.content, q).desc())
		.limit(limit)
	)
	if not principal.is_admin:
		stmt = stmt.where(Memory.user_id == principal.user.id)
	result = await db.execute(stmt)
	return [
		SearchResultItem(
			type=SearchResultType.MEMORY,
			id=TypeID(mem.id),
			title=mem.content[:80] if mem.content else "",
			preview=", ".join(mem.tags) if mem.tags else None,
			created_at=mem.created_at,
			updated_at=mem.updated_at,
		)
		for mem in result.scalars().all()
	]


async def _hybrid_search_memories(
	query_text: str,
	db: AsyncSession,
	principal: Principal,
	limit: int = 10,
	search_params: SearchParams | None = None,
	query_embedding: list[float] | None = None,
) -> list[SearchResultItem]:
	"""qdrant hybrid search for memories (dense + BM25)."""
	params = search_params or SearchParams()
	need_dense = params.mode in (SearchMode.DENSE, SearchMode.HYBRID, SearchMode.FULL)
	need_sparse = params.mode in (SearchMode.SPARSE, SearchMode.HYBRID, SearchMode.FULL)
	query_emb = (
		query_embedding
		if query_embedding is not None
		else (await embed_text(text=query_text, session=db) if need_dense else None)
	)
	text_query = query_text if need_sparse else None
	# memories are user-private (no sharing) - owner_id filter is efficient.
	query_filter = vectorstore_service.resource_types_filter(
		[VectorChunkResourceType.MEMORY],
		owner_id=(str(principal.user.id) if not principal.is_admin else None),
	)
	results = await vectorstore_service.search(
		session=db,
		query=query_emb,
		text_query=text_query,
		limit=limit,
		query_filter=query_filter,
		normalize=params.normalize,
	)
	if not results:
		return []
	resource_ids: list[str] = [str(r.metadata["resource_id"]) for r in results]
	stmt = select(Memory).where(Memory.id.in_(resource_ids))
	if not principal.is_admin:
		stmt = stmt.where(Memory.user_id == principal.user.id)
	db_result = await db.execute(stmt)
	by_id = {str(m.id): m for m in db_result.scalars().all()}
	score_by_rid = {str(r.metadata["resource_id"]): r.score for r in results}
	items: list[SearchResultItem] = []
	for r in results:
		rid = str(r.metadata["resource_id"])
		mem = by_id.get(rid)
		if not mem:
			continue
		items.append(
			SearchResultItem(
				type=SearchResultType.MEMORY,
				id=TypeID(mem.id),
				title=mem.content[:80] if mem.content else "",
				preview=", ".join(mem.tags) if mem.tags else None,
				score=score_by_rid.get(rid),
				created_at=mem.created_at,
				updated_at=mem.updated_at,
			)
		)
	return items


async def search_memories(
	query_text: str,
	db: AsyncSession,
	principal: Principal,
	limit: int = 10,
	cursor: str | None = None,
	search_params: SearchParams | None = None,
	query_embedding: list[float] | None = None,
) -> CursorPage[SearchResultItem]:
	"""parallel pg_trgm + qdrant hybrid search with cursor pagination."""
	params = search_params or SearchParams()
	coros: list[Coroutine[None, None, list[SearchResultItem]]] = []
	run_autocomplete = params.mode in (
		SearchMode.AUTOCOMPLETE,
		SearchMode.FULL,
	)
	run_hybrid = params.mode in (
		SearchMode.HYBRID,
		SearchMode.DENSE,
		SearchMode.SPARSE,
		SearchMode.FULL,
	)
	# hybrid first - wins on deduplication (higher quality than autocomplete)
	if run_hybrid:
		coros.append(
			_hybrid_search_memories(
				query_text,
				db,
				principal=principal,
				limit=limit + 1,
				search_params=params,
				query_embedding=query_embedding,
			)
		)
	if run_autocomplete:
		coros.append(
			_autocomplete_memories(query_text, db, principal=principal, limit=limit + 1)
		)
	results = await asyncio.gather(*coros, return_exceptions=True)
	items = vectorstore_service.merge_deduplicate(
		results, limit + 1, resource_name="memories"
	)
	if cursor:
		ts, cid = decode_cursor(cursor)
		_sk = MEMORY_SPEC.sort_key
		items = [i for i in items if (getattr(i, _sk), str(i.id)) < (ts, cid)]
	_sk = MEMORY_SPEC.sort_key
	items.sort(key=lambda r: (getattr(r, _sk), str(r.id)), reverse=True)
	return build_cursor_page(items, limit, sort_key=MEMORY_SPEC.sort_key)


async def query_relevant_memories(
	query_text: str,
	db: AsyncSession,
	principal: Principal,
	limit: int = 10,
	score_threshold: float = 0.0,
	query_embedding: list[float] | None = None,
) -> list[Memory]:
	"""hybrid search returning full Memory objects in relevance order.

	intended for internal consumers (filters, tools) that need full
	memory content rather than the truncated SearchResultItem used by
	UI search endpoints.

	args:
		query_text: natural-language search text.
		db: async database session.
		principal: authenticated user.
		limit: max memories to return.
		score_threshold: minimum normalized score (0-1). results below
			this threshold are dropped.
		query_embedding: pre-computed embedding vector. when provided
			the function skips the embed_text call and uses this directly.

	returns:
		full Memory objects ordered by relevance (best first).
	"""
	query_emb = query_embedding or await embed_text(text=query_text, session=db)
	query_filter = vectorstore_service.resource_types_filter(
		[VectorChunkResourceType.MEMORY],
		owner_id=(str(principal.user.id) if not principal.is_admin else None),
	)
	results = await vectorstore_service.search(
		session=db,
		query=query_emb,
		text_query=query_text,
		limit=limit,
		query_filter=query_filter,
		normalize=True,
	)
	if not results:
		return []

	# apply score threshold.
	results = [r for r in results if r.score >= score_threshold]
	if not results:
		return []

	# fetch full Memory objects.
	resource_ids: list[str] = [str(r.metadata["resource_id"]) for r in results]
	stmt = select(Memory).where(Memory.id.in_(resource_ids))
	if not principal.is_admin:
		stmt = stmt.where(Memory.user_id == principal.user.id)
	db_result = await db.execute(stmt)
	by_id = {str(m.id): m for m in db_result.scalars().all()}

	# preserve relevance order from vector search.
	return [by_id[rid] for rid in resource_ids if rid in by_id]


async def post_process_relevant_memories(
	query_text: str,
	session: AsyncSession,
	principal: Principal,
	max_related_memories: int = 10,
	conversation_snapshot: str | None = None,
	progress_callback: MemoryPostProcessingProgress | None = None,
) -> JSONObject:
	"""create/update/delete memories from the latest conversation context."""
	query = _truncate_post_processing_text(
		query_text,
		MEMORY_POST_PROCESSING_QUERY_MAX_CHARS,
	)
	if not query:
		return {"skipped": True, "reason": "empty query"}
	conversation = _truncate_post_processing_text(
		conversation_snapshot or query_text,
		MEMORY_POST_PROCESSING_QUERY_MAX_CHARS,
	)

	try:
		await _notify_memory_post_processing_progress(
			progress_callback,
			15,
			"embedding memory query",
		)
		query_embedding = await _run_memory_stage(
			"embedding memory query",
			MEMORY_POST_PROCESSING_EMBED_TIMEOUT_SECONDS,
			embed_text(text=query, session=session),
		)
		await _notify_memory_post_processing_progress(
			progress_callback,
			30,
			"searching relevant memories",
		)
		memories = await _run_memory_stage(
			"searching relevant memories",
			MEMORY_POST_PROCESSING_SEARCH_TIMEOUT_SECONDS,
			query_relevant_memories(
				query,
				session,
				principal=principal,
				limit=max_related_memories,
				query_embedding=query_embedding,
			),
		)
	except _MemoryPostProcessingTimeoutError as exc:
		logger.warning(
			"memory post-processing skipped after timeout stage=%s error=%s",
			exc.stage,
			exc.cause_type,
		)
		return exc.to_result()

	await _notify_memory_post_processing_progress(
		progress_callback,
		45,
		"resolving memory model",
	)
	try:
		chat_model = await resolve_task_chat_model(session, "memory_post_processing")
	except ValueError:
		logger.debug("memory post-processing skipped: no task model configured")
		return {"skipped": True, "reason": "no model"}

	memory_entries: list[dict[str, object]] = []
	for memory in memories:
		memory_entries.append(
			{
				"id": str(memory.id),
				"content": _truncate_post_processing_text(
					memory.content,
					MEMORY_POST_PROCESSING_MEMORY_MAX_CHARS,
				),
				"tags": list(memory.tags) if memory.tags else [],
				"created_at": memory.created_at.isoformat()
				if memory.created_at
				else "",
				"updated_at": memory.updated_at.isoformat()
				if memory.updated_at
				else "",
			}
		)

	await _notify_memory_post_processing_progress(
		progress_callback,
		60,
		"running memory model",
	)
	try:
		raw = await _run_memory_stage(
			"running memory model",
			MEMORY_POST_PROCESSING_MODEL_TIMEOUT_SECONDS,
			run_chat_model_json_schema(
				chat_model,
				thread=SDKThread(
					messages=[
						SystemMessage.from_text(_POST_PROCESSING_PROMPT),
						UserMessage.from_text(
							"recent conversation:\n"
							f"{conversation}\n\nrelated memories:\n"
							f"{json.dumps(memory_entries, ensure_ascii=False)}"
						),
					]
				),
				json_schema=_MemoryPostProcessingResponse.model_json_schema(),
				purpose="memory_post_processing",
			),
		)
	except _MemoryPostProcessingTimeoutError as exc:
		logger.warning(
			"memory post-processing skipped after timeout stage=%s error=%s",
			exc.stage,
			exc.cause_type,
		)
		return exc.to_result()
	result = _MemoryPostProcessingResponse.model_validate(raw)
	if not result.actions:
		return {"actions": 0, "created": 0, "updated": 0, "deleted": 0}

	await _notify_memory_post_processing_progress(
		progress_callback,
		80,
		"applying memory actions",
	)
	memory_ids = {str(memory.id) for memory in memories}
	created = 0
	updated = 0
	deleted = 0
	for action in result.actions:
		if action.action == "add":
			content = (action.content or "").strip()
			if not content:
				continue
			await create_memory(
				MemoryCreate(
					content=content,
					tags=action.tags or None,
					user_id=TypeID(principal.user.id),
				),
				session,
				principal,
			)
			created += 1
			continue
		if action.id is None or action.id not in memory_ids:
			logger.warning(
				"post-processing: unknown memory id %s for user %s",
				action.id,
				principal.user_id,
			)
			continue
		memory_id = TypeID(action.id)
		if action.action == "update" and action.new_content:
			await update_memory(
				memory_id,
				MemoryUpdate(content=action.new_content),
				session,
				principal,
			)
			updated += 1
		elif action.action == "delete":
			await delete_memory(memory_id, session, principal)
			deleted += 1

	await session.commit()
	return {
		"actions": len(result.actions),
		"created": created,
		"updated": updated,
		"deleted": deleted,
	}
