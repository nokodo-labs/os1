"""thread content vectors: reconcile transcript passages in the vectorstore.

owns the vector-database side of thread transcripts. the full message tree
is planned into deterministic passages (see passages.py); reconciliation
diffs the plan against stored chunks and only embeds what changed, making
every trigger (post-run, edit, delete, import, sweep) an idempotent
convergence step. branch state is never written to the index; active-branch
filtering happens at query time against PostgreSQL.
"""

import logging
from datetime import UTC, datetime

from sqlalchemy import ColumnElement, Integer, and_, cast, or_, select
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.ext.asyncio import AsyncSession

from api.constants import PRIVATE_METADATA_KEY
from api.models.message import Message
from api.models.thread import Thread
from api.models.thread_passage import ThreadPassage
from api.permissions import ResourceType
from api.settings import settings
from api.v1.service.authorization import ACL_REVISION_KEY, fetch_bulk_acl_metadata
from api.v1.service.embeddings import embed_texts, embedding_token_capacity
from api.v1.service.threads.passages import (
	TranscriptPassage,
	build_transcript_passages,
	delete_passages,
	list_passages,
)
from api.v1.service.vectorize import StaleBy, fingerprint_payload
from api.v1.service.vectorstores import (
	ChunkFilter,
	FieldMatch,
	FieldMatchAny,
	VectorChunkResourceType,
	child_resource_filter,
	delete,
	get_collection,
	resource_types_filter,
	scroll_chunks,
	upsert_chunks,
)
from nokodo_ai.adapters.base.vectorstores import Chunk
from nokodo_ai.types.json import JSONObject
from nokodo_ai.utils.typeid import TypeID


logger = logging.getLogger(__name__)

THREAD_RESOURCE_TYPE = VectorChunkResourceType.THREAD
THREAD_CONTENT_RESOURCE_TYPE = VectorChunkResourceType.THREAD_CONTENT

THREAD_CONTENT_PIPELINE_VERSION = 1
"""provenance version stamped on reconciled threads; bump after a passage
code change so stale threads become targetable."""

CONTENT_VECTORS_SCHEMA_KEY = "content_vectors_schema"
"""private metadata key holding the pipeline version of the last reconcile."""

CONTENT_VECTORS_BUILT_AT_KEY = "content_vectors_built_at"
"""private metadata key holding the timestamp of the last reconcile."""

CONTENT_VECTORS_CONFIG_KEY = "content_vectors_config"
"""private metadata key holding the config fingerprint of the last reconcile."""

CONTENT_VECTORS_COLLECTION_KEY = "content_vectors_collection"
"""private metadata key holding the collection the last reconcile wrote to."""

ANCHOR_MESSAGE_ID_KEY = "anchor_message_id"
ENRICHMENT_KEY = "enrichment"


def content_vectors_due_predicate(collection: str) -> ColumnElement[bool]:
	"""SQL predicate matching threads whose transcript vectors are due.

	due = never reconciled, built before the thread's latest activity, or
	written to a different collection than the active one (a model or layout
	switch makes those vectors unreachable, so this is never knob-gated).
	version/config staleness is included only when the thread_passages
	revectorize triggers enable it.
	"""
	schema_text = Thread.metadata_[
		(PRIVATE_METADATA_KEY, CONTENT_VECTORS_SCHEMA_KEY)
	].as_string()
	built_text = Thread.metadata_[
		(PRIVATE_METADATA_KEY, CONTENT_VECTORS_BUILT_AT_KEY)
	].as_string()
	collection_text = Thread.metadata_[
		(PRIVATE_METADATA_KEY, CONTENT_VECTORS_COLLECTION_KEY)
	].as_string()
	conditions: list[ColumnElement[bool]] = [
		schema_text.is_(None),
		cast(built_text, TIMESTAMP(timezone=True)) < Thread.last_activity_at,
		collection_text.is_(None),
		collection_text != collection,
	]
	triggers = settings.assets.revectorize.thread_passages
	if triggers.on_pipeline_version:
		conditions.append(content_vectors_stale_predicate(StaleBy.PIPELINE_VERSION))
	if triggers.on_config_change:
		conditions.append(content_vectors_stale_predicate(StaleBy.CONFIG))
	return or_(*conditions)


