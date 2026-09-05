"""service layer for memory operations."""

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

from api.database.main import session_scope
from api.models.event import Event, EventScope
from api.models.event_types import EventType
from api.models.memory import Memory
from api.models.task import Task, TaskType
from api.permissions import ActionPermission, ResourceType
from api.schemas.memory import (
	Memory as MemoryOut,
)
from api.schemas.memory import (
	MemoryCreate,
	MemoryListFilters,
	MemorySearchFilters,
	MemoryUpdate,
)
from api.schemas.search import (
	SearchMode,
	SearchParams,
)
from api.settings import settings as app_settings
from api.v1.service.authentication import Principal
from api.v1.service.authorization import (
	apply_metadata_write,
	apply_resource_access_list_filters,
	list_accessible_user_ids_for_resources,
	project_private,
	require_permission,
	resource_access_predicate,
	vector_acl_filter,
)
from api.v1.service.chat.models import (
	resolve_task_chat_model,
	run_chat_model_json_schema,
)
from api.v1.service.embeddings import embed_text
from api.v1.service.events import persist_and_fanout_event
from api.v1.service.listing import SortDir, apply_sort
from api.v1.service.search.primitives import ScoredResult, merge_scored
from api.v1.service.tasks import start_task
from api.v1.service.vectorize import (
	VectorSpec,
	remove_vectorized_resource,
	vectorize_resource,
	vectorize_resources,
)
from api.v1.service.vectorstores import (
	FieldCondition,
	FieldMatch,
	FieldMatchAny,
	VectorChunkResourceType,
	resource_types_filter,
	search,
	with_conditions,
)
from api.v1.service.vectorstores import (
	delete as delete_vectors,
)
from nokodo_ai.messages import SystemMessage, UserMessage
from nokodo_ai.threads import Thread as SDKThread
from nokodo_ai.types.json import JSONObject, JSONValue
from nokodo_ai.utils.search import contains_pattern
from nokodo_ai.utils.typeid import TypeID


logger = logging.getLogger(__name__)

MEMORY_POST_PROCESSING_TASK = "memory.post_process"
MEMORY_POST_PROCESSING_QUERY_MAX_CHARS = 4000
MEMORY_POST_PROCESSING_MEMORY_MAX_CHARS = 1200
MEMORY_POST_PROCESSING_EMBED_TIMEOUT_SECONDS = 45
MEMORY_POST_PROCESSING_SEARCH_TIMEOUT_SECONDS = 20
MEMORY_POST_PROCESSING_MODEL_TIMEOUT_SECONDS = 60


