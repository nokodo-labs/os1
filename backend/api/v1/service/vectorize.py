"""shared vectorization contract.

VectorSpec is the contract each resource service implements to declare:
  - what text to embed (dense) and store for BM25 retrieval
  - what metadata fields accompany the chunk
  - how to extract the resource ID (used for filter-based identity)
  - when an update requires re-vectorizing

chunk identity is entirely filter-based: (resource_type, resource_id)
identifies a chunk in the vectorstore without relying on the chunk ID.
chunks are assigned random UUIDs so a single resource can grow to N
chunks in the future without any schema changes.

concrete specs live in each resource's service module.

resource tier contract - how unbounded content is vectorized:
  - single-tier (this module): the resource is one logical text (note,
    memory, reminder, calendar event, thread/file metadata point).
    oversized dense_text overflow-splits via split_for_embedding; the
    chunks share the resource_id and collapse at search time through
    group_by="resource_id". use this by default.
  - two-tier (custom pipeline per resource): content chunks carry their
    own resource_id plus parent_resource_type/id, so a hit can anchor a
    sub-resource and rebuilds can be incremental. precedents:
    files/text_contents/vectors.py (FILE_CONTENT, extraction-input
    fingerprint) and threads/content_vectors.py (THREAD_CONTENT,
    per-passage content-hash fingerprints + row stamps for sweep
    dueness). upgrade a resource to two-tier only when it needs
    sub-resource anchors or incremental reconcile.
  - staleness is split by cause: fingerprints digest CONTENT only, and
    every stored chunk carries pipeline_v/config_fp provenance stamps.
    content mismatch always rebuilds; version/config mismatch rebuilds
    only when the pipeline's settings.assets.revectorize triggers allow
    it, or when an admin explicitly targets that staleness cause.
  - splitting decisions route on embeddings.embedding_token_capacity():
    how many tokens one embedding call accepts. None (unlimited,
    contextualized models) never splits; finite capacities split before
    embedding. chunk/passage sizes remain retrieval-granularity knobs,
    independent of call capacity.
"""

import hashlib
import json
import logging
import uuid
from collections.abc import Awaitable, Callable, Collection, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from api.permissions import ResourceType
from api.settings import settings
from api.v1.service.authorization import (
	ACL_REVISION_KEY,
	ACL_SYNC_VECTOR_CHUNK_RESOURCE_TYPES,
	VECTOR_CHUNK_PARENT_RESOURCE_TYPES,
	fetch_bulk_acl_metadata,
)
from api.v1.service.embeddings import (
	_get_embedding_model,
	count_input_tokens,
	embed_texts,
	embedding_token_capacity,
)
from api.v1.service.vectorstores import (
	VectorChunkResourceType,
	delete,
	get_collection,
	get_vectorstore,
	parent_resource_filter,
	resource_types_filter,
	scroll_resource_chunks,
	upsert_chunks,
)
from nokodo_ai.adapters.base.loaders import Text
from nokodo_ai.adapters.base.vectorstores import Chunk, ChunkFilter
from nokodo_ai.adapters.nokodo_ai.semantic import SemanticChunkerAdapter
from nokodo_ai.chunkers import Chunker, ContentChunk
from nokodo_ai.types.json import JSONObject
from nokodo_ai.utils.concurrency import map_concurrently
from nokodo_ai.utils.tokens import CHARS_PER_TOKEN, estimate_tokens
from nokodo_ai.utils.typeid import TypeID


_VECTOR_ACL_UPDATE_CONCURRENCY = 32
VECTORIZATION_PIPELINE_VERSION = 1
"""provenance version stamped on generic single-tier chunks; bump after a
chunking/text-building code change so stale vectors become targetable."""

PIPELINE_VERSION_KEY = "pipeline_v"
"""chunk metadata key holding the pipeline version that built the chunk."""

CONFIG_FP_KEY = "config_fp"
"""chunk metadata key holding the config fingerprint the chunk was built with."""


