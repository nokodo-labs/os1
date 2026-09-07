"""content vectors: embed text chunks and search them.

owns the vector-database side of the text content sub-resource: turning the
extracted chunks into content vectors (with input fingerprinting so re-imports
are no-ops) and querying them for a single file. the extracted text itself is
produced by extraction and stored by store; this module consumes both.
"""

import logging
from collections.abc import Mapping
from dataclasses import dataclass

from sqlalchemy import ColumnElement, Integer, and_, cast, or_
from sqlalchemy.ext.asyncio import AsyncSession

from api.constants import PRIVATE_METADATA_KEY
from api.models.file import File
from api.permissions import ResourceType
from api.settings import settings
from api.v1.service.authentication import Principal
from api.v1.service.authorization import fetch_bulk_acl_metadata
from api.v1.service.embeddings import embed_text, embed_texts
from api.v1.service.files.metadata import (
	FILE_CONTENT_RESOURCE_TYPE,
	FILE_RESOURCE_TYPE,
)
from api.v1.service.files.text_contents.extraction import (
	FileContentChunk,
	FileContentChunkBatch,
	chunk_loaded_text,
	load_file_content_chunks,
	resolve_content_loader_chat_model,
)
from api.v1.service.files.text_contents.store import (
	load_accessible_file,
	read_extracted_text,
)
from api.v1.service.vectorize import (
	CONFIG_FP_KEY,
	PIPELINE_VERSION_KEY,
	StaleBy,
	chunks_match_fingerprint,
	fingerprint_payload,
)
from api.v1.service.vectorstores import (
	child_resource_filter,
	delete,
	get_collection,
	parent_resource_filter,
	scroll_chunks,
	search,
	upsert_chunks,
)
from nokodo_ai.adapters.base.vectorstores import Chunk, ChunkSearchResult
from nokodo_ai.loaders import Text
from nokodo_ai.types.json import JSONObject, JSONValue
from nokodo_ai.utils.typeid import TypeID


logger = logging.getLogger(__name__)

CONTENT_VECTOR_FINGERPRINT_KEY = "content_vector_fingerprint"
"""private metadata key recording the content fingerprint of the last vectorization."""

CONTENT_VECTOR_PIPELINE_KEY = "content_vector_pipeline_v"
"""private metadata key holding the pipeline version of the last vectorization."""

CONTENT_VECTOR_CONFIG_KEY = "content_vector_config_fp"
"""private metadata key holding the config fingerprint of the last vectorization."""

CONTENT_VECTOR_COLLECTION_KEY = "content_vector_collection"
"""private metadata key holding the collection of the last vectorization."""

FILE_CONTENT_PIPELINE_VERSION = 1
"""provenance version stamped on vectorized files."""


@dataclass(slots=True)
class FileContentChunkHit:
	"""one content chunk matched by a query, with its position in the text."""

	text: str
	score: float
	chunk_index: int
	chunk_count: int
	line_start: int | None
	line_end: int | None
	char_start: int | None
	char_end: int | None


def _record_content_vector_state(
	file: File,
	fingerprint: str,
	config_fp: str,
	collection: str,
) -> None:
	"""persist content fingerprint and provenance stamps on the file row.

	lets verify treat a file as current even when it stored no chunks.
	"""
	file.set_metadata(
		private={
			**file.private_metadata,
			CONTENT_VECTOR_FINGERPRINT_KEY: fingerprint,
			CONTENT_VECTOR_PIPELINE_KEY: FILE_CONTENT_PIPELINE_VERSION,
			CONTENT_VECTOR_CONFIG_KEY: config_fp,
			CONTENT_VECTOR_COLLECTION_KEY: collection,
		}
	)


def file_content_fingerprint(file: File) -> str:
	"""compute the content fingerprint for a file.

	digests the file bytes via checksum. model-backed loaders extract text
	non-deterministically, so the stored text cannot be reverse-checked;
	fingerprinting the input bytes instead means a re-import is a no-op.
	pipeline version and configuration are tracked as separate provenance
	stamps so their staleness can be policy-gated.
	"""
	return fingerprint_payload({"checksum": file.checksum_sha256 or ""})