def content_vectors_stale_predicate(by: StaleBy) -> ColumnElement[bool]:
	"""SQL predicate matching reconciled threads provenance-stale by one cause."""
	schema_text = Thread.metadata_[
		(PRIVATE_METADATA_KEY, CONTENT_VECTORS_SCHEMA_KEY)
	].as_string()
	if by is StaleBy.PIPELINE_VERSION:
		return and_(
			schema_text.is_not(None),
			cast(schema_text, Integer) != THREAD_CONTENT_PIPELINE_VERSION,
		)
	config_text = Thread.metadata_[
		(PRIVATE_METADATA_KEY, CONTENT_VECTORS_CONFIG_KEY)
	].as_string()
	return and_(
		schema_text.is_not(None),
		or_(
			config_text.is_(None),
			config_text != thread_passages_config_fp(),
		),
	)


def thread_passages_config_fp() -> str:
	"""fingerprint of the settings that shape transcript passage chunking."""
	cfg = settings.assets.thread_passages
	return fingerprint_payload(
		{
			"target_tokens": cfg.target_tokens,
			"overlap_ratio": cfg.overlap_ratio,
		}
	)


def passage_chunking_params() -> tuple[int, int]:
	"""return (target_tokens, overlap_tokens) from thread passage settings."""
	cfg = settings.assets.thread_passages
	return cfg.target_tokens, int(cfg.target_tokens * cfg.overlap_ratio)


async def passage_generation_params(session: AsyncSession) -> tuple[int, int]:
	"""return passage geometry after validating active model capacity."""
	target_tokens, overlap_tokens = passage_chunking_params()
	capacity = await embedding_token_capacity(session)
	if capacity is not None and target_tokens > capacity:
		raise ValueError(
			f"thread passage target_tokens ({target_tokens}) exceeds the active "
			f"embedding model capacity ({capacity}); lower the passage target or "
			"select a model with a larger context window"
		)
	return target_tokens, overlap_tokens


def _passage_key(passage: TranscriptPassage) -> tuple[str, str, int]:
	return (
		passage.first_message_id,
		passage.last_message_id,
		passage.part_index,
	)


def _passage_dense_text(
	thread: Thread, passage: TranscriptPassage, enrichment: str
) -> str:
	"""passage transcript contextualized for embedding.

	the model-written enrichment replaces the title prefix when present.
	"""
	if enrichment:
		return f"{enrichment}\n{passage.text}"
	title = (thread.title or "").strip()
	if title:
		return f"{title}\n{passage.text}"
	return passage.text


def _passage_bm25_text(passage: TranscriptPassage, enrichment: str) -> str:
	"""passage sparse text; enrichment terms are folded in for lexical recall."""
	if enrichment:
		return f"{enrichment}\n{passage.text}"
	return passage.text


def _passage_fingerprint(dense_text: str, bm25_text: str) -> str:
	return fingerprint_payload(
		{
			"dense": dense_text,
			"bm25": bm25_text,
		}
	)


def _stamp_content_vector_state(
	thread: Thread,
	built_at: datetime,
	collection: str,
) -> None:
	"""record reconcile state on the thread row for SQL-side sweep dueness."""
	thread.set_metadata(
		private={
			**thread.private_metadata,
			CONTENT_VECTORS_SCHEMA_KEY: THREAD_CONTENT_PIPELINE_VERSION,
			CONTENT_VECTORS_BUILT_AT_KEY: built_at.isoformat(),
			CONTENT_VECTORS_CONFIG_KEY: thread_passages_config_fp(),
			CONTENT_VECTORS_COLLECTION_KEY: collection,
		}
	)


def _clear_content_vector_state(thread: Thread) -> None:
	"""drop reconcile stamps so a re-enabled thread is due again."""
	private = thread.private_metadata
	for key in (
		CONTENT_VECTORS_SCHEMA_KEY,
		CONTENT_VECTORS_BUILT_AT_KEY,
		CONTENT_VECTORS_CONFIG_KEY,
		CONTENT_VECTORS_COLLECTION_KEY,
	):
		private.pop(key, None)
	thread.set_metadata(private=private)


