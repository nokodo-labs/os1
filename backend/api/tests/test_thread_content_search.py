"""tests for thread content vectors and message-level search."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.message import Message, MessageType
from api.models.model import Model
from api.models.provider import Provider
from api.models.thread import Thread
from api.models.thread_passage import ThreadPassage
from api.models.user import User
from api.permissions import DefaultResourceAccess
from api.schemas.search import SearchMode, SearchParams
from api.schemas.thread import ThreadSearchFilters
from api.settings import settings
from api.tests.factories import reconcile_one_thread
from api.tests.mocks import patch_vectorstore_ops
from api.v1.service.authentication import Principal
from api.v1.service.threads import content_vectors as content_vectors_service
from api.v1.service.threads import core as thread_service
from api.v1.service.threads.content_vectors import (
	ANCHOR_MESSAGE_ID_KEY,
	CONTENT_VECTORS_BUILT_AT_KEY,
	CONTENT_VECTORS_COLLECTION_KEY,
	CONTENT_VECTORS_CONFIG_KEY,
	CONTENT_VECTORS_SCHEMA_KEY,
	ENRICHMENT_KEY,
	THREAD_CONTENT_PIPELINE_VERSION,
	content_vectors_due_predicate,
	content_vectors_stale_predicate,
	purge_thread_content_vectors,
	thread_passages_config_fp,
)
from api.v1.service.threads.passages import list_passages
from api.v1.service.threads.search import (
	_autocomplete_messages,
	_hybrid_search_threads,
)
from api.v1.service.threads.tree import active_branch_message_ids
from api.v1.service.vectorize import StaleBy
from nokodo_ai.adapters.base.vectorstores import (
	Chunk,
	ChunkFilter,
	ChunkSearchResult,
	FieldMatch,
	FieldMatchAny,
)
from nokodo_ai.messages import SystemMessage
from nokodo_ai.threads import Thread as SDKThread
from nokodo_ai.utils.security import hash_password


_SPARSE = SearchParams(mode=SearchMode.SPARSE)


@pytest.fixture(autouse=True)
def _stub_passage_embedding_capacity(monkeypatch: pytest.MonkeyPatch) -> None:
	async def _capacity(session: object = None) -> int:
		return 8192

	monkeypatch.setattr(
		content_vectors_service,
		"embedding_token_capacity",
		_capacity,
	)


def _uid() -> str:
	return uuid4().hex[:8]


def _user(suffix: str) -> User:
	return User(
		email=f"{suffix}@tcs.test",
		username=f"tcs_{suffix}",
		hashed_password=hash_password("x"),
		is_active=True,
	)


def _principal(user: User) -> Principal:
	return Principal.for_user(
		user=user,
		group_ids=(),
		permissions=frozenset(),
		role_resource_defaults=DefaultResourceAccess(),
	)


def _message(
	thread: Thread,
	parent: Message | None,
	mtype: MessageType,
	text: str,
) -> Message:
	message_cls = Message.__mapper__.polymorphic_map[mtype].class_
	return message_cls(
		thread_id=thread.id,
		parent_id=parent.id if parent is not None else None,
		content=[{"type": "text", "text": text}],
	)


async def _linear_thread(
	db_session: AsyncSession,
	owner: User,
	texts: list[tuple[MessageType, str]],
	title: str = "test thread",
) -> tuple[Thread, list[Message]]:
	thread = Thread(owner_id=owner.id, title=title, is_temporary=False)
	db_session.add(thread)
	await db_session.flush()
	messages: list[Message] = []
	parent: Message | None = None
	for mtype, text in texts:
		message = _message(thread, parent, mtype, text)
		db_session.add(message)
		await db_session.flush()
		messages.append(message)
		parent = message
	thread.current_message_id = messages[-1].id if messages else None
	await db_session.commit()
	return thread, messages


class _VectorstoreCapture:
	"""in-memory stand-in for the vectorstore chunk lifecycle."""

	def __init__(self) -> None:
		self.chunks: dict[str, Chunk] = {}
		self.upserted_batches: list[list[Chunk]] = []
		self.collection = "test_collection"

	def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
		async def _scroll(query_filter: object, *args: object, **kwargs: object):
			return list(self.chunks.values())

		async def _upsert(chunks: list[Chunk], *args: object, **kwargs: object):
			self.upserted_batches.append(chunks)
			for chunk in chunks:
				self.chunks[chunk.id] = chunk

		async def _delete(target: object, *args: object, **kwargs: object):
			assert isinstance(target, ChunkFilter)
			matches: dict[str, list[str]] = {}
			for condition in target.all_of:
				if isinstance(condition, FieldMatch):
					matches.setdefault(condition.key, []).append(str(condition.value))
				elif isinstance(condition, FieldMatchAny):
					matches.setdefault(condition.key, []).extend(
						str(v) for v in condition.values
					)

			def _dropped(chunk: Chunk) -> bool:
				for key in ("resource_id", "parent_resource_id"):
					targets = matches.get(key)
					if targets and chunk.metadata.get(key) in targets:
						return True
				# a resource_type-only filter targets the whole tier.
				type_targets = matches.get("resource_type")
				if (
					type_targets
					and not matches.keys() - {"resource_type"}
					and chunk.metadata.get("resource_type") in type_targets
				):
					return True
				return False

			self.chunks = {
				cid: chunk for cid, chunk in self.chunks.items() if not _dropped(chunk)
			}

		async def _collection(session: object = None) -> str:
			return self.collection

		patch_vectorstore_ops(
			monkeypatch,
			scroll_chunks=_scroll,
			upsert_chunks=_upsert,
			delete=_delete,
			get_collection=_collection,
		)

	@property
	def built_count(self) -> int:
		return sum(len(batch) for batch in self.upserted_batches)


@pytest.mark.asyncio
async def test_reconcile_builds_passages_and_is_idempotent(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	s = _uid()
	owner = _user(f"rc_{s}")
	db_session.add(owner)
	await db_session.flush()
	thread, messages = await _linear_thread(
		db_session,
		owner,
		[
			(MessageType.USER, "how do we fix the connection pool exhaustion"),
			(MessageType.ASSISTANT, "switch to pgbouncer with transaction pooling"),
		],
	)
	capture = _VectorstoreCapture()
	capture.install(monkeypatch)

	first = await reconcile_one_thread(thread.id, db_session)
	first_built = first.get("built")
	assert isinstance(first_built, int) and first_built >= 1
	assert capture.built_count == first_built
	stored = list(capture.chunks.values())
	assert stored, "passages must be upserted"
	chunk = stored[0]
	assert chunk.metadata["parent_resource_id"] == str(thread.id)
	assert chunk.metadata[ANCHOR_MESSAGE_ID_KEY] == str(messages[0].id)
	assert chunk.metadata["owner_id"] == str(owner.id)
	passage_rows = await list_passages(thread.id, db_session)
	assert len(passage_rows) == 1
	passage_row = passage_rows[0]
	assert chunk.id == str(passage_row.id)
	assert chunk.metadata["resource_id"] == str(passage_row.id)
	# dense text is title-prefixed, stored content is the raw transcript
	assert "pgbouncer" in chunk.content
	metadata = thread.private_metadata
	assert metadata.get(CONTENT_VECTORS_SCHEMA_KEY) == THREAD_CONTENT_PIPELINE_VERSION
	assert metadata.get(CONTENT_VECTORS_BUILT_AT_KEY) is not None
	assert metadata.get(CONTENT_VECTORS_CONFIG_KEY) == thread_passages_config_fp()

	second = await reconcile_one_thread(thread.id, db_session)
	assert second["built"] == 0
	assert capture.built_count == first_built, "no re-embeds on unchanged thread"


@pytest.mark.asyncio
async def test_reconcile_rebuilds_changed_and_deletes_orphans(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	s = _uid()
	owner = _user(f"ro_{s}")
	db_session.add(owner)
	await db_session.flush()
	thread, messages = await _linear_thread(
		db_session,
		owner,
		[
			(MessageType.USER, "original question about kubernetes"),
			(MessageType.ASSISTANT, "original answer about pods"),
		],
	)
	capture = _VectorstoreCapture()
	capture.install(monkeypatch)
	await reconcile_one_thread(thread.id, db_session)
	old_ids = {chunk.metadata["resource_id"] for chunk in capture.chunks.values()}
	assert old_ids

	rows_before = await list_passages(thread.id, db_session)
	assert len(rows_before) == 1
	old_hash = rows_before[0].content_hash
	old_row_id = str(rows_before[0].id)
	rows_before[0].enrichment = "stale enrichment"
	rows_before[0].enriched_at = datetime.now(tz=UTC)
	rows_before[0].enrichment_pipeline_v = 7
	messages[0].content = [{"type": "text", "text": "edited question about docker"}]
	await db_session.commit()
	result = await reconcile_one_thread(thread.id, db_session)
	result_built = result.get("built")
	assert isinstance(result_built, int) and result_built >= 1
	new_ids = {chunk.metadata["resource_id"] for chunk in capture.chunks.values()}
	assert new_ids
	assert new_ids == old_ids == {old_row_id}
	row_after = await db_session.get(ThreadPassage, old_row_id)
	assert row_after is not None
	assert row_after.content_hash != old_hash
	assert row_after.enrichment is None
	assert row_after.enrichment_model_id is None
	assert row_after.enriched_at is None
	assert row_after.enrichment_pipeline_v is None


@pytest.mark.asyncio
async def test_reconcile_culls_replaced_spans(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	s = _uid()
	owner = _user(f"cull_{s}")
	db_session.add(owner)
	await db_session.flush()
	thread, messages = await _linear_thread(
		db_session,
		owner,
		[
			(MessageType.USER, "initial deployment question"),
			(MessageType.ASSISTANT, "initial deployment answer"),
		],
	)
	capture = _VectorstoreCapture()
	capture.install(monkeypatch)
	await reconcile_one_thread(thread.id, db_session)
	old_rows = await list_passages(thread.id, db_session)
	assert len(old_rows) == 1
	old_row_id = str(old_rows[0].id)

	appended = _message(
		thread,
		messages[-1],
		MessageType.USER,
		"follow-up that replaces the previous terminal span",
	)
	db_session.add(appended)
	await db_session.flush()
	thread.current_message_id = appended.id
	thread.last_activity_at = datetime.now(tz=UTC)
	await db_session.commit()

	result = await reconcile_one_thread(thread.id, db_session)
	assert result["deleted"] == 1
	assert await db_session.get(ThreadPassage, old_row_id) is None
	assert all(
		chunk.metadata["resource_id"] != old_row_id for chunk in capture.chunks.values()
	)


@pytest.mark.asyncio
async def test_reconcile_culls_vectors_after_message_hard_delete(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	s = _uid()
	owner = _user(f"hard_delete_{s}")
	db_session.add(owner)
	await db_session.flush()
	thread, messages = await _linear_thread(
		db_session,
		owner,
		[
			(MessageType.USER, "question that remains"),
			(MessageType.ASSISTANT, "answer that will be hard deleted"),
		],
	)
	capture = _VectorstoreCapture()
	capture.install(monkeypatch)
	await reconcile_one_thread(thread.id, db_session)
	old_passages = await list_passages(thread.id, db_session)
	assert len(old_passages) == 1
	old_passage_id = str(old_passages[0].id)

	thread.current_message_id = messages[0].id
	thread.last_activity_at = datetime.now(tz=UTC)
	await db_session.execute(delete(Message).where(Message.id == messages[-1].id))
	await db_session.commit()
	remaining_id = (
		await db_session.execute(
			select(ThreadPassage.id).where(ThreadPassage.id == old_passage_id)
		)
	).scalar_one_or_none()
	assert remaining_id is None

	result = await reconcile_one_thread(thread.id, db_session)
	assert result["deleted"] == 1
	assert all(
		chunk.metadata["resource_id"] != old_passage_id
		for chunk in capture.chunks.values()
	)


@pytest.mark.asyncio
async def test_reconcile_applies_and_preserves_enrichment(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""enrichment re-embeds the passage and survives later reconciles."""
	s = _uid()
	owner = _user(f"en_{s}")
	db_session.add(owner)
	await db_session.flush()
	thread, _messages = await _linear_thread(
		db_session,
		owner,
		[
			(MessageType.USER, "yeah lets go with the second option"),
			(MessageType.ASSISTANT, "done, switching it over now"),
		],
		title="infra chat",
	)
	capture = _VectorstoreCapture()
	capture.install(monkeypatch)
	await reconcile_one_thread(thread.id, db_session)
	chunk = next(iter(capture.chunks.values()))
	passage_id = chunk.metadata["resource_id"]
	assert isinstance(passage_id, str)
	assert ENRICHMENT_KEY not in chunk.metadata

	blurb = f"discussion about pgbouncer pooling options {s}"
	passage_row = await db_session.get(ThreadPassage, passage_id)
	assert passage_row is not None
	passage_row.enrichment = blurb
	result = await reconcile_one_thread(thread.id, db_session)
	assert result["built"] == 1
	chunk = next(iter(capture.chunks.values()))
	assert chunk.metadata[ENRICHMENT_KEY] == blurb
	assert isinstance(chunk.content, str) and chunk.content.startswith(blurb)

	result = await reconcile_one_thread(thread.id, db_session)
	assert result["built"] == 0
	chunk = next(iter(capture.chunks.values()))
	assert chunk.metadata[ENRICHMENT_KEY] == blurb