class StaleBy(StrEnum):
	"""non-content staleness causes an explicit revectorize can target."""

	PIPELINE_VERSION = "pipeline_version"
	CONFIG = "config"
	ACL = "acl"


logger = logging.getLogger(__name__)

# acl fields live on chunks but are owned by acl sync, so they are
# excluded from the fingerprint and never read as a stale vector.
_FINGERPRINT_EXCLUDED_METADATA = frozenset(
	{
		"allowed_user_ids",
		"allowed_group_ids",
		"allowed_role_ids",
		ACL_REVISION_KEY,
		"vec_fingerprint",
		"chunk_index",
		"chunk_count",
	}
)


@dataclass(frozen=True, slots=True)
class VectorSpec[T]:
	"""definition of how a resource type is embedded and stored.

	- resource_id: bare resource ID string extracted from the object;
		(filter-based identity - NOT the chunk ID)

	- dense_text: text for dense (semantic) vector
	- bm25_text: full text for BM25/sparse retrieval
	- metadata: resource-specific fields; resource_type/resource_id injected
	- should_revectorize: async (current, update_data, session) -> bool
	- fingerprint: deterministic input digest used to detect stale vectors;
		defaults to a hash of bm25_text plus comparable (non-acl) metadata
	- chunker: chunker adapter used when dense_text overflows the embedding
		model's input limit and must be split into multiple chunks
	"""

	resource_type: VectorChunkResourceType
	resource_id: Callable[[T], str]
	dense_text: Callable[[T], str]
	bm25_text: Callable[[T], str]
	metadata: Callable[[T], JSONObject]
	should_revectorize: Callable[[T, Any, AsyncSession], Awaitable[bool]]
	fingerprint: Callable[[T], str] | None = None
	chunker: Literal["recursive", "markdown", "semantic"] = "recursive"


def fingerprint_payload(payload: JSONObject) -> str:
	"""stable sha256 over a json-serializable payload."""
	encoded = json.dumps(
		payload,
		sort_keys=True,
		ensure_ascii=False,
		default=str,
	)
	return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def resource_fingerprint[T](spec: VectorSpec[T], resource: T) -> str:
	"""compute the content fingerprint for a resource.

	digests only the content inputs that produced the stored chunks; pipeline
	version and configuration are tracked as separate provenance stamps so
	their staleness can be policy-gated. uses the spec override when provided,
	else hashes bm25_text plus comparable metadata (acl and chunk-bookkeeping
	fields excluded).
	"""
	if spec.fingerprint is not None:
		return spec.fingerprint(resource)
	meta = {
		key: value
		for key, value in spec.metadata(resource).items()
		if key not in _FINGERPRINT_EXCLUDED_METADATA
	}
	return fingerprint_payload(
		{
			"text": spec.bm25_text(resource),
			"meta": meta,
		}
	)


def vectorization_config_fp() -> str:
	"""fingerprint of the settings that shape generic single-tier chunking."""
	cfg = settings.assets.content_vectorization
	return fingerprint_payload(
		{
			"chunker": cfg.chunking_algorithm,
			"target_tokens": cfg.target_tokens,
			"overlap_tokens": cfg.overlap_tokens,
			"max_chunks": cfg.max_chunks,
			"semantic_breakpoint_percentile": cfg.semantic_breakpoint_percentile,
			"semantic_min_sentences": cfg.semantic_min_sentences,
			"semantic_buffer_size": cfg.semantic_buffer_size,
		}
	)