async def purge_thread_content_vectors(
	session: AsyncSession,
	thread_ids: list[TypeID | str] | None = None,
) -> int:
	"""remove persisted passages, their vectors, and their reconcile stamps.

	thread_ids=None purges every thread, which is what turning passage
	indexing off does. returns the number of threads whose stamps were
	cleared.
	"""
	# stamps written earlier in this session must be visible to the sweep below.
	await session.flush()
	await delete_passages(session, thread_ids=thread_ids)
	if thread_ids is None:
		chunk_target = resource_types_filter([THREAD_CONTENT_RESOURCE_TYPE])
	else:
		chunk_target = child_resource_filter(
			THREAD_RESOURCE_TYPE,
			[str(tid) for tid in thread_ids],
			THREAD_CONTENT_RESOURCE_TYPE,
		)
	await delete(target=chunk_target, session=session)
	schema_text = Thread.metadata_[
		(PRIVATE_METADATA_KEY, CONTENT_VECTORS_SCHEMA_KEY)
	].as_string()
	stmt = select(Thread).where(schema_text.is_not(None))
	if thread_ids is not None:
		stmt = stmt.where(Thread.id.in_([str(tid) for tid in thread_ids]))
	threads = list((await session.execute(stmt)).scalars().all())
	for thread in threads:
		_clear_content_vector_state(thread)
	await session.flush()
	return len(threads)


