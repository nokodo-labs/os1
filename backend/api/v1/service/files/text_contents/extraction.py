"""text content extraction: file bytes -> normalized text + chunks.

the isolated producer of a file's body text. owns the loader/chunker routing
and the API policy that decides between local and model-backed extraction. it
knows nothing about vectors, descriptions, or storage of the result - those are
parallel consumers of what this module produces.
"""

import logging
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from api.models.file import File
from api.models.model import InputModality
from api.settings import settings
from api.storage import get_storage_backend
from api.v1.service.chat.models import (
	TaskChatModel,
	resolve_task_chat_model_config,
)
from api.v1.service.embeddings import embedding_token_capacity
from api.v1.service.files.modalities import file_input_modality
from nokodo_ai import Chunker, Loader
from nokodo_ai.chunkers import ContentChunk
from nokodo_ai.loaders import File as SDKFile
from nokodo_ai.loaders import Text
from nokodo_ai.types.json import JSONObject, JSONValue
from nokodo_ai.utils.error_mapping import error_text, status_code_from_attrs
from nokodo_ai.utils.files import file_metadata


logger = logging.getLogger(__name__)


FileContentChunk = ContentChunk
_AUTO_LOCAL_LOADERS = ("plain", "markitdown")

# provider responses that mean the input itself is unusable. retrying never
# helps, so the file is marked permanently skipped instead of flooding the
# worker with tracebacks and endless re-dispatches.
_PERMANENT_PROVIDER_STATUS = frozenset({400, 413, 415, 422})
_PERMANENT_EXTRACTION_TEXT_MARKERS = (
	"truncated",
	"invalid image",
	"corrupt",
	"unsupported image",
)

# document text density thresholds: a document loader that returns too little
# text (or too sparse for its size) is treated as scanned, so model extraction
# is tried instead.
_MIN_DOCUMENT_TEXT_CHARS = 40
_MIN_DOCUMENT_TEXT_DENSITY_BYTES = 64 * 1024
_MIN_DOCUMENT_TEXT_CHARS_PER_KIB = 4.0


@dataclass(slots=True)
class FileContentChunkBatch:
	"""result of the file-to-content-chunks pipeline."""

	chunks: list[FileContentChunk]
	text_loadable: bool
	loader: str
	chunker: str
	skipped_reason: str | None = None
	# verbatim extracted text before chunking. media files use this as their
	# description directly; text-extractable files summarize it.
	content: str = ""


# extraction routing policy


def is_direct_model_text_candidate(
	filename: str | None,
	mime_type: str | None,
) -> bool:
	"""return whether local text loaders should be skipped."""
	return file_input_modality(filename, mime_type) in {
		InputModality.IMAGES,
		InputModality.AUDIO,
		InputModality.VIDEO,
	}


def should_try_model_text(
	filename: str | None,
	mime_type: str | None,
	extracted_text: str,
	size_bytes: int | None = None,
) -> bool:
	"""return whether API policy should try model-backed file text extraction."""
	modality = file_input_modality(filename, mime_type)
	if modality in {InputModality.IMAGES, InputModality.AUDIO, InputModality.VIDEO}:
		return True
	if modality != InputModality.DOCUMENTS:
		return False
	meaningful_chars = len(_meaningful_text(extracted_text))
	if meaningful_chars < _MIN_DOCUMENT_TEXT_CHARS:
		return True
	if size_bytes is None or size_bytes < _MIN_DOCUMENT_TEXT_DENSITY_BYTES:
		return False
	chars_per_kib = meaningful_chars / (size_bytes / 1024)
	return chars_per_kib < _MIN_DOCUMENT_TEXT_CHARS_PER_KIB


def _meaningful_text(text: str) -> str:
	"""return only alphanumeric characters for density heuristics."""
	return "".join(char for char in text if char.isalnum())


def _is_permanent_extraction_error(exc: Exception) -> bool:
	"""classify a model extraction failure as permanent (vs retryable)."""
	if status_code_from_attrs(exc) in _PERMANENT_PROVIDER_STATUS:
		return True
	text = error_text(exc).lower()
	return any(marker in text for marker in _PERMANENT_EXTRACTION_TEXT_MARKERS)


# extraction pipeline


async def load_file_content_chunks(
	file: File,
	session: AsyncSession | None = None,
) -> FileContentChunkBatch:
	"""load and chunk file body text."""
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
	chunks = await chunk_loaded_text(loaded, session)
	return FileContentChunkBatch(
		chunks=chunks,
		text_loadable=loaded.status == "loaded",
		loader=loaded.source,
		chunker=chunker,
		skipped_reason=loaded.skipped_reason,
		content=loaded.content,
	)


async def chunk_loaded_text(
	loaded: Text,
	session: AsyncSession | None = None,
) -> list[FileContentChunk]:
	"""chunk already-loaded content with current content settings"""
	cfg = settings.assets.content_vectorization
	target_tokens = cfg.target_tokens
	overlap_tokens = cfg.overlap_tokens
	capacity = await embedding_token_capacity(session)
	if capacity is not None and target_tokens > capacity:
		target_tokens = capacity
		overlap_tokens = min(overlap_tokens, target_tokens // 2)
	return await Chunker.create(
		adapter=_chunker_adapter_name(loaded),
		target_tokens=target_tokens,
		overlap_tokens=overlap_tokens,
		max_chunks=cfg.max_chunks,
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
	try:
		loaded = await Loader.create(
			adapter="chatmodel",
			chat_model=chat_model.chat_model,
		).load(file)
	except Exception as exc:
		if not _is_permanent_extraction_error(exc):
			raise
		status = status_code_from_attrs(exc)
		logger.warning(
			"chatmodel file extraction permanently skipped "
			"file=%s modality=%s status=%s",
			file.metadata.get("resource_id"),
			modality.value,
			status,
		)
		return _unsupported_text(
			file,
			"chatmodel_loader",
			"permanent_provider_error",
			{"provider_status": status},
		)
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