DEFAULT_POST_PROCESSING_PROMPT = """\
You are the curator of a user's long-term memory store.
You are called after every turn in a conversation between a User and an Assistant.

You will be provided with:
1. The most recent conversation turns (negative indices; -1 is the most
   recent overall message).
2. Existing memories semantically related to that conversation, ordered by
   relevance (most relevant first).

Your task is to determine what actions to take on the memory collection
based on the user's **latest** message.

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
5. Capture anything the **user says about themselves** that is valuable for
	personalizing future interactions.
6. Always **honor direct memory requests from the user** ("remember this",
	"forget that"). Treat these as strong signals to store, update, or delete.
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
11. The user is the ONLY source of new memory facts. Never create a memory from
	anything stated only by the assistant, including tool outcomes, retrieved
	context, recalled knowledge, assumptions, or facts in an answer. Assistant
	text may only help interpret what the user said.
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
- Questions or things the user was merely curious about (a question is not a fact)
- Things the user learned or was told during the conversation
- Tool or web-search outcomes and world facts from the assistant's answer (part
  of the conversation, not durable facts about the user)
- Anything stated only by the assistant, even when it sounds personal or
	references the user; only facts stated by the user can become new memories
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
**Example 1 - Nothing to store (questions, curiosity, and recaps are not facts)**
Conversation:
-2. user: How do JWT refresh tokens work?
-1. assistant: Great question! Since I know you're building an app with JWT \
authentication, this will be helpful :)
So here's how it works: a refresh token lets you get a new access token \
without re-authenticating...
Related Memories:
[{"id": "memory_301", "created_at": "2025-11-03T10:00:00",
  "content": "User is building a new app, starting from the backend"},
 {"id": "memory_302", "created_at": "2025-11-04T18:20:00",
  "content": "User started coding in november 2025"}]
Output:
{"actions": []}

**Example 2 - Clean up: break down bloated memories and delete junk**
Conversation:
-2. user: ok let's keep going
-1. assistant: Sounds good - I'm ready when you are.
Related Memories:
[{"id": "memory_401", "created_at": "2025-10-01T08:00:00",
  "content": "User is a backend developer who lives in Lisbon, drives a Tesla \
Model 3, is allergic to peanuts, and is learning Portuguese"},
 {"id": "memory_402", "created_at": "2025-11-05T14:00:00",
  "content": "User is interested in how JWTs work and has asked exactly what \
it takes to integrate them into his new app project"},
 {"id": "memory_403", "created_at": "2025-11-06T09:30:00",
  "content": "User asked how to center a div in CSS"},
 {"id": "memory_404", "created_at": "2025-11-07T16:00:00",
  "content": "User wanted a summary of a paper about transformer models"},
 {"id": "memory_405", "created_at": "2025-09-12T08:00:00",
  "content": "User enjoys rock climbing and also plays piano on weekends"}]
Output:
{
  "actions": [
    {"action": "update", "id": "memory_401",
     "new_content": "User is a backend developer"},
    {"action": "add", "content": "User lives in Lisbon", "tags": ["location"]},
    {"action": "add", "content": "User drives a Tesla Model 3", "tags": \
["possessions"]},
    {"action": "add", "content": "User is allergic to peanuts", "tags": \
["health"]},
    {"action": "add", "content": "User is learning Portuguese", "tags": \
["learning"]},
    {"action": "delete", "id": "memory_402"},
    {"action": "delete", "id": "memory_403"},
    {"action": "delete", "id": "memory_404"},
    {"action": "update", "id": "memory_405",
     "new_content": "User enjoys rock climbing"},
    {"action": "add", "content": "User plays piano on weekends", "tags": \
["hobbies"]}
  ]
}

**Example 3 - Only store facts if stated by the user in their LAST message**
Conversation:
-4. user: yeah, I really do love BBQ sauce lol
-3. assistant: haha, I know! you love everything to with BBQ to be fair
-2. user: wow... you really do know me well! then what are my favorite foods, huh?
-1. assistant: hmm... let me think
[called recall_memories tool 5 times]
so... you LOVE BBQ sauce, you love spicy food, and you love chocolate. \
those are your top 3 favorite foods!
Related Memories: []
Output:
{"actions": []}

**Example 4 - Add new, distinct facts**
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

**Example 5 - Update on changed preference**
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
     "new_content": "User prefers TypeScript for frontend projects"}
  ]
}

**Example 6 - Delete on negation / sarcasm**
Conversation:
-2. user: I'm joking! I didn't actually buy the iPhone!
-1. assistant: Ahh, you got me! No worries.
Related Memories:
[{"id": "memory_xyz", "created_at": "2024-03-01T09:00:00",
  "content": "User just bought a new iPhone"}]
Output:
{"actions": [{"action": "delete", "id": "memory_xyz"}]}

**Example 7 - Normalize a name reference**
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

**Example 8 - Passive maintenance: dedupe and merge**
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
"""default system prompt for the memory post-processing maintenance agent."""


type MemoryPostProcessingProgress = Callable[[int, str], Awaitable[None]]


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


def memory_payloads(memories: list[Memory], principal: Principal) -> list[MemoryOut]:
	"""project memory rows to their API payloads for the principal."""
	return project_private(
		principal,
		ResourceType.MEMORY,
		[MemoryOut.from_row(memory) for memory in memories],
	)


async def _get_memory(
	memory_id: TypeID,
	session: AsyncSession,
	principal: Principal,
) -> Memory:
	stmt = select(Memory).where(Memory.id == memory_id)
	# operator is the platform's answer to cross-user visibility; a raw
	# is_superuser check here would 404 for an operator that the listing
	# predicate happily shows.
	if not principal.is_resource_operator(ResourceType.MEMORY):
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
	require_permission(principal, ActionPermission.MEMORIES_CREATE)
	data = memory_in.model_dump(exclude={"metadata"})
	if not principal.user.is_superuser:
		data["user_id"] = principal.user.id
	memory = Memory(**data)
	apply_metadata_write(memory, memory_in.metadata)
	session.add(memory)
	await session.flush()
	await session.refresh(memory)
	memory_id = memory.id
	event = Event(
		scope=EventScope.USER,
		scope_id=principal.user.id,
		type=EventType.MEMORY_CREATED,
		data={"id": str(memory_id)},
		user_id=principal.user.id,
	)
	await persist_and_fanout_event(
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
	stmt = stmt.where(resource_access_predicate(principal, ResourceType.MEMORY))
	if filters.owner_id is not None:
		stmt = stmt.where(Memory.user_id == filters.owner_id)
	if filters.search:
		stmt = stmt.where(
			Memory.content.ilike(contains_pattern(filters.search), escape="\\")
		)
	if filters.tags:
		stmt = stmt.where(Memory.tags.op("&&")(filters.tags))
	return apply_resource_access_list_filters(
		stmt,
		principal,
		ResourceType.MEMORY,
		filters.access_relationship,
		filters.resolved_access_level,
	)


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

	update_data = memory_in.model_dump(exclude_unset=True, exclude={"metadata"})
	for key, value in update_data.items():
		setattr(memory, key, value)
	apply_metadata_write(memory, memory_in.metadata)

	event = Event(
		scope=EventScope.USER,
		scope_id=principal.user.id,
		type=EventType.MEMORY_UPDATED,
		data={"id": str(memory_id)},
		user_id=principal.user.id,
	)
	await persist_and_fanout_event(
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
	delete_recipients = await list_accessible_user_ids_for_resources(
		[(ResourceType.MEMORY, memory_id)], session
	)

	await session.delete(memory)

	event = Event(
		scope=EventScope.USER,
		scope_id=principal.user.id,
		type=EventType.MEMORY_DELETED,
		data={"id": str(memory_id)},
		user_id=principal.user.id,
	)
	await persist_and_fanout_event(
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
		scope_id=principal.user.id,
		type=EventType.MEMORY_DELETED,
		data={"all": True, "user_id": str(user_id)},
		user_id=principal.user.id,
	)
	await persist_and_fanout_event(
		session,
		event=event,
		origin_session_id=origin_session_id,
	)

	await delete_vectors(
		target=resource_types_filter(
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
)


async def vectorize_memories(
	session: AsyncSession,
	ids: list[TypeID] | None = None,
) -> int:
	"""vectorize memory points; ids=None means every memory. returns count."""
	if ids is not None and not ids:
		return 0
	stmt = select(Memory)
	if ids is not None:
		stmt = stmt.where(Memory.id.in_([str(mid) for mid in ids]))
	result = await session.execute(stmt)
	return await vectorize_resources(
		spec=MEMORY_SPEC, resources=list(result.scalars().all()), session=session
	)


def _memory_search_conditions(
	filters: MemorySearchFilters | None,
) -> list[FieldCondition]:
	"""vector-layer narrowing conditions derived from memory search filters."""
	conditions: list[FieldCondition] = []
	if filters is None:
		return conditions
	if filters.owner_id is not None:
		conditions.append(FieldMatch(key="owner_id", value=str(filters.owner_id)))
	if filters.tags:
		conditions.append(FieldMatchAny(key="tags", values=filters.tags))
	return conditions


def _apply_memory_search_filters(
	stmt: Select,
	filters: MemorySearchFilters | None,
) -> Select:
	"""SQL-layer narrowing mirroring _memory_search_conditions."""
	if filters is None:
		return stmt
	if filters.owner_id is not None:
		stmt = stmt.where(Memory.user_id == filters.owner_id)
	if filters.tags:
		stmt = stmt.where(Memory.tags.op("&&")(filters.tags))
	return stmt


async def _autocomplete_memories(
	q: str,
	db: AsyncSession,
	principal: Principal,
	limit: int = 5,
	offset: int = 0,
	filters: MemorySearchFilters | None = None,
) -> list[ScoredResult[Memory]]:
	"""pg_trgm autocomplete tier for memories, scored by content similarity."""
	pattern = contains_pattern(q)
	sim = func.word_similarity(q, Memory.content)
	stmt = (
		select(Memory, sim.label("sim"))
		.where(
			or_(
				sim > 0.1,
				Memory.content.ilike(pattern, escape="\\"),
			),
		)
		.where(resource_access_predicate(principal, ResourceType.MEMORY))
		.order_by(sim.desc())
		.offset(offset)
		.limit(limit)
	)
	stmt = _apply_memory_search_filters(stmt, filters)
	result = await db.execute(stmt)
	return [ScoredResult(item=mem, score=float(score)) for mem, score in result.all()]


async def _hybrid_search_memories(
	query_text: str,
	db: AsyncSession,
	principal: Principal,
	limit: int = 10,
	search_params: SearchParams | None = None,
	query_embedding: list[float] | None = None,
	filters: MemorySearchFilters | None = None,
) -> list[ScoredResult[Memory]]:
	"""qdrant hybrid tier for memories (dense + BM25), scored by fused rank."""
	params = search_params or SearchParams()
	need_dense = params.mode in (SearchMode.DENSE, SearchMode.HYBRID, SearchMode.FULL)
	need_sparse = params.mode in (SearchMode.SPARSE, SearchMode.HYBRID, SearchMode.FULL)
	query_emb = (
		query_embedding
		if query_embedding is not None
		else (
			await embed_text(text=query_text, session=db, input_type="query")
			if need_dense
			else None
		)
	)
	text_query = query_text if need_sparse else None
	# ACL prefilter (owner + admin handled inside), narrowed by search filters.
	query_filter = with_conditions(
		vector_acl_filter([VectorChunkResourceType.MEMORY], principal),
		_memory_search_conditions(filters),
	)
	results = await search(
		session=db,
		query=query_emb,
		text_query=text_query,
		limit=limit,
		query_filter=query_filter,
		normalize=params.normalize,
		group_by="resource_id",
	)
	if not results:
		return []
	resource_ids: list[str] = [str(r.metadata["resource_id"]) for r in results]
	stmt = select(Memory).where(
		Memory.id.in_(resource_ids),
		resource_access_predicate(principal, ResourceType.MEMORY),
	)
	stmt = _apply_memory_search_filters(stmt, filters)
	db_result = await db.execute(stmt)
	by_id = {str(m.id): m for m in db_result.scalars().all()}
	scored: list[ScoredResult[Memory]] = []
	for r in results:
		mem = by_id.get(str(r.metadata["resource_id"]))
		if mem is None:
			continue
		scored.append(ScoredResult(item=mem, score=r.score))
	return scored


async def search_memories(
	query_text: str,
	db: AsyncSession,
	principal: Principal,
	limit: int = 10,
	offset: int = 0,
	search_params: SearchParams | None = None,
	query_embedding: list[float] | None = None,
	filters: MemorySearchFilters | None = None,
	score_threshold: float = 0.0,
) -> list[ScoredResult[Memory]]:
	"""relevance-ordered, deduped memory hits with internal scores.

	hybrid tier ranks first; autocomplete-only matches are appended.
	"""
	params = search_params or SearchParams()
	if params.mode == SearchMode.AUTOCOMPLETE:
		return await _autocomplete_memories(
			query_text,
			db,
			principal=principal,
			limit=limit,
			offset=offset,
			filters=filters,
		)
	fetch = offset + limit
	coros: list[Coroutine[None, None, list[ScoredResult[Memory]]]] = []
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

	async def _run_hybrid() -> list[ScoredResult[Memory]]:
		async with session_scope(None) as s:
			return await _hybrid_search_memories(
				query_text,
				s,
				principal=principal,
				limit=fetch,
				search_params=params,
				query_embedding=query_embedding,
				filters=filters,
			)

	async def _run_autocomplete() -> list[ScoredResult[Memory]]:
		async with session_scope(None) as s:
			return await _autocomplete_memories(
				query_text,
				s,
				principal=principal,
				limit=fetch,
				filters=filters,
			)

	# hybrid first - wins on deduplication (higher quality than autocomplete)
	if run_hybrid:
		coros.append(_run_hybrid())
	if run_autocomplete:
		coros.append(_run_autocomplete())
	results = await asyncio.gather(*coros, return_exceptions=True)
	merged = merge_scored(results, resource_name="memories")
	if score_threshold > 0.0:
		merged = [s for s in merged if s.score >= score_threshold]
	return merged[offset : offset + limit]


async def post_process_relevant_memories(
	query_text: str,
	session: AsyncSession,
	principal: Principal,
	max_related_memories: int = 10,
	conversation_snapshot: str | None = None,
	progress_callback: MemoryPostProcessingProgress | None = None,
	source_message_id: str | None = None,
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
			embed_text(text=query, session=session, input_type="query"),
		)
		await _notify_memory_post_processing_progress(
			progress_callback,
			30,
			"searching relevant memories",
		)
		memories_scored = await _run_memory_stage(
			"searching relevant memories",
			MEMORY_POST_PROCESSING_SEARCH_TIMEOUT_SECONDS,
			search_memories(
				query,
				session,
				principal=principal,
				limit=max_related_memories,
				search_params=SearchParams(mode=SearchMode.HYBRID),
				query_embedding=query_embedding,
				filters=MemorySearchFilters(owner_id=principal.user.id),
			),
		)
		memories = [s.item for s in memories_scored]
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
	system_prompt = (
		app_settings.ai.memory.post_processing_prompt or DEFAULT_POST_PROCESSING_PROMPT
	)
	try:
		raw = await _run_memory_stage(
			"running memory model",
			MEMORY_POST_PROCESSING_MODEL_TIMEOUT_SECONDS,
			run_chat_model_json_schema(
				chat_model,
				thread=SDKThread(
					messages=[
						SystemMessage.from_text(system_prompt),
						UserMessage.from_text(
							"recent conversation:\n"
							f"{conversation}\n\nrelated memories:\n"
							f"{json.dumps(memory_entries, ensure_ascii=False)}"
						),
					]
				),
				json_schema=_MemoryPostProcessingResponse.model_json_schema(),
				purpose="memory_post_processing",
				reasoning_effort=app_settings.ai.memory.post_processing_reasoning_effort,
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
					source_message_id=TypeID(source_message_id)
					if source_message_id
					else None,
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
				principal.user.id,
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


async def start_memory_post_processing_task(
	session: AsyncSession,
	principal: Principal,
	query_text: str,
	max_related_memories: int,
	conversation_snapshot: str | None = None,
	thread_id: str | None = None,
	message_id: str | None = None,
	message_ref: str | None = None,
	run_id: str | None = None,
	emit_activity: bool = False,
) -> Task:
	"""enqueue durable memory maintenance for a conversation query."""
	runtime: JSONObject = {
		"query_text": query_text,
		"max_related_memories": max_related_memories,
		"conversation_snapshot": conversation_snapshot,
		"thread_id": thread_id,
		"message_id": message_id,
		"message_ref": message_ref,
		"run_id": run_id,
		"emit_activity": emit_activity,
	}
	return await start_task(
		session,
		principal,
		task_type=TaskType.CUSTOM,
		task_name=MEMORY_POST_PROCESSING_TASK,
		metadata={"query_length": len(query_text)},
		runtime=runtime,
		stage="queued memory processing",
		progress=0,
	)