def build_chunk[T](
	spec: VectorSpec[T],
	resource: T,
	embedding: list[float],
	extra_metadata: Mapping[str, Any] | None = None,
	chunk_index: int = 0,
	chunk_count: int = 1,
	fingerprint: str | None = None,
	content: str | None = None,
) -> Chunk:
	"""build a Chunk from a resource using its VectorSpec.

	chunks receive a random UUID. identity is filter-based via
	(resource_type, resource_id) in metadata - not via chunk ID.
	this decouples chunk cardinality from resource cardinality.

	extra_metadata is merged after spec.metadata() and before the
	injected resource_type/resource_id so callers (e.g. ACL sync) can
	add fields without risk of clobbering identity fields.

	content overrides the stored BM25 text; defaults to bm25_text(resource).
	multi-chunk callers pass the per-chunk text so each chunk indexes its own
	slice instead of duplicating the full resource text.

	vec_fingerprint/chunk_index/chunk_count are stamped so a later
	verification pass can tell whether the stored chunk set is complete and
	current without re-deriving the chunk contents.
	"""
	rid = spec.resource_id(resource)
	chunk_content = content if content is not None else spec.bm25_text(resource)
	meta: JSONObject = {
		**spec.metadata(resource),
		**(extra_metadata or {}),
		"resource_type": spec.resource_type.value,
		"resource_id": rid,
		"vec_fingerprint": (
			fingerprint
			if fingerprint is not None
			else resource_fingerprint(spec, resource)
		),
		PIPELINE_VERSION_KEY: VECTORIZATION_PIPELINE_VERSION,
		CONFIG_FP_KEY: vectorization_config_fp(),
		"chunk_index": chunk_index,
		"chunk_count": chunk_count,
	}
	return Chunk(
		id=str(uuid.uuid4()),
		content=chunk_content,
		embedding=embedding,
		metadata=meta,
	)


def chunks_match_fingerprint(chunks: Sequence[Chunk], fingerprint: str) -> bool:
	"""return whether stored chunks are a complete, current vectorization.

	complete = the stored chunk_index values cover 0..chunk_count-1 exactly.
	current = every stored chunk carries the expected vec_fingerprint and a
	consistent chunk_count. missing, extra, mismatched, or partial chunk sets
	all read as not-vectorized so the caller rebuilds them.
	"""
	if not chunks:
		return False
	count: int | None = None
	indices: set[int] = set()
	for chunk in chunks:
		meta = chunk.metadata
		if meta.get("vec_fingerprint") != fingerprint:
			return False
		index = meta.get("chunk_index")
		chunk_count = meta.get("chunk_count")
		if not isinstance(index, int) or not isinstance(chunk_count, int):
			return False
		if count is None:
			count = chunk_count
		elif count != chunk_count:
			return False
		indices.add(index)
	if count is None or count <= 0:
		return False
	return indices == set(range(count))


def chunk_stamps_stale(
	chunks: Sequence[Chunk],
	by: Collection[StaleBy] | None = None,
) -> bool:
	"""whether stored chunks are provenance-stale by any of the given causes.

	without ``by``, staleness is gated by the generic pipeline's revectorize
	triggers; with ``by``, exactly those causes are checked, ungated (explicit
	admin targeting). chunks missing a stamp count as stale for its cause.
	"""
	if not chunks:
		return False
	triggers = settings.assets.revectorize.resources
	check_version = (
		StaleBy.PIPELINE_VERSION in by
		if by is not None
		else triggers.on_pipeline_version
	)
	check_config = StaleBy.CONFIG in by if by is not None else triggers.on_config_change
	if check_version and any(
		chunk.metadata.get(PIPELINE_VERSION_KEY) != VECTORIZATION_PIPELINE_VERSION
		for chunk in chunks
	):
		return True
	if check_config:
		config_fp = vectorization_config_fp()
		if any(chunk.metadata.get(CONFIG_FP_KEY) != config_fp for chunk in chunks):
			return True
	return False