async def file_content_config_fp(session: AsyncSession | None) -> str:
	"""fingerprint of the settings and loader model that shape file content vectors."""
	cfg = settings.assets.content_vectorization
	model = (
		await resolve_content_loader_chat_model(session)
		if session is not None
		else None
	)
	model_name = model.chat_model.model_name if model is not None else ""
	return fingerprint_payload(
		{
			"loader": cfg.loader,
			"chunker": cfg.chunking_algorithm,
			"target_tokens": cfg.target_tokens,
			"overlap_tokens": cfg.overlap_tokens,
			"max_chunks": cfg.max_chunks,
			"max_bytes": cfg.max_bytes,
			"model": model_name,
		}
	)


async def filter_unvectorized_files(
	files: list[File],
	session: AsyncSession,
) -> list[File]:
	"""return files whose content vectors are missing or stale.

	a file is kept (re-vectorized) when its content fingerprint fails to match
	what was already stored, or when it is provenance-stale per the
	file_contents revectorize triggers. content currency is established by the
	fingerprint recorded on the file row after a successful run, or by a
	matching, complete stored chunk set. files that legitimately yield no
	chunks (media without a model loader) rely on the row fingerprint, so
	re-importing them is a no-op once recorded.
	"""
	if not files:
		return []
	config_fp = await file_content_config_fp(session)
	collection = await get_collection(session)
	expected = {str(file.id): file_content_fingerprint(file) for file in files}
	chunks = await scroll_chunks(
		child_resource_filter(
			FILE_RESOURCE_TYPE,
			list(expected.keys()),
			FILE_CONTENT_RESOURCE_TYPE,
		),
		session,
	)
	grouped: dict[str, list[Chunk]] = {}
	for chunk in chunks:
		parent_id = chunk.metadata.get("parent_resource_id")
		if isinstance(parent_id, str):
			grouped.setdefault(parent_id, []).append(chunk)
	pending: list[File] = []
	for file in files:
		fid = str(file.id)
		private = file.private_metadata
		stored_fp = private.get(CONTENT_VECTOR_FINGERPRINT_KEY)
		content_current = stored_fp == expected[fid] or chunks_match_fingerprint(
			grouped.get(fid, []), expected[fid]
		)
		collection_current = private.get(CONTENT_VECTOR_COLLECTION_KEY) == collection
		if (
			not content_current
			or not collection_current
			or _file_provenance_stale(file, config_fp)
		):
			pending.append(file)
	return pending


def _file_provenance_stale(file: File, config_fp: str) -> bool:
	"""whether a content-current file is provenance-stale per the triggers."""
	triggers = settings.assets.revectorize.file_contents
	private = file.private_metadata
	if (
		triggers.on_pipeline_version
		and private.get(CONTENT_VECTOR_PIPELINE_KEY) != FILE_CONTENT_PIPELINE_VERSION
	):
		return True
	return (
		bool(triggers.on_config_change)
		and private.get(CONTENT_VECTOR_CONFIG_KEY) != config_fp
	)


def file_content_stale_predicate(
	by: StaleBy,
	config_fp: str | None = None,
) -> ColumnElement[bool]:
	"""SQL predicate matching vectorized files provenance-stale by one cause."""
	fingerprint_text = File.metadata_[
		(PRIVATE_METADATA_KEY, CONTENT_VECTOR_FINGERPRINT_KEY)
	].as_string()
	if by is StaleBy.PIPELINE_VERSION:
		version_text = File.metadata_[
			(PRIVATE_METADATA_KEY, CONTENT_VECTOR_PIPELINE_KEY)
		].as_string()
		return and_(
			fingerprint_text.is_not(None),
			or_(
				version_text.is_(None),
				cast(version_text, Integer) != FILE_CONTENT_PIPELINE_VERSION,
			),
		)
	if config_fp is None:
		raise ValueError("config staleness requires the current config fingerprint")
	config_text = File.metadata_[
		(PRIVATE_METADATA_KEY, CONTENT_VECTOR_CONFIG_KEY)
	].as_string()
	return and_(
		fingerprint_text.is_not(None),
		or_(config_text.is_(None), config_text != config_fp),
	)


