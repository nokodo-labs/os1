"""file content vectorization pipeline."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from api.models.file import File
from api.permissions import ResourceType
from api.settings import settings
from api.storage import get_storage_backend
from api.v1.service import vectorstores as vectorstore_service
from api.v1.service.authorization import fetch_acl_metadata
from api.v1.service.chat.models import (
	TaskChatModel,
	resolve_task_chat_model_config,
)
from api.v1.service.embeddings import embed_texts
from api.v1.service.files.modalities import (
	file_input_modality,
	is_direct_model_text_candidate,
	should_try_model_text,
)
from api.v1.service.files.vectorization import (
	_build_file_content_chunk,
	remove_file_vectors,
)
from nokodo_ai import Chunker, Loader
from nokodo_ai.chunkers import ContentChunk
from nokodo_ai.loaders import File as SDKFile
from nokodo_ai.loaders import Text
from nokodo_ai.types.json import JSONObject, JSONValue
from nokodo_ai.utils.files import file_metadata


FileContentChunk = ContentChunk
_AUTO_LOCAL_LOADERS = ("plain", "markitdown")


@dataclass(slots=True)
class FileContentChunkBatch:
	"""result of the file-to-content-chunks pipeline."""

	chunks: list[FileContentChunk]
	text_loadable: bool
	loader: str
	chunker: str
	skipped_reason: str | None = None


async def load_file_content_chunks(
	file: File,
	session: AsyncSession | None = None,
) -> FileContentChunkBatch:
	"""load and chunk file body text for content vectorization."""
	raw = await _read_limited_bytes(file)
	chat_model = (
		await resolve_content_loader_chat_model(session)
		if session is not None
		else None
	)
	loaded = await load_sdk_file_text(
		SDKFile(
			data=raw,
			filename=file.filename,
			mime_type=file.mime_type,
			metadata={"resource_id": str(file.id)},
		),
		chat_model=chat_model,
	)
	chunker = _chunker_adapter_name(loaded)
	chunks = await chunk_loaded_text(loaded)
	return FileContentChunkBatch(
		chunks=chunks,
		text_loadable=loaded.status == "loaded",
		loader=loaded.source,
		chunker=chunker,
		skipped_reason=loaded.skipped_reason,
	)


async def vectorize_file_content(
	file: File,
	session: AsyncSession,
	content_chunks: list[FileContentChunk] | None = None,
) -> FileContentChunkBatch:
	"""load, chunk, embed, and vectorize file body contents."""
	if content_chunks is None:
		batch = await load_file_content_chunks(file, session)
		chunks = batch.chunks
	else:
		chunker = settings.assets.content_vectorization.chunking_algorithm
		batch = FileContentChunkBatch(
			chunks=content_chunks,
			text_loadable=bool(content_chunks),
			loader=settings.assets.content_vectorization.loader,
			chunker=chunker,
		)
		chunks = content_chunks
	await remove_file_vectors(
		str(file.id),
		session,
		include_file_vector=False,
	)
	if not chunks:
		return batch
	acl_metadata = await fetch_acl_metadata(str(file.id), ResourceType.FILE, session)
	texts = [_content_embedding_text(file, chunk) for chunk in chunks]
	embeddings = await embed_texts(texts, session)
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
			},
		)
		for index, (chunk, embedding) in enumerate(zip(chunks, embeddings))
	]
	await vectorstore_service.upsert_chunks(chunks=vector_chunks, session=session)
	return batch


async def chunk_loaded_text(loaded: Text) -> list[FileContentChunk]:
	"""chunk already-loaded content with current content vectorization settings."""
	return await Chunker.create(
		adapter=_chunker_adapter_name(loaded),
		target_tokens=settings.assets.content_vectorization.target_tokens,
		overlap_tokens=settings.assets.content_vectorization.overlap_tokens,
		max_chunks=settings.assets.content_vectorization.max_chunks,
	).chunk(loaded)


async def load_sdk_file_text(
	file: SDKFile,
	chat_model: TaskChatModel | None = None,
) -> Text:
	"""load text from an SDK file using API-owned routing policy."""
	loader = settings.assets.content_vectorization.loader
	if loader == "auto":
		return await _load_auto_file_text(file, chat_model)
	if loader == "chatmodel":
		return await _load_chatmodel_file_text(file, chat_model)
	return await Loader.create(adapter=loader).load(file)


async def resolve_content_loader_chat_model(
	session: AsyncSession,
) -> TaskChatModel | None:
	"""resolve the optional ChatModel used by model-backed file text loaders.

	Missing task-model configuration is allowed here: plain and structured text
	loaders still work, while model-backed paths return unsupported with a
	factual skipped reason.
	"""
	try:
		return await resolve_task_chat_model_config(session, "asset_text_extraction")
	except ValueError:
		return None


async def _load_auto_file_text(
	file: SDKFile,
	chat_model: TaskChatModel | None,
) -> Text:
	"""route a file through API local-first text extraction policy."""
	if is_direct_model_text_candidate(file.filename, file.mime_type):
		return await _load_chatmodel_file_text(file, chat_model)
	for loader in _AUTO_LOCAL_LOADERS:
		loaded = await Loader.create(adapter=loader).load(file)
		if loaded.status == "loaded":
			if should_try_model_text(
				file.filename,
				file.mime_type,
				loaded.content,
				len(file.data),
			):
				return await _load_chatmodel_file_text(file, chat_model)
			return loaded
	if should_try_model_text(file.filename, file.mime_type, "", len(file.data)):
		return await _load_chatmodel_file_text(file, chat_model)
	return _unsupported_text(file, "auto", "unsupported_type")


async def _load_chatmodel_file_text(
	file: SDKFile,
	chat_model: TaskChatModel | None,
) -> Text:
	"""run ChatModel-backed text extraction after API capability checks."""
	modality = file_input_modality(file.filename, file.mime_type)
	if chat_model is None:
		return _unsupported_text(file, "chatmodel_loader", "missing_chat_model")
	if modality.value not in chat_model.input_modalities:
		model_input_modalities: list[JSONValue] = []
		model_input_modalities.extend(sorted(chat_model.input_modalities))
		extra_metadata: JSONObject = {
			"model_input_modalities": model_input_modalities,
		}
		return _unsupported_text(
			file,
			"chatmodel_loader",
			"unsupported_input_modality",
			extra_metadata,
		)
	loaded = await Loader.create(
		adapter="chatmodel",
		chat_model=chat_model.chat_model,
	).load(file)
	loaded.metadata = {
		**loaded.metadata,
		"input_modality": modality.value,
	}
	return loaded


def _unsupported_text(
	file: SDKFile,
	source: str,
	skipped_reason: str,
	extra_metadata: JSONObject | None = None,
) -> Text:
	"""build a factual unsupported text load result for API routing failures."""
	modality = file_input_modality(file.filename, file.mime_type)
	metadata: JSONObject = {
		**file_metadata(file.filename, file.mime_type, file.metadata),
		"input_modality": modality.value,
		"text_kind": "file_text",
	}
	if extra_metadata:
		metadata.update(extra_metadata)
	return Text(
		content="",
		status="unsupported",
		source=source,
		metadata=metadata,
		skipped_reason=skipped_reason,
	)


def _chunker_adapter_name(loaded: Text) -> str:
	"""select the concrete SDK chunker adapter for loaded text."""
	chunking_algorithm = settings.assets.content_vectorization.chunking_algorithm
	if chunking_algorithm != "auto":
		return chunking_algorithm
	if loaded.format == "markdown":
		return "markdown"
	return "recursive"


async def _read_limited_bytes(file: File) -> bytes:
	"""read file bytes from storage, honoring the configured byte cap."""
	limit = settings.assets.content_vectorization.max_bytes
	backend = get_storage_backend(file.storage_backend)
	if not await backend.exists(file.storage_key):
		raise FileNotFoundError(
			f"storage object missing: {file.storage_key!r} "
			f"on backend {file.storage_backend!r}"
		)
	stream = await backend.get(file.storage_key)
	parts: list[bytes] = []
	total = 0
	async for part in stream:
		if limit is None:
			parts.append(part)
			continue
		if total >= limit:
			break
		remaining = limit - total
		parts.append(part[:remaining])
		total += min(len(part), remaining)
	return b"".join(parts)


def _content_embedding_text(file: File, chunk: FileContentChunk) -> str:
	"""combine filename, description, and chunk text for embedding."""
	parts = [file.filename or "file"]
	if file.description:
		parts.append(file.description)
	parts.append(chunk.text)
	return "\n".join(part for part in parts if part).strip()