async def filter_unvectorized[T](
	spec: VectorSpec[T],
	resources: Sequence[T],
	session: AsyncSession,
) -> list[T]:
	"""return resources whose stored vectors are missing or stale.

	one scroll fetches every chunk for the candidate resource ids; each
	resource is kept when its stored chunks fail the content fingerprint and
	completeness check, or are provenance-stale per the revectorize triggers.
	callers re-vectorize the returned subset, making bulk vectorization
	idempotent and gap-filling on re-runs.
	"""
	if not resources:
		return []
	expected = {
		spec.resource_id(resource): resource_fingerprint(spec, resource)
		for resource in resources
	}
	chunks = await scroll_resource_chunks(
		spec.resource_type,
		list(expected.keys()),
		session,
	)
	grouped: dict[str, list[Chunk]] = {}
	for chunk in chunks:
		rid = chunk.metadata.get("resource_id")
		if isinstance(rid, str):
			grouped.setdefault(rid, []).append(chunk)
	pending: list[T] = []
	for resource in resources:
		rid = spec.resource_id(resource)
		stored = grouped.get(rid, [])
		if not chunks_match_fingerprint(stored, expected[rid]) or chunk_stamps_stale(
			stored
		):
			pending.append(resource)
	return pending


async def remove_vectorized_resource[T](
	spec: VectorSpec[T],
	resource_id: str,
	session: AsyncSession,
) -> None:
	"""remove all chunks for a resource from the vectorstore."""
	await delete(
		target=resource_types_filter([spec.resource_type], resource_id=resource_id),
		session=session,
	)


@dataclass(frozen=True, slots=True)
class _EmbeddingPiece:
	"""one embed/index unit produced from a resource's dense_text."""

	embed_text: str
	content: str
	chunk_index: int
	chunk_count: int
	metadata: JSONObject


async def _chunk_dense_text[T](spec: VectorSpec[T], dense: str) -> list[ContentChunk]:
	"""split oversized dense_text into chunks using the configured chunker."""
	cfg = settings.assets.content_vectorization
	algorithm = (
		cfg.chunking_algorithm if cfg.chunking_algorithm != "auto" else spec.chunker
	)
	if algorithm == "semantic":
		embedder = await _get_embedding_model()
		adapter = SemanticChunkerAdapter(
			embedder=embedder,
			breakpoint_percentile=cfg.semantic_breakpoint_percentile,
			min_sentences_per_chunk=cfg.semantic_min_sentences,
			buffer_size=cfg.semantic_buffer_size,
		)
		chunker = Chunker.create(
			adapter=adapter,
			target_tokens=cfg.target_tokens,
			overlap_tokens=cfg.overlap_tokens,
			max_chunks=cfg.max_chunks,
		)
	else:
		chunker = Chunker.create(
			adapter=algorithm,
			target_tokens=cfg.target_tokens,
			overlap_tokens=cfg.overlap_tokens,
			max_chunks=cfg.max_chunks,
		)
	text = Text(
		content=dense,
		status="loaded",
		source=spec.resource_type.value,
		format="markdown" if algorithm == "markdown" else "plain",
	)
	return await chunker.chunk(text)


async def split_for_embedding[T](
	spec: VectorSpec[T],
	resource: T,
	session: AsyncSession,
) -> list[_EmbeddingPiece]:
	"""split a resource's dense_text into embeddable pieces.

	returns a single piece (preserving the existing single-chunk behaviour and
	its distinct bm25_text content) when the text fits the embedding model's
	input limit. oversized text is chunked; each chunk indexes its own slice so
	embedding never receives more tokens than the model accepts.
	"""
	dense = spec.dense_text(resource)
	if not dense.strip():
		return []
	capacity = await embedding_token_capacity(session)
	counts = await count_input_tokens([dense], session)
	# estimate_tokens already applies a safety margin, so the estimate path
	# chunks slightly earlier than strictly necessary - the safe direction.
	tokens = counts[0] if counts is not None else estimate_tokens(dense)
	if capacity is None or tokens <= capacity:
		return [
			_EmbeddingPiece(
				embed_text=dense,
				content=spec.bm25_text(resource),
				chunk_index=0,
				chunk_count=1,
				metadata={},
			)
		]
	chunks = [c for c in await _chunk_dense_text(spec, dense) if c.text.strip()]
	if not chunks:
		return [
			_EmbeddingPiece(
				embed_text=dense,
				content=spec.bm25_text(resource),
				chunk_index=0,
				chunk_count=1,
				metadata={},
			)
		]
	# defensive backstop: a misconfigured target_tokens above the capacity
	# could still emit an oversized chunk; hard-truncate by character budget.
	char_budget = int(capacity * CHARS_PER_TOKEN)
	total = len(chunks)
	pieces: list[_EmbeddingPiece] = []
	for index, chunk in enumerate(chunks):
		text = chunk.text
		if estimate_tokens(text) > capacity:
			text = text[:char_budget]
		pieces.append(
			_EmbeddingPiece(
				embed_text=text,
				content=text,
				chunk_index=index,
				chunk_count=total,
				metadata=dict(chunk.metadata),
			)
		)
	return pieces