async def vectorize_file_content(
	file: File,
	session: AsyncSession,
	content_chunks: list[FileContentChunk] | None = None,
	force: bool = False,
) -> FileContentChunkBatch:
	"""load, chunk, embed, and vectorize file body contents.

	with force=False a content-current file is left untouched unless it is
	provenance-stale per the file_contents revectorize triggers, so a
	re-dispatch or re-import never reruns extraction (a vision model call for
	media). pass force=True to rebuild vectors regardless, or pass
	content_chunks to vectorize a known chunk set.
	"""
	fingerprint = file_content_fingerprint(file)
	config_fp = await file_content_config_fp(session)
	collection = await get_collection(session)
	if content_chunks is None:
		if not force:
			private = file.private_metadata
			content_current = private.get(CONTENT_VECTOR_FINGERPRINT_KEY) == fingerprint
			collection_current = (
				private.get(CONTENT_VECTOR_COLLECTION_KEY) == collection
			)
			if (
				content_current
				and collection_current
				and not _file_provenance_stale(file, config_fp)
			):
				cfg = settings.assets.content_vectorization
				return FileContentChunkBatch(
					chunks=[],
					text_loadable=False,
					loader=cfg.loader,
					chunker=cfg.chunking_algorithm,
					skipped_reason="already_current",
				)
		batch = await load_file_content_chunks_reusing_stored_text(file, session)
		chunks = batch.chunks
	else:
		chunker = settings.assets.content_vectorization.chunking_algorithm
		batch = FileContentChunkBatch(
			chunks=content_chunks,
			text_loadable=bool(content_chunks),
			loader=settings.assets.content_vectorization.loader,
			chunker=chunker,
			content="\n\n".join(chunk.text for chunk in content_chunks),
		)
		chunks = content_chunks
	await delete(
		target=parent_resource_filter(
			FILE_RESOURCE_TYPE,
			str(file.id),
			resource_types=[FILE_CONTENT_RESOURCE_TYPE],
		),
		session=session,
	)
	if not chunks:
		_record_content_vector_state(file, fingerprint, config_fp, collection)
		return batch
	acl_metadata = (
		await fetch_bulk_acl_metadata([str(file.id)], ResourceType.FILE, session)
	)[str(file.id)]
	# TODO(contextualized-embeddings): route on embedding_token_capacity() -
	# unlimited capacity embeds the whole chunk list as one document call.
	texts = [_content_embedding_text(file, chunk) for chunk in chunks]
	embeddings = await embed_texts(texts, session, input_type="document")
	vector_chunks = [
		_build_file_content_chunk(
			file=file,
			content=texts[index],
			embedding=embedding,
			chunk_index=chunk.index,
			chunk_count=chunk.total,
			extra_metadata={
				**acl_metadata,
				**chunk.metadata,
				"text_loader": batch.loader,
				"chunking_algorithm": batch.chunker,
				"vec_fingerprint": fingerprint,
				PIPELINE_VERSION_KEY: FILE_CONTENT_PIPELINE_VERSION,
				CONFIG_FP_KEY: config_fp,
			},
		)
		for index, (chunk, embedding) in enumerate(zip(chunks, embeddings))
	]
	await upsert_chunks(chunks=vector_chunks, session=session)
	_record_content_vector_state(file, fingerprint, config_fp, collection)
	return batch


async def load_file_content_chunks_reusing_stored_text(
	file: File,
	session: AsyncSession,
) -> FileContentChunkBatch:
	"""chunk the stored extracted text, extracting from source only if absent.

	extraction can spend model calls (vision or chat) for media, so the stored
	text is reused whenever it exists. the returned batch reports which path
	ran through its ``loader``.
	"""
	stored_text = await read_extracted_text(file, session)
	if stored_text is None:
		return await load_file_content_chunks(file, session)
	loaded = Text(
		content=stored_text,
		status="loaded",
		source="stored_extraction",
	)
	chunks = await chunk_loaded_text(loaded, session)
	return FileContentChunkBatch(
		chunks=chunks,
		text_loadable=True,
		loader=loaded.source,
		chunker=settings.assets.content_vectorization.chunking_algorithm,
		content=stored_text,
	)