async def _reconcile_one_thread_content_vectors(
	thread_id: TypeID,
	session: AsyncSession,
) -> JSONObject:
	"""converge persisted passages and their vectors to the current message tree."""
	if not settings.assets.thread_passages.enabled:
		return {"thread_id": str(thread_id), "skipped": True}
	thread = await session.get(Thread, thread_id)
	if thread is None or thread.deleted_at is not None or thread.is_temporary:
		await purge_thread_content_vectors(session, thread_ids=[thread_id])
		return {"thread_id": str(thread_id), "purged": True}

	result = await session.execute(
		select(Message).where(Message.thread_id == str(thread_id))
	)
	messages = list(result.scalars().all())
	observed_activity_at = thread.last_activity_at or datetime.now(tz=UTC)

	stored_chunks = await scroll_chunks(
		child_resource_filter(
			THREAD_RESOURCE_TYPE,
			[str(thread.id)],
			THREAD_CONTENT_RESOURCE_TYPE,
		),
		session,
	)
	chunk_fingerprints: dict[str, str] = {}
	for chunk in stored_chunks:
		rid = chunk.metadata.get("resource_id")
		fingerprint = chunk.metadata.get("vec_fingerprint")
		if isinstance(rid, str):
			chunk_fingerprints[rid] = (
				fingerprint if isinstance(fingerprint, str) else ""
			)

	target_tokens, overlap_tokens = await passage_generation_params(session)
	passages = build_transcript_passages(
		messages,
		target_tokens=target_tokens,
		overlap_tokens=overlap_tokens,
	)
	stored_rows = await list_passages(thread.id, session)
	rows_by_key = {
		(str(row.first_message_id), str(row.last_message_id), row.part_index): row
		for row in stored_rows
	}
	planned_rows: list[tuple[ThreadPassage, TranscriptPassage]] = []
	for passage in passages:
		key = _passage_key(passage)
		row = rows_by_key.pop(key, None)
		if row is None:
			row = ThreadPassage(
				first_message_id=passage.first_message_id,
				last_message_id=passage.last_message_id,
				part_index=passage.part_index,
				content_hash=passage.content_hash,
				anchor_message_id=passage.anchor_message_id,
				content=passage.text,
			)
			session.add(row)
		elif row.content_hash != passage.content_hash:
			row.content_hash = passage.content_hash
			row.anchor_message_id = TypeID(passage.anchor_message_id)
			row.content = passage.text
			row.enrichment = None
			row.enrichment_model_id = None
			row.enriched_at = None
			row.enrichment_pipeline_v = None
		planned_rows.append((row, passage))
	orphaned_row_ids = [str(row.id) for row in rows_by_key.values()]
	for row in rows_by_key.values():
		await session.delete(row)
	await session.flush()

	planned: dict[str, tuple[TranscriptPassage, str, str, str]] = {}
	for row, passage in planned_rows:
		persisted_passage = TranscriptPassage(
			first_message_id=str(row.first_message_id),
			last_message_id=str(row.last_message_id),
			part_index=row.part_index,
			content_hash=row.content_hash,
			anchor_message_id=str(row.anchor_message_id),
			text=row.content,
		)
		blurb = row.enrichment or ""
		dense_text = _passage_dense_text(thread, persisted_passage, blurb)
		bm25_text = _passage_bm25_text(persisted_passage, blurb)
		planned[str(row.id)] = (
			persisted_passage,
			dense_text,
			_passage_fingerprint(dense_text, bm25_text),
			blurb,
		)

	to_build = [
		passage_id
		for passage_id, (_, _, fingerprint, _) in planned.items()
		if chunk_fingerprints.get(passage_id) != fingerprint
	]

	if to_build:
		acl_metadata = (
			await fetch_bulk_acl_metadata(
				[str(thread.id)], ResourceType.THREAD, session
			)
		)[str(thread.id)]
		# TODO(contextualized-embeddings): route on embedding_token_capacity() -
		# unlimited capacity embeds all a thread's passages as one document call.
		embeddings = await embed_texts(
			[planned[passage_id][1] for passage_id in to_build],
			session,
			input_type="document",
		)
		built_at = datetime.now(tz=UTC).isoformat()
		chunks: list[Chunk] = []
		for passage_id, embedding in zip(to_build, embeddings):
			passage, _, fingerprint, blurb = planned[passage_id]
			metadata: JSONObject = {
				"resource_type": THREAD_CONTENT_RESOURCE_TYPE.value,
				"resource_id": passage_id,
				"parent_resource_type": THREAD_RESOURCE_TYPE.value,
				"parent_resource_id": str(thread.id),
				"owner_id": str(thread.owner_id),
				ANCHOR_MESSAGE_ID_KEY: passage.anchor_message_id,
				"vec_fingerprint": fingerprint,
				"chunk_index": 0,
				"chunk_count": 1,
				"built_at": built_at,
			}
			if blurb:
				metadata[ENRICHMENT_KEY] = blurb
			metadata.update(
				{
					"allowed_user_ids": list(acl_metadata["allowed_user_ids"]),
					"allowed_group_ids": list(acl_metadata["allowed_group_ids"]),
					"allowed_role_ids": list(acl_metadata["allowed_role_ids"]),
					ACL_REVISION_KEY: acl_metadata[ACL_REVISION_KEY],
				}
			)
			chunks.append(
				Chunk(
					id=passage_id,
					content=_passage_bm25_text(passage, blurb),
					embedding=embedding,
					metadata=metadata,
				)
			)
		# delete every id being built so points a concurrent reconcile wrote
		# for the same passage never persist as duplicates.
		await delete(
			target=ChunkFilter(
				all_of=[
					FieldMatch(
						key="resource_type",
						value=THREAD_CONTENT_RESOURCE_TYPE.value,
					),
					FieldMatchAny(key="resource_id", values=to_build),
				]
			),
			session=session,
		)
		await upsert_chunks(chunks=chunks, session=session)

	orphaned = list(
		set(orphaned_row_ids)
		| {passage_id for passage_id in chunk_fingerprints if passage_id not in planned}
	)
	if orphaned:
		await delete(
			target=ChunkFilter(
				all_of=[
					FieldMatch(
						key="resource_type",
						value=THREAD_CONTENT_RESOURCE_TYPE.value,
					),
					FieldMatchAny(key="resource_id", values=orphaned),
				]
			),
			session=session,
		)

	collection = await get_collection(session)
	_stamp_content_vector_state(thread, observed_activity_at, collection)
	summary: JSONObject = {
		"thread_id": str(thread.id),
		"passages": len(planned),
		"built": len(to_build),
		"deleted": len(orphaned),
	}
	if to_build or orphaned:
		logger.info(
			"thread content vectors reconciled thread_id=%s passages=%d "
			"built=%d deleted=%d",
			thread.id,
			len(planned),
			len(to_build),
			len(orphaned),
		)
	return summary


async def reconcile_thread_content_vectors(
	session: AsyncSession,
	thread_ids: list[TypeID] | None = None,
) -> list[JSONObject]:
	"""converge persisted passages and their vectors to the current message tree.

	returns one summary per reconciled thread. thread_ids=None sweeps every
	thread that is due (the admin rebuild path), committing per thread so
	partial progress survives a failure mid-corpus; an explicit list
	reconciles exactly those threads in the caller's transaction.
	"""
	if thread_ids is not None:
		return [
			await _reconcile_one_thread_content_vectors(thread_id, session)
			for thread_id in thread_ids
		]

	if not settings.assets.thread_passages.enabled:
		return []
	collection = await get_collection(session)
	stmt = select(Thread.id).where(
		Thread.deleted_at.is_(None),
		Thread.is_temporary.is_(False),
		content_vectors_due_predicate(collection),
	)
	due_ids = [TypeID(str(row[0])) for row in (await session.execute(stmt))]
	summaries: list[JSONObject] = []
	for thread_id in due_ids:
		summaries.append(
			await _reconcile_one_thread_content_vectors(thread_id, session)
		)
		await session.commit()
	return summaries