async def vectorize_resource[T](
	spec: VectorSpec[T],
	resource: T,
	session: AsyncSession,
	extra_metadata: Mapping[str, Any] | None = None,
) -> None:
	"""vectorize a single resource: delete existing chunks then insert fresh.

	delete-before-insert keeps the vectorstore consistent without relying
	on stable chunk IDs. a new random UUID is assigned each time.

	dense_text that fits the embedding model input limit produces one chunk
	(unchanged behaviour); oversized text is split into multiple chunks that
	share one fingerprint and carry sequential chunk_index/chunk_count.

	extra_metadata is merged into the chunk payload (e.g. acl fields).
	"""
	pieces = await split_for_embedding(spec, resource, session)
	if not pieces:
		return
	fingerprint = resource_fingerprint(spec, resource)
	await remove_vectorized_resource(spec, spec.resource_id(resource), session)
	embeddings = await embed_texts(
		[p.embed_text for p in pieces], session, input_type="document"
	)
	chunks = [
		build_chunk(
			spec,
			resource,
			embedding,
			extra_metadata={**(extra_metadata or {}), **piece.metadata},
			content=piece.content,
			chunk_index=piece.chunk_index,
			chunk_count=piece.chunk_count,
			fingerprint=fingerprint,
		)
		for piece, embedding in zip(pieces, embeddings)
	]
	await upsert_chunks(chunks=chunks, session=session)


async def vectorize_resources[T](
	spec: VectorSpec[T],
	resources: Sequence[T],
	session: AsyncSession,
	extra_metadata_by_id: dict[str, Any] | None = None,
) -> int:
	"""bulk-vectorize resources with a single embedding round-trip.

	each resource is split independently; all chunk texts are embedded in one
	batch and regrouped per resource so oversized resources contribute several
	chunks without inflating the number of embedding calls. returns the number
	of resources that produced at least one chunk.
	"""
	plans: list[tuple[T, str, str, list[_EmbeddingPiece]]] = []
	for resource in resources:
		pieces = await split_for_embedding(spec, resource, session)
		if not pieces:
			continue
		rid = spec.resource_id(resource)
		plans.append((resource, rid, resource_fingerprint(spec, resource), pieces))
	if not plans:
		return 0
	# TODO(contextualized-embeddings): route on embedding_token_capacity() -
	# unlimited capacity embeds each resource's ordered pieces as ONE call.
	flat_texts = [piece.embed_text for _, _, _, pieces in plans for piece in pieces]
	embeddings = await embed_texts(flat_texts, session, input_type="document")
	chunks: list[Chunk] = []
	cursor = 0
	for resource, rid, fingerprint, pieces in plans:
		await remove_vectorized_resource(spec, rid, session)
		extra = (extra_metadata_by_id or {}).get(rid) or {}
		for piece in pieces:
			embedding = embeddings[cursor]
			cursor += 1
			chunks.append(
				build_chunk(
					spec,
					resource,
					embedding,
					extra_metadata={**extra, **piece.metadata},
					content=piece.content,
					chunk_index=piece.chunk_index,
					chunk_count=piece.chunk_count,
					fingerprint=fingerprint,
				)
			)
	await upsert_chunks(chunks=chunks, session=session)
	return len(plans)


# ACL sync: DB -> qdrant metadata for types with per-chunk ACL fields.
# principal resolution lives in authorization.metadata.