@pytest.mark.asyncio
async def test_collection_rebuild_reuses_persisted_enrichment_without_chat(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	from api.v1.service.chat import thread_maintenance

	s = _uid()
	owner = _user(f"disposable_{s}")
	db_session.add(owner)
	await db_session.flush()
	thread, _messages = await _linear_thread(
		db_session,
		owner,
		[
			(MessageType.USER, "choose a postgres pooling strategy"),
			(MessageType.ASSISTANT, "use transaction pooling through pgbouncer"),
		],
	)
	capture = _VectorstoreCapture()
	capture.install(monkeypatch)
	await reconcile_one_thread(thread.id, db_session)
	passages = await list_passages(thread.id, db_session)
	assert len(passages) == 1
	passage = passages[0]
	passage.enrichment = "decision about PostgreSQL connection pooling"
	passage.enriched_at = datetime.now(tz=UTC)
	passage.enrichment_pipeline_v = 1
	await reconcile_one_thread(thread.id, db_session)

	async def _unexpected_chat_call(*args: object, **kwargs: object) -> object:
		raise AssertionError("vector-store rebuild must not call a chat model")

	monkeypatch.setattr(
		thread_maintenance,
		"run_chat_model_json_schema",
		_unexpected_chat_call,
	)
	capture.chunks.clear()
	capture.collection = "replacement_collection"
	result = await reconcile_one_thread(thread.id, db_session)

	assert result["built"] == 1
	rebuilt = next(iter(capture.chunks.values()))
	enrichment = passage.enrichment
	assert enrichment is not None
	assert rebuilt.metadata[ENRICHMENT_KEY] == enrichment
	assert isinstance(rebuilt.content, str)
	assert rebuilt.content.startswith(enrichment)
	assert passage.enriched_at is not None
	assert passage.enrichment_pipeline_v == 1
	assert thread.private_metadata[CONTENT_VECTORS_COLLECTION_KEY] == (
		"replacement_collection"
	)


@pytest.mark.asyncio
async def test_enrich_thread_passages_generates_and_applies(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""the maintenance enrichment pass targets unenriched passages only."""
	from api.v1.service.chat import thread_maintenance

	s = _uid()
	owner = _user(f"ep_{s}")
	db_session.add(owner)
	await db_session.flush()
	thread, _messages = await _linear_thread(
		db_session,
		owner,
		[
			(MessageType.USER, f"how do we scale the ingest pipeline {s}"),
			(MessageType.ASSISTANT, "shard the queue and batch the writes"),
		],
		title="scaling chat",
	)
	capture = _VectorstoreCapture()
	capture.install(monkeypatch)
	await reconcile_one_thread(thread.id, db_session)

	blurb = f"context about queue sharding {s}"
	seen_prompt: str | None = None
	provider = Provider(
		name=f"passage-enrichment-{s}",
		adapter_type="openai",
	)
	db_session.add(provider)
	await db_session.flush()
	model = Model(provider_id=provider.id, name="cheap-enrichment")
	db_session.add(model)
	await db_session.flush()
	model_override = model.id

	async def _fake_structured(
		chat_model: object,
		thread: SDKThread,
		json_schema: dict[str, object],
		purpose: str = "structured_output",
	) -> dict[str, str]:
		nonlocal seen_prompt
		system_message = thread.messages[0]
		assert isinstance(system_message, SystemMessage)
		seen_prompt = system_message.text
		return {"context": blurb}

	async def _fake_model(session: object, task: str) -> object:
		assert session is db_session
		assert task == "passage_enrichment"
		return object()

	monkeypatch.setattr(
		thread_maintenance, "run_chat_model_json_schema", _fake_structured
	)
	monkeypatch.setattr(thread_maintenance, "resolve_task_chat_model", _fake_model)
	monkeypatch.setattr(
		settings.ai.tasks, "passage_enrichment_prompt", "custom enrichment prompt"
	)
	monkeypatch.setattr(
		settings.ai.tasks,
		"passage_enrichment_model_id",
		model_override,
	)

	enriched = await thread_maintenance.enrich_thread_passages(thread.id, db_session)
	assert enriched == 1
	assert seen_prompt == "custom enrichment prompt"
	chunk = next(iter(capture.chunks.values()))
	assert chunk.metadata[ENRICHMENT_KEY] == blurb
	passage = await db_session.get(ThreadPassage, chunk.metadata["resource_id"])
	assert passage is not None
	assert passage.enrichment == blurb
	assert passage.enrichment_model_id == model_override
	assert passage.enriched_at is not None
	assert (
		passage.enrichment_pipeline_v
		== thread_maintenance.PASSAGE_ENRICHMENT_PIPELINE_VERSION
	)

	# second pass finds nothing left to enrich
	enriched = await thread_maintenance.enrich_thread_passages(thread.id, db_session)
	assert enriched == 0


@pytest.mark.asyncio
async def test_disabled_passages_skip_reconcile_and_enrichment(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""the master toggle stops passage persistence and enrichment entirely."""
	from api.v1.service.chat import thread_maintenance

	s = _uid()
	owner = _user(f"off_{s}")
	db_session.add(owner)
	await db_session.flush()
	thread, _messages = await _linear_thread(
		db_session,
		owner,
		[
			(MessageType.USER, "does the toggle stop indexing"),
			(MessageType.ASSISTANT, "it must stop everything"),
		],
	)
	capture = _VectorstoreCapture()
	capture.install(monkeypatch)
	monkeypatch.setattr(settings.assets.thread_passages, "enabled", False)

	result = await reconcile_one_thread(thread.id, db_session)

	assert result["skipped"] is True
	assert capture.chunks == {}
	assert await list_passages(thread.id, db_session) == []
	assert await thread_maintenance.enrich_thread_passages(thread.id, db_session) == 0


@pytest.mark.asyncio
async def test_purge_thread_content_vectors_clears_rows_chunks_and_stamps(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""turning passages off removes rows, vectors, and reconcile stamps."""
	s = _uid()
	owner = _user(f"purge_{s}")
	db_session.add(owner)
	await db_session.flush()
	thread, _messages = await _linear_thread(
		db_session,
		owner,
		[
			(MessageType.USER, "index this transcript"),
			(MessageType.ASSISTANT, "then drop the whole tier"),
		],
	)
	capture = _VectorstoreCapture()
	capture.install(monkeypatch)
	await reconcile_one_thread(thread.id, db_session)
	assert await list_passages(thread.id, db_session)
	assert capture.chunks

	purged = await purge_thread_content_vectors(db_session)

	assert purged >= 1
	assert await list_passages(thread.id, db_session) == []
	assert capture.chunks == {}
	metadata = thread.private_metadata
	assert CONTENT_VECTORS_SCHEMA_KEY not in metadata
	assert CONTENT_VECTORS_COLLECTION_KEY not in metadata


@pytest.mark.asyncio
async def test_delete_thread_purges_passage_vectors(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""deleting a thread drops its passage tier, not just the thread point.

	passage chunks are keyed by their own resource_id, so the thread-point
	removal never matches them: without an explicit purge they outlive the
	thread and waste overfetch slots at search time.
	"""
	s = _uid()
	owner = _user(f"del_{s}")
	db_session.add(owner)
	await db_session.flush()
	thread, _messages = await _linear_thread(
		db_session,
		owner,
		[
			(MessageType.USER, "this transcript must not outlive the thread"),
			(MessageType.ASSISTANT, "agreed, purge it on delete"),
		],
	)
	capture = _VectorstoreCapture()
	capture.install(monkeypatch)
	await reconcile_one_thread(thread.id, db_session)
	assert capture.chunks
	assert await list_passages(thread.id, db_session)

	await thread_service.delete_thread(
		thread.id,
		db_session,
		principal=_principal(owner),
	)

	assert capture.chunks == {}
	assert await list_passages(thread.id, db_session) == []


@pytest.mark.asyncio
async def test_restore_thread_rebuilds_passage_vectors(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""restore rebuilds the passage tier that delete purged."""
	s = _uid()
	owner = _user(f"res_{s}")
	owner.is_superuser = True
	db_session.add(owner)
	await db_session.flush()
	thread, _messages = await _linear_thread(
		db_session,
		owner,
		[(MessageType.USER, "restore must bring the transcript back")],
	)
	capture = _VectorstoreCapture()
	capture.install(monkeypatch)
	principal = _principal(owner)
	await reconcile_one_thread(thread.id, db_session)
	assert capture.chunks

	await thread_service.delete_thread(thread.id, db_session, principal=principal)
	assert capture.chunks == {}

	await thread_service.restore_thread(thread.id, db_session, principal=principal)

	passage_chunks = [
		chunk
		for chunk in capture.chunks.values()
		if chunk.metadata.get("parent_resource_id") == str(thread.id)
	]
	assert passage_chunks
	assert await list_passages(thread.id, db_session)


@pytest.mark.asyncio
async def test_reconcile_purges_temporary_thread(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	s = _uid()
	owner = _user(f"rp_{s}")
	db_session.add(owner)
	await db_session.flush()
	thread = Thread(owner_id=owner.id, title=f"temp_{s}", is_temporary=True)
	db_session.add(thread)
	await db_session.commit()
	capture = _VectorstoreCapture()
	capture.install(monkeypatch)
	result = await reconcile_one_thread(thread.id, db_session)
	assert result.get("purged") is True
	assert capture.chunks == {}


@pytest.mark.asyncio
async def test_reconcile_rejects_passages_larger_than_embedding_capacity(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	s = _uid()
	owner = _user(f"cap_{s}")
	db_session.add(owner)
	await db_session.flush()
	thread, _messages = await _linear_thread(
		db_session,
		owner,
		[(MessageType.USER, "capacity guard")],
	)
	capture = _VectorstoreCapture()
	capture.install(monkeypatch)
	monkeypatch.setattr(settings.assets.thread_passages, "target_tokens", 2000)

	async def _capacity(session: object = None) -> int:
		return 1000

	monkeypatch.setattr(
		content_vectors_service,
		"embedding_token_capacity",
		_capacity,
	)
	with pytest.raises(ValueError, match="target_tokens.*exceeds"):
		await reconcile_one_thread(thread.id, db_session)


@pytest.mark.asyncio
async def test_active_branch_message_ids_walks_only_active_path(
	db_session: AsyncSession,
) -> None:
	s = _uid()
	owner = _user(f"ab_{s}")
	db_session.add(owner)
	await db_session.flush()
	thread = Thread(owner_id=owner.id, title=f"branchy_{s}", is_temporary=False)
	db_session.add(thread)
	await db_session.flush()
	m1 = _message(thread, None, MessageType.USER, "root question")
	db_session.add(m1)
	await db_session.flush()
	m2a = _message(thread, m1, MessageType.ASSISTANT, "first answer")
	db_session.add(m2a)
	await db_session.flush()
	m2b = _message(thread, m1, MessageType.ASSISTANT, "regenerated answer")
	db_session.add(m2b)
	await db_session.flush()
	thread.current_message_id = m2b.id
	await db_session.commit()

	branches = await active_branch_message_ids(db_session, [str(thread.id)])
	active = branches[str(thread.id)]
	assert str(m1.id) in active
	assert str(m2b.id) in active
	assert str(m2a.id) not in active


@pytest.mark.asyncio
async def test_message_autocomplete_returns_anchor_and_respects_branch(
	db_session: AsyncSession,
) -> None:
	s = _uid()
	owner = _user(f"ma_{s}")
	db_session.add(owner)
	await db_session.flush()
	thread = Thread(owner_id=owner.id, title=f"chat_{s}", is_temporary=False)
	db_session.add(thread)
	await db_session.flush()
	# the off-branch token must share no substring with on-branch text, or
	# trigram overlap makes on-branch messages legitimate matches.
	s_off = _uid()
	m1 = _message(thread, None, MessageType.USER, f"tell me about zanzibar_{s}")
	db_session.add(m1)
	await db_session.flush()
	m2a = _message(
		thread, m1, MessageType.ASSISTANT, f"abandoned draft about quokkas_{s_off}"
	)
	db_session.add(m2a)
	await db_session.flush()
	m2b = _message(
		thread, m1, MessageType.ASSISTANT, f"final answer about zanzibar_{s}"
	)
	db_session.add(m2b)
	await db_session.flush()
	thread.current_message_id = m2b.id
	await db_session.commit()

	# search_text is maintained by the mapper event on insert
	await db_session.refresh(m1)
	assert m1.search_text and f"zanzibar_{s}" in m1.search_text

	hits = await _autocomplete_messages(
		f"zanzibar_{s}", db_session, principal=_principal(owner)
	)
	assert hits, "active-branch message must be found"
	assert str(hits[0].item.id) == str(thread.id)
	anchor = hits[0].hit.anchor
	assert anchor is not None
	assert str(anchor.id) in (str(m1.id), str(m2b.id))

	# the abandoned sibling branch must not surface
	off_branch = await _autocomplete_messages(
		f"quokkas_{s_off}", db_session, principal=_principal(owner)
	)
	assert not off_branch


@pytest.mark.asyncio
async def test_message_autocomplete_isolates_other_user(
	db_session: AsyncSession,
) -> None:
	s = _uid()
	u_a, u_b = _user(f"mi_{s}_a"), _user(f"mi_{s}_b")
	db_session.add_all([u_a, u_b])
	await db_session.flush()
	_thread, _messages = await _linear_thread(
		db_session,
		u_b,
		[(MessageType.USER, f"private_secret_{s} in message")],
	)
	hits = await _autocomplete_messages(
		f"private_secret_{s}", db_session, principal=_principal(u_a)
	)
	assert not hits


@pytest.mark.asyncio
async def test_tool_messages_have_no_search_text(
	db_session: AsyncSession,
) -> None:
	s = _uid()
	owner = _user(f"tm_{s}")
	db_session.add(owner)
	await db_session.flush()
	thread, messages = await _linear_thread(
		db_session,
		owner,
		[
			(MessageType.USER, f"user text {s}"),
			(MessageType.TOOL, f"tool output {s}"),
		],
	)
	await db_session.refresh(messages[0])
	await db_session.refresh(messages[1])
	assert messages[0].search_text
	assert messages[1].search_text is None


@pytest.mark.asyncio
async def test_message_autocomplete_include_all_branches(
	db_session: AsyncSession,
) -> None:
	"""include_all_branches surfaces hits from abandoned sibling branches."""
	s = _uid()
	owner = _user(f"ib_{s}")
	db_session.add(owner)
	await db_session.flush()
	thread = Thread(owner_id=owner.id, title=f"chat_{s}", is_temporary=False)
	db_session.add(thread)
	await db_session.flush()
	m1 = _message(thread, None, MessageType.USER, f"root question {s}")
	db_session.add(m1)
	await db_session.flush()
	m2a = _message(thread, m1, MessageType.ASSISTANT, f"abandoned xylophone_{s} draft")
	db_session.add(m2a)
	await db_session.flush()
	m2b = _message(thread, m1, MessageType.ASSISTANT, f"kept answer {s}")
	db_session.add(m2b)
	await db_session.flush()
	thread.current_message_id = m2b.id
	await db_session.commit()

	filters = ThreadSearchFilters(include_all_branches=True)
	hits = await _autocomplete_messages(
		f"xylophone_{s}", db_session, principal=_principal(owner), filters=filters
	)
	assert hits, "off-branch hit must surface with include_all_branches"
	anchor = hits[0].hit.anchor
	assert anchor is not None and str(anchor.id) == str(m2a.id)


@pytest.mark.asyncio
async def test_include_all_branches_stops_at_shared_thread_boundary(
	db_session: AsyncSession,
) -> None:
	"""in a shared thread the abandoned branches were never part of the
	conversation, so no filter may surface them."""
	from api.models.access_rule import AccessLevel
	from api.permissions import ResourceType
	from api.v1.service import access_rules

	s = _uid()
	owner = _user(f"ibs_{s}")
	mate = _user(f"ibm_{s}")
	db_session.add_all([owner, mate])
	await db_session.flush()
	thread = Thread(owner_id=owner.id, title=f"chat_{s}", is_temporary=False)
	db_session.add(thread)
	await db_session.flush()
	m1 = _message(thread, None, MessageType.USER, f"root question {s}")
	db_session.add(m1)
	await db_session.flush()
	abandoned = _message(
		thread, m1, MessageType.ASSISTANT, f"abandoned kazoo_{s} draft"
	)
	db_session.add(abandoned)
	await db_session.flush()
	kept = _message(thread, m1, MessageType.ASSISTANT, f"kept answer {s}")
	db_session.add(kept)
	await db_session.flush()
	thread.current_message_id = kept.id
	await db_session.commit()
	await access_rules.grant_user_access_unchecked(
		ResourceType.THREAD,
		thread.id,
		mate.id,
		db_session,
		level=AccessLevel.EDITOR,
	)

	filters = ThreadSearchFilters(include_all_branches=True)
	hits = await _autocomplete_messages(
		f"kazoo_{s}", db_session, principal=_principal(owner), filters=filters
	)
	anchored = {str(hit.hit.anchor.id) for hit in hits if hit.hit.anchor is not None}
	assert str(abandoned.id) not in anchored, (
		"shared threads must not leak abandoned branches"
	)


# hybrid fold tier (fake vectorstore hits)


def _thread_point_hit(thread_id: str, score: float) -> ChunkSearchResult:
	return ChunkSearchResult(
		id=uuid4().hex,
		content="title + summary",
		metadata={"resource_type": "thread", "resource_id": thread_id},
		score=score,
	)


def _passage_hit(
	thread_id: str,
	anchor_message_id: str,
	score: float,
	text: str = "user: passage text",
) -> ChunkSearchResult:
	return ChunkSearchResult(
		id=uuid4().hex,
		content=text,
		metadata={
			"resource_type": "thread_content",
			"parent_resource_id": thread_id,
			"resource_id": uuid4().hex,
			ANCHOR_MESSAGE_ID_KEY: anchor_message_id,
		},
		score=score,
	)


def _install_fake_hits(
	monkeypatch: pytest.MonkeyPatch,
	hits: list[ChunkSearchResult],
) -> None:
	async def _search(**_kwargs: object) -> list[ChunkSearchResult]:
		return hits

	patch_vectorstore_ops(monkeypatch, search=_search)


@pytest.mark.asyncio
async def test_hybrid_folds_to_one_result_with_passage_anchor(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""passage and thread-point hits fold to one result anchored at the best passage."""
	s = _uid()
	owner = _user(f"hf_{s}")
	db_session.add(owner)
	await db_session.flush()
	thread, messages = await _linear_thread(
		db_session,
		owner,
		[
			(MessageType.USER, "question"),
			(MessageType.ASSISTANT, "answer"),
		],
	)
	tid = str(thread.id)
	_install_fake_hits(
		monkeypatch,
		[
			_passage_hit(tid, str(messages[0].id), 0.9),
			_thread_point_hit(tid, 0.5),
			_passage_hit(tid, str(messages[1].id), 0.4),
		],
	)
	results = await _hybrid_search_threads(
		"question", db_session, principal=_principal(owner), search_params=_SPARSE
	)
	assert len(results) == 1
	assert str(results[0].item.id) == tid
	assert results[0].score == pytest.approx(0.9)
	anchor = results[0].hit.anchor
	assert anchor is not None and str(anchor.id) == str(messages[0].id)
	assert results[0].hit.matched_chunks


@pytest.mark.asyncio
async def test_hybrid_thread_point_best_still_anchors_via_passage(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""when the thread point outranks passages, the best passage still anchors."""
	s = _uid()
	owner = _user(f"ha_{s}")
	db_session.add(owner)
	await db_session.flush()
	thread, messages = await _linear_thread(
		db_session,
		owner,
		[(MessageType.USER, "question")],
	)
	tid = str(thread.id)
	_install_fake_hits(
		monkeypatch,
		[
			_thread_point_hit(tid, 0.9),
			_passage_hit(tid, str(messages[0].id), 0.4),
		],
	)
	results = await _hybrid_search_threads(
		"question", db_session, principal=_principal(owner), search_params=_SPARSE
	)
	assert len(results) == 1
	assert results[0].score == pytest.approx(0.9)
	anchor = results[0].hit.anchor
	assert anchor is not None and str(anchor.id) == str(messages[0].id)


@pytest.mark.asyncio
async def test_hybrid_drops_off_branch_passages(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""off-branch passage hits are dropped; include_all_branches restores them."""
	s = _uid()
	owner = _user(f"hb_{s}")
	db_session.add(owner)
	await db_session.flush()
	thread = Thread(owner_id=owner.id, title=f"branchy_{s}", is_temporary=False)
	db_session.add(thread)
	await db_session.flush()
	m1 = _message(thread, None, MessageType.USER, "root")
	db_session.add(m1)
	await db_session.flush()
	m2a = _message(thread, m1, MessageType.ASSISTANT, "abandoned")
	db_session.add(m2a)
	await db_session.flush()
	m2b = _message(thread, m1, MessageType.ASSISTANT, "kept")
	db_session.add(m2b)
	await db_session.flush()
	thread.current_message_id = m2b.id
	await db_session.commit()
	tid = str(thread.id)

	_install_fake_hits(monkeypatch, [_passage_hit(tid, str(m2a.id), 0.9)])
	results = await _hybrid_search_threads(
		"abandoned", db_session, principal=_principal(owner), search_params=_SPARSE
	)
	assert not results, "thread with only off-branch hits must be excluded"

	filters = ThreadSearchFilters(include_all_branches=True)
	results = await _hybrid_search_threads(
		"abandoned",
		db_session,
		principal=_principal(owner),
		search_params=_SPARSE,
		filters=filters,
	)
	assert len(results) == 1
	anchor = results[0].hit.anchor
	assert anchor is not None and str(anchor.id) == str(m2a.id)


@pytest.mark.asyncio
async def test_hybrid_include_all_branches_stops_at_shared_boundary(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""the passage path honours the shared-thread boundary too: no filter may
	surface a branch abandoned before the thread was shared."""
	from api.models.access_rule import AccessLevel
	from api.permissions import ResourceType
	from api.v1.service import access_rules

	s = _uid()
	owner = _user(f"hbs_{s}")
	mate = _user(f"hbm_{s}")
	db_session.add_all([owner, mate])
	await db_session.flush()
	thread = Thread(owner_id=owner.id, title=f"branchy_{s}", is_temporary=False)
	db_session.add(thread)
	await db_session.flush()
	m1 = _message(thread, None, MessageType.USER, "root")
	db_session.add(m1)
	await db_session.flush()
	abandoned = _message(thread, m1, MessageType.ASSISTANT, "abandoned")
	db_session.add(abandoned)
	await db_session.flush()
	kept = _message(thread, m1, MessageType.ASSISTANT, "kept")
	db_session.add(kept)
	await db_session.flush()
	thread.current_message_id = kept.id
	await db_session.commit()
	await access_rules.grant_user_access_unchecked(
		ResourceType.THREAD,
		thread.id,
		mate.id,
		db_session,
		level=AccessLevel.EDITOR,
	)
	tid = str(thread.id)

	_install_fake_hits(monkeypatch, [_passage_hit(tid, str(abandoned.id), 0.9)])
	results = await _hybrid_search_threads(
		"abandoned",
		db_session,
		principal=_principal(owner),
		search_params=_SPARSE,
		filters=ThreadSearchFilters(include_all_branches=True),
	)
	assert not results, "shared threads must not leak abandoned branch passages"


@pytest.mark.asyncio
async def test_hybrid_postgres_postfilter_blocks_cross_user_passages(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""passage hits for another user's thread are blocked by the postgres re-check."""
	s = _uid()
	u_a, u_b = _user(f"hx_{s}_a"), _user(f"hx_{s}_b")
	db_session.add_all([u_a, u_b])
	await db_session.flush()
	thread, messages = await _linear_thread(
		db_session,
		u_b,
		[(MessageType.USER, f"leaked passage {s}")],
	)
	_install_fake_hits(
		monkeypatch,
		[_passage_hit(str(thread.id), str(messages[0].id), 0.9)],
	)
	results = await _hybrid_search_threads(
		"leaked", db_session, principal=_principal(u_a), search_params=_SPARSE
	)
	assert not results


# sweep dueness predicate


@pytest.mark.asyncio
async def test_backfill_sweep_dispatches_vector_reconcile(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""the maintenance backfill sweep enqueues vector reconcile for due threads."""
	from api.v1.service.chat import thread_maintenance as thread_maintenance_service

	s = _uid()
	owner = _user(f"sw_{s}")
	db_session.add(owner)
	await db_session.flush()
	# no messages and no head: ineligible for llm maintenance, but vector-due
	# (never reconciled), so only the vector pass may pick it up.
	thread = Thread(owner_id=owner.id, title=f"sweep_{s}", is_temporary=False)
	db_session.add(thread)
	await db_session.flush()
	thread.last_activity_at = datetime.now(tz=UTC) - timedelta(hours=3)
	await db_session.commit()

	enqueued: list[str] = []

	async def _fake_enqueue(thread_id: str) -> bool:
		enqueued.append(str(thread_id))
		return True

	monkeypatch.setattr(
		thread_maintenance_service,
		"schedule_thread_content_vectorization",
		_fake_enqueue,
	)
	result = await thread_maintenance_service.run_thread_maintenance_backfill_sweep(
		batch_size=10,
		max_lookback_days=30,
		min_inactivity_hours=1,
		respect_enabled=False,
	)
	assert str(thread.id) in enqueued
	vectors_dispatched = result.get("vectors_dispatched")
	assert isinstance(vectors_dispatched, int) and vectors_dispatched >= 1


@pytest.mark.asyncio
async def test_content_vector_due_predicate(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""dueness = never reconciled, new activity, or a different collection;
	version staleness is knob-gated."""
	s = _uid()
	owner = _user(f"dp_{s}")
	db_session.add(owner)
	await db_session.flush()
	now = datetime.now(tz=UTC)
	collection = "test_collection"
	never = Thread(owner_id=owner.id, title=f"never_{s}", is_temporary=False)
	current = Thread(
		owner_id=owner.id,
		title=f"current_{s}",
		is_temporary=False,
	)
	current.set_metadata(
		private={
			CONTENT_VECTORS_SCHEMA_KEY: THREAD_CONTENT_PIPELINE_VERSION,
			CONTENT_VECTORS_BUILT_AT_KEY: now.isoformat(),
			CONTENT_VECTORS_COLLECTION_KEY: collection,
		}
	)
	old_schema = Thread(
		owner_id=owner.id,
		title=f"oldschema_{s}",
		is_temporary=False,
	)
	old_schema.set_metadata(
		private={
			CONTENT_VECTORS_SCHEMA_KEY: THREAD_CONTENT_PIPELINE_VERSION - 1,
			CONTENT_VECTORS_BUILT_AT_KEY: now.isoformat(),
			CONTENT_VECTORS_COLLECTION_KEY: collection,
		}
	)
	stale = Thread(
		owner_id=owner.id,
		title=f"stale_{s}",
		is_temporary=False,
	)
	stale.set_metadata(
		private={
			CONTENT_VECTORS_SCHEMA_KEY: THREAD_CONTENT_PIPELINE_VERSION,
			CONTENT_VECTORS_BUILT_AT_KEY: (now - timedelta(hours=2)).isoformat(),
			CONTENT_VECTORS_COLLECTION_KEY: collection,
		}
	)
	other_collection = Thread(
		owner_id=owner.id,
		title=f"othercol_{s}",
		is_temporary=False,
	)
	other_collection.set_metadata(
		private={
			CONTENT_VECTORS_SCHEMA_KEY: THREAD_CONTENT_PIPELINE_VERSION,
			CONTENT_VECTORS_BUILT_AT_KEY: now.isoformat(),
			CONTENT_VECTORS_COLLECTION_KEY: "previous_collection",
		}
	)
	db_session.add_all([never, current, old_schema, stale, other_collection])
	await db_session.flush()
	for thread in (never, current, old_schema, stale, other_collection):
		thread.last_activity_at = now - timedelta(hours=1)
	await db_session.commit()

	stmt = select(Thread.id).where(
		Thread.owner_id == str(owner.id),
		content_vectors_due_predicate(collection),
	)
	due_ids = {str(row[0]) for row in (await db_session.execute(stmt))}
	assert str(never.id) in due_ids
	assert str(stale.id) in due_ids
	# vectors in a different collection are unreachable: always due, no knob.
	assert str(other_collection.id) in due_ids
	# version staleness alone is not due while the trigger is off (default).
	assert str(old_schema.id) not in due_ids
	assert str(current.id) not in due_ids

	monkeypatch.setattr(
		settings.assets.revectorize.thread_passages,
		"on_pipeline_version",
		True,
	)
	gated_stmt = select(Thread.id).where(
		Thread.owner_id == str(owner.id),
		content_vectors_due_predicate(collection),
	)
	gated_ids = {str(row[0]) for row in (await db_session.execute(gated_stmt))}
	assert str(old_schema.id) in gated_ids
	assert str(current.id) not in gated_ids


def test_thread_passages_config_fp_tracks_settings(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	base = thread_passages_config_fp()
	assert base == thread_passages_config_fp()
	monkeypatch.setattr(settings.assets.thread_passages, "target_tokens", 555)
	assert thread_passages_config_fp() != base


@pytest.mark.asyncio
async def test_content_vectors_stale_predicate_by_cause(
	db_session: AsyncSession,
) -> None:
	"""each staleness cause matches exactly its provenance mismatch."""
	s = _uid()
	owner = _user(f"sp_{s}")
	db_session.add(owner)
	await db_session.flush()
	now = datetime.now(tz=UTC).isoformat()
	config_fp = thread_passages_config_fp()
	never = Thread(owner_id=owner.id, title=f"never_{s}", is_temporary=False)
	current = Thread(
		owner_id=owner.id,
		title=f"current_{s}",
		is_temporary=False,
	)
	current.set_metadata(
		private={
			CONTENT_VECTORS_SCHEMA_KEY: THREAD_CONTENT_PIPELINE_VERSION,
			CONTENT_VECTORS_BUILT_AT_KEY: now,
			CONTENT_VECTORS_CONFIG_KEY: config_fp,
		}
	)
	old_version = Thread(
		owner_id=owner.id,
		title=f"oldv_{s}",
		is_temporary=False,
	)
	old_version.set_metadata(
		private={
			CONTENT_VECTORS_SCHEMA_KEY: THREAD_CONTENT_PIPELINE_VERSION - 1,
			CONTENT_VECTORS_BUILT_AT_KEY: now,
			CONTENT_VECTORS_CONFIG_KEY: config_fp,
		}
	)
	bad_config = Thread(
		owner_id=owner.id,
		title=f"badcfg_{s}",
		is_temporary=False,
	)
	bad_config.set_metadata(
		private={
			CONTENT_VECTORS_SCHEMA_KEY: THREAD_CONTENT_PIPELINE_VERSION,
			CONTENT_VECTORS_BUILT_AT_KEY: now,
			CONTENT_VECTORS_CONFIG_KEY: "other-config",
		}
	)
	missing_config = Thread(
		owner_id=owner.id,
		title=f"nocfg_{s}",
		is_temporary=False,
	)
	missing_config.set_metadata(
		private={
			CONTENT_VECTORS_SCHEMA_KEY: THREAD_CONTENT_PIPELINE_VERSION,
			CONTENT_VECTORS_BUILT_AT_KEY: now,
		}
	)
	db_session.add_all([never, current, old_version, bad_config, missing_config])
	await db_session.flush()

	async def _matching(cause: StaleBy) -> set[str]:
		stmt = select(Thread.id).where(
			Thread.owner_id == str(owner.id),
			content_vectors_stale_predicate(cause),
		)
		return {str(row[0]) for row in (await db_session.execute(stmt))}

	by_version = await _matching(StaleBy.PIPELINE_VERSION)
	assert by_version == {str(old_version.id)}
	by_config = await _matching(StaleBy.CONFIG)
	assert by_config == {str(bad_config.id), str(missing_config.id)}