def _content_embedding_text(file: File, chunk: FileContentChunk) -> str:
	"""combine filename, description, and chunk text for embedding."""
	parts = [file.filename or "file"]
	if file.description:
		parts.append(file.description)
	parts.append(chunk.text)
	return "\n".join(part for part in parts if part).strip()


def _build_file_content_chunk(
	file: File,
	content: str,
	embedding: list[float],
	chunk_index: int,
	chunk_count: int,
	extra_metadata: Mapping[str, object] | None = None,
) -> Chunk:
	"""build a vector chunk for extracted file body content."""
	metadata: JSONObject = {
		"resource_type": FILE_CONTENT_RESOURCE_TYPE.value,
		"parent_resource_type": FILE_RESOURCE_TYPE.value,
		"parent_resource_id": str(file.id),
		"owner_id": str(file.owner_id),
		"chunk_index": chunk_index,
		"chunk_count": chunk_count,
	}
	metadata.update(_json_metadata(extra_metadata))
	return Chunk(
		id=f"{file.id}:content:{chunk_index}",
		content=content,
		embedding=embedding,
		metadata=metadata,
	)


def _json_metadata(values: Mapping[str, object] | None) -> JSONObject:
	metadata: JSONObject = {}
	if values is None:
		return metadata
	for key, value in values.items():
		json_value = _json_value(value)
		if json_value is not None:
			metadata[key] = json_value
	return metadata


def _json_value(value: object) -> JSONValue | None:
	if value is None or isinstance(value, (str, int, float, bool)):
		return value
	if isinstance(value, list):
		items: list[JSONValue] = []
		for item in value:
			json_item = _json_value(item)
			if json_item is not None:
				items.append(json_item)
		return items
	if isinstance(value, dict):
		nested: JSONObject = {}
		for key, item in value.items():
			json_item = _json_value(item)
			if json_item is not None:
				nested[str(key)] = json_item
		return nested
	return str(value)


async def query_file_content(
	file_id: TypeID,
	query: str,
	session: AsyncSession,
	principal: Principal,
	limit: int = 5,
) -> list[FileContentChunkHit]:
	"""return the top matching content chunks for one file with line ranges.

	chunk text is sliced from the stored body by char range, so it is clean text
	rather than the embedding input. requires read access.
	"""
	file = await load_accessible_file(file_id, session, principal)
	query_embedding = await embed_text(text=query, session=session, input_type="query")
	results = await search(
		session=session,
		query=query_embedding,
		text_query=query,
		limit=limit,
		query_filter=child_resource_filter(
			FILE_RESOURCE_TYPE,
			[str(file_id)],
			FILE_CONTENT_RESOURCE_TYPE,
		),
	)
	full_text = await read_extracted_text(file, session)
	return [_chunk_hit(hit, full_text) for hit in results]


def _chunk_hit(hit: ChunkSearchResult, full_text: str | None) -> FileContentChunkHit:
	"""build a content chunk hit, slicing clean text from the stored body."""
	char_start = _int_or_none(hit.metadata.get("char_start"))
	char_end = _int_or_none(hit.metadata.get("char_end"))
	text = ""
	if (
		full_text is not None
		and char_start is not None
		and char_end is not None
		and 0 <= char_start < char_end <= len(full_text)
	):
		text = full_text[char_start:char_end].strip()
	if not text:
		# blob missing or range unusable: fall back to the stored chunk content.
		text = hit.content.strip()
	return FileContentChunkHit(
		text=text,
		score=hit.score,
		chunk_index=_int_or_none(hit.metadata.get("chunk_index")) or 0,
		chunk_count=_int_or_none(hit.metadata.get("chunk_count")) or 0,
		line_start=_int_or_none(hit.metadata.get("line_start")),
		line_end=_int_or_none(hit.metadata.get("line_end")),
		char_start=char_start,
		char_end=char_end,
	)


def _int_or_none(value: JSONValue) -> int | None:
	"""coerce a JSON metadata value to int when it is integral."""
	if isinstance(value, bool):
		return None
	if isinstance(value, int):
		return value
	return None