async def sync_resource_refs_vector_acl(
	resource_refs: list[tuple[ResourceType, TypeID]],
	session: AsyncSession,
) -> None:
	"""patch ACL payloads for concrete resource references.

	descendants are deliberately not walked: a chunk's stamped revision
	aggregates its resource's own revision with every ancestor's, so an
	ancestor-only change already makes descendant stamps differ and the ACL
	staleness sweep repairs them.
	"""
	resources_by_type: dict[ResourceType, list[str]] = {}
	for resource_type, resource_id in resource_refs:
		resources_by_type.setdefault(resource_type, []).append(str(resource_id))
	for resource_type, resource_ids in resources_by_type.items():
		await _sync_resource_vector_acl_payloads(resource_ids, resource_type, session)


async def _sync_resource_vector_acl_payloads(
	resource_ids: list[str],
	resource_type: ResourceType,
	session: AsyncSession,
) -> None:
	"""sync acl metadata for multiple resources in parallel.

	fetches all access rules for all resource ids in ONE db query then
	fires parallel qdrant update calls - optimized for bulk acl changes.
	"""
	if not resource_ids:
		return
	if resource_type not in ACL_SYNC_VECTOR_CHUNK_RESOURCE_TYPES:
		return
	unique_resource_ids = list(dict.fromkeys(resource_ids))
	acl_by_id = await fetch_bulk_acl_metadata(
		unique_resource_ids,
		resource_type,
		session,
	)
	coll = await get_collection(session)
	vs = get_vectorstore(collection=coll)

	async def _sync_one(rid: str) -> None:
		payload: dict[str, object] = {
			key: value for key, value in acl_by_id[rid].items()
		}
		for target in _acl_sync_chunk_filters(resource_type, rid):
			await vs.update(target, payload=payload)

	await map_concurrently(
		_sync_one,
		unique_resource_ids,
		limit=_VECTOR_ACL_UPDATE_CONCURRENCY,
	)


async def sync_resource_vector_payload(
	resource_ids: list[str],
	resource_type: ResourceType,
	payload_by_id: Mapping[str, Mapping[str, object]],
	session: AsyncSession,
) -> None:
	"""patch arbitrary filterable payload fields on a resource's chunks.

	same mechanism as the acl sync (payload-only ``vs.update``: vectors and
	other metadata are untouched, no re-embedding), for fields the caller
	resolves itself - e.g. per-user thread state. silent no-op for resources
	that were never vectorized.
	"""
	unique_resource_ids = [
		rid for rid in dict.fromkeys(resource_ids) if rid in payload_by_id
	]
	if not unique_resource_ids:
		return
	coll = await get_collection(session)
	vs = get_vectorstore(collection=coll)

	async def _sync_one(rid: str) -> None:
		payload: dict[str, object] = dict(payload_by_id[rid])
		for target in _acl_sync_chunk_filters(resource_type, rid):
			await vs.update(target, payload=payload)

	await map_concurrently(
		_sync_one,
		unique_resource_ids,
		limit=_VECTOR_ACL_UPDATE_CONCURRENCY,
	)


def _acl_sync_chunk_filters(
	resource_type: ResourceType,
	resource_id: str,
) -> list[ChunkFilter]:
	chunk_resource_types = ACL_SYNC_VECTOR_CHUNK_RESOURCE_TYPES.get(resource_type)
	if chunk_resource_types is None:
		return []
	direct_resource_types: list[VectorChunkResourceType] = []
	targets: list[ChunkFilter] = []
	for chunk_resource_type in chunk_resource_types:
		parent_resource_type = VECTOR_CHUNK_PARENT_RESOURCE_TYPES.get(
			chunk_resource_type
		)
		if parent_resource_type is None:
			direct_resource_types.append(chunk_resource_type)
			continue
		targets.append(
			parent_resource_filter(
				parent_resource_type,
				resource_id,
				resource_types=[chunk_resource_type],
			)
		)
	if direct_resource_types:
		targets.append(
			resource_types_filter(
				direct_resource_types,
				resource_id=resource_id,
			)
		)
	return targets
