"""tests for file content vectorization primitives."""

from __future__ import annotations

import base64
from collections.abc import AsyncIterator, Awaitable
from typing import Literal, overload

import pytest
from pydantic import PrivateAttr
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.file import File, FileSource, FileStatus
from api.settings import settings
from api.storage.base import FileInfo, MimeType, StorageBackend
from api.v1.service.chat.models import TaskChatModel
from api.v1.service.files import content_vectorization as content_vectorization_service
from api.v1.service.files import processing as processing_service
from api.v1.service.files.content_vectorization import (
	FileContentChunkBatch,
	chunk_loaded_text,
	load_file_content_chunks,
	load_sdk_file_text,
	vectorize_file_content,
)
from api.v1.service.files.description import _content_excerpt, _truncate_description
from api.v1.service.files.metadata import FILE_CONTENT_RESOURCE_TYPE, FILE_RESOURCE_TYPE
from api.v1.service.files.modalities import should_try_model_text
from api.v1.service.files.search import _file_id_for_hit
from api.v1.service.files.vectorization import FILE_SPEC, _build_file_content_chunk
from api.v1.service.search.grouping import ResourceHitGroup, group_resource_hits
from api.v1.service.vectorize import build_chunk
from nokodo_ai.adapters.base.chat import BaseChatAdapter, ChatGenerationParams
from nokodo_ai.adapters.base.vectorstores import Chunk as VectorChunk
from nokodo_ai.adapters.base.vectorstores import ChunkSearchResult
from nokodo_ai.chat_models import ChatModel
from nokodo_ai.chunkers import ContentChunk
from nokodo_ai.loaders import File as SDKFile
from nokodo_ai.loaders import Text
from nokodo_ai.messages import (
	AssistantMessage,
	FileContent,
	ImageContent,
	Message,
	UserMessage,
)
from nokodo_ai.tool import ToolDefinition
from nokodo_ai.utils.typeid import TypeID, new_typeid


class _ExtractionChatAdapter(BaseChatAdapter):
	type: Literal["test.file_extraction"] = "test.file_extraction"
	_response: str = PrivateAttr(default="")
	_messages: list[Message] = PrivateAttr(default_factory=list)

	def __init__(self, response: str) -> None:
		super().__init__()
		self._response = response

	@property
	def messages(self) -> list[Message]:
		return self._messages

	@overload
	def generate(
		self,
		messages: list[Message],
		model: str,
		stream: Literal[False] = False,
		tools: list[ToolDefinition] = [],
		params: ChatGenerationParams | None = None,
	) -> Awaitable[AssistantMessage]: ...

	@overload
	def generate(
		self,
		messages: list[Message],
		model: str,
		stream: Literal[True],
		tools: list[ToolDefinition] = [],
		params: ChatGenerationParams | None = None,
	) -> AsyncIterator[AssistantMessage]: ...

	def generate(
		self,
		messages: list[Message],
		model: str,
		stream: bool = False,
		tools: list[ToolDefinition] = [],
		params: ChatGenerationParams | None = None,
	) -> Awaitable[AssistantMessage] | AsyncIterator[AssistantMessage]:
		self._messages = messages
		if stream:

			async def empty_stream() -> AsyncIterator[AssistantMessage]:
				if False:
					yield AssistantMessage.from_text("")

			return empty_stream()

		async def response() -> AssistantMessage:
			return AssistantMessage.from_text(self._response)

		return response()


class _StatusError(Exception):
	def __init__(self, status_code: int) -> None:
		super().__init__("provider rejected input")
		self.status_code = status_code


class _RaisingChatAdapter(BaseChatAdapter):
	type: Literal["test.raising_extraction"] = "test.raising_extraction"
	_exc: Exception = PrivateAttr()

	def __init__(self, exc: Exception) -> None:
		super().__init__()
		self._exc = exc

	@property
	def messages(self) -> list[Message]:
		return []

	@overload
	def generate(
		self,
		messages: list[Message],
		model: str,
		stream: Literal[False] = False,
		tools: list[ToolDefinition] = [],
		params: ChatGenerationParams | None = None,
	) -> Awaitable[AssistantMessage]: ...

	@overload
	def generate(
		self,
		messages: list[Message],
		model: str,
		stream: Literal[True],
		tools: list[ToolDefinition] = [],
		params: ChatGenerationParams | None = None,
	) -> AsyncIterator[AssistantMessage]: ...

	def generate(
		self,
		messages: list[Message],
		model: str,
		stream: bool = False,
		tools: list[ToolDefinition] = [],
		params: ChatGenerationParams | None = None,
	) -> Awaitable[AssistantMessage] | AsyncIterator[AssistantMessage]:
		exc = self._exc
		if stream:

			async def raising_stream() -> AsyncIterator[AssistantMessage]:
				raise exc
				yield AssistantMessage.from_text("")  # pragma: no cover

			return raising_stream()

		async def raising() -> AssistantMessage:
			raise exc

		return raising()


def _image_chat_model(adapter: BaseChatAdapter) -> TaskChatModel:
	return TaskChatModel(
		chat_model=ChatModel.model_construct(model_name="extractor", adapter=adapter),
		input_modalities=frozenset({"images"}),
	)


class _MemoryStorageBackend(StorageBackend):
	def __init__(self, data: bytes) -> None:
		super().__init__("memory")
		self.data = data

	async def put(
		self,
		key: str,
		data: bytes | AsyncIterator[bytes],
		content_type: MimeType,
	) -> None:
		if isinstance(data, bytes):
			self.data = data
		else:
			parts: list[bytes] = []
			async for chunk in data:
				parts.append(chunk)
			self.data = b"".join(parts)

	async def get(self, key: str) -> AsyncIterator[bytes]:
		return _single_chunk(self.data)

	async def delete(self, key: str) -> None:
		self.data = b""

	async def exists(self, key: str) -> bool:
		return True

	async def stat(self, key: str) -> FileInfo | None:
		return None

	async def copy(self, src_key: str, dst_key: str) -> None:
		return None

	async def get_url(self, key: str, expires_in: int | None = None) -> str | None:
		return None


async def _single_chunk(data: bytes) -> AsyncIterator[bytes]:
	yield data


def _task_chat_model(
	response: str,
	input_modalities: frozenset[str] = frozenset(
		{"documents", "images", "audio", "video"}
	),
) -> tuple[TaskChatModel, _ExtractionChatAdapter]:
	adapter = _ExtractionChatAdapter(response)
	chat_model = ChatModel.model_construct(model_name="extractor", adapter=adapter)
	return (
		TaskChatModel(chat_model=chat_model, input_modalities=input_modalities),
		adapter,
	)


def _file_record(
	filename: str,
	mime_type: str,
	data: bytes,
) -> File:
	return File(
		id=new_typeid("file"),
		owner_id=new_typeid("user"),
		source=FileSource.UPLOAD,
		storage_backend="memory",
		storage_key=f"tests/{filename}",
		filename=filename,
		mime_type=mime_type,
		size_bytes=len(data),
		checksum_sha256=None,
		description="stored file",
		status=FileStatus.AVAILABLE,
		projects=[],
	)


def _user_message(adapter: _ExtractionChatAdapter) -> UserMessage:
	message = adapter.messages[1]
	assert isinstance(message, UserMessage)
	return message


async def test_content_chunks_are_indexed_with_total(monkeypatch) -> None:
	monkeypatch.setattr(settings.assets.content_vectorization, "target_tokens", 50)
	monkeypatch.setattr(settings.assets.content_vectorization, "overlap_tokens", 5)
	monkeypatch.setattr(settings.assets.content_vectorization, "max_chunks", 20)
	monkeypatch.setattr(
		settings.assets.content_vectorization,
		"chunking_algorithm",
		"recursive",
	)
	text = "\n\n".join(f"paragraph {index} " + "word " * 80 for index in range(8))

	chunks = await chunk_loaded_text(
		Text(
			content=text,
			status="loaded",
			source="plain",
			metadata={"mime_type": "text/plain"},
		)
	)

	assert len(chunks) > 1
	assert [chunk.index for chunk in chunks] == list(range(len(chunks)))
	assert {chunk.total for chunk in chunks} == {len(chunks)}
	for chunk in chunks:
		line_start = chunk.metadata["line_start"]
		line_end = chunk.metadata["line_end"]
		assert isinstance(line_start, int)
		assert isinstance(line_end, int)
		assert line_start <= line_end


def test_file_vector_metadata_uses_file_resource_identity() -> None:
	file_id = new_typeid("file")
	owner_id = new_typeid("user")
	file = File(
		id=file_id,
		owner_id=owner_id,
		source=FileSource.UPLOAD,
		storage_backend="local",
		storage_key="file-key",
		filename="report.txt",
		mime_type="text/plain",
		size_bytes=100,
		checksum_sha256=None,
		description="quarterly report",
		status=FileStatus.AVAILABLE,
		projects=[],
	)

	chunk = build_chunk(FILE_SPEC, file, [0.1, 0.2])

	assert chunk.metadata["resource_type"] == FILE_RESOURCE_TYPE
	assert chunk.metadata["resource_id"] == str(file_id)
	assert chunk.metadata["owner_id"] == str(owner_id)
	assert chunk.metadata["chunk_index"] == 0
	assert chunk.metadata["chunk_count"] == 1
	assert "chunk_source" not in chunk.metadata
	assert "parent_resource_type" not in chunk.metadata
	assert "parent_resource_id" not in chunk.metadata


def test_file_content_chunk_metadata_uses_parent_resource_identity() -> None:
	file_id = new_typeid("file")
	owner_id = new_typeid("user")
	file = File(
		id=file_id,
		owner_id=owner_id,
		source=FileSource.UPLOAD,
		storage_backend="local",
		storage_key="file-key",
		filename="report.txt",
		mime_type="text/plain",
		size_bytes=100,
		checksum_sha256=None,
		description="quarterly report",
		status=FileStatus.AVAILABLE,
		projects=[],
	)

	chunk = _build_file_content_chunk(
		file=file,
		content="body text",
		embedding=[0.1, 0.2],
		chunk_index=2,
		chunk_count=7,
		extra_metadata={"line_start": 10, "line_end": 20},
	)

	assert chunk.metadata["resource_type"] == FILE_CONTENT_RESOURCE_TYPE
	assert "resource_id" not in chunk.metadata
	assert chunk.metadata["parent_resource_type"] == FILE_RESOURCE_TYPE
	assert chunk.metadata["parent_resource_id"] == str(file_id)
	assert chunk.metadata["owner_id"] == str(owner_id)
	assert chunk.metadata["chunk_index"] == 2
	assert chunk.metadata["chunk_count"] == 7
	assert chunk.metadata["line_start"] == 10
	assert chunk.metadata["line_end"] == 20
	assert "filename" not in chunk.metadata
	assert "mime_type" not in chunk.metadata
	assert "status" not in chunk.metadata
	assert "project_ids" not in chunk.metadata
	assert "chunk_source" not in chunk.metadata


def test_file_search_groups_content_hits_by_parent_file_id() -> None:
	file_id = str(new_typeid("file"))
	hits = [
		ChunkSearchResult(
			id="content-chunk",
			content="body match",
			embedding=[],
			score=0.9,
			metadata={
				"resource_type": FILE_CONTENT_RESOURCE_TYPE,
				"parent_resource_id": file_id,
				"chunk_index": 0,
				"chunk_count": 2,
			},
		),
		ChunkSearchResult(
			id="file-chunk",
			content="description match",
			embedding=[],
			score=0.7,
			metadata={
				"resource_type": FILE_RESOURCE_TYPE,
				"resource_id": file_id,
			},
		),
	]

	groups = group_resource_hits(hits, _file_id_for_hit)
	matched_payload = ResourceHitGroup(resource_id="x", hits=[hits[0]]).matched_chunks(
		1, 9999
	)[0]
	assert isinstance(matched_payload, dict)

	assert list(groups) == [file_id]
	assert len(groups[file_id].hits) == 2
	assert matched_payload["resource_type"] == FILE_CONTENT_RESOURCE_TYPE
	assert matched_payload["chunk_index"] == 0
	assert matched_payload["chunk_count"] == 2
	assert "chunk_source" not in matched_payload


async def test_api_auto_loader_routes_images_to_missing_chat_model_fact(
	monkeypatch,
) -> None:
	monkeypatch.setattr(settings.assets.content_vectorization, "loader", "auto")
	loaded = await load_sdk_file_text(
		SDKFile(data=b"", filename="scan.png", mime_type="image/png")
	)

	assert loaded.status == "unsupported"
	assert loaded.skipped_reason == "missing_chat_model"
	assert loaded.metadata["input_modality"] == "images"


async def test_api_auto_loader_rejects_unsupported_chat_model_modality(
	monkeypatch,
) -> None:
	monkeypatch.setattr(settings.assets.content_vectorization, "loader", "auto")
	chat_model = TaskChatModel(
		chat_model=ChatModel.model_construct(
			model_name="text-only",
			adapter=None,
		),
		input_modalities=frozenset({"text"}),
	)

	loaded = await load_sdk_file_text(
		SDKFile(data=b"image-bytes", filename="scan.png", mime_type="image/png"),
		chat_model=chat_model,
	)

	assert loaded.status == "unsupported"
	assert loaded.skipped_reason == "unsupported_input_modality"
	assert loaded.metadata["input_modality"] == "images"
	assert loaded.metadata["model_input_modalities"] == ["text"]


async def test_api_auto_loader_skips_permanent_provider_failure(monkeypatch) -> None:
	"""a 4xx input rejection is recorded as skipped, never retried."""
	monkeypatch.setattr(settings.assets.content_vectorization, "loader", "auto")
	chat_model = _image_chat_model(_RaisingChatAdapter(_StatusError(400)))

	loaded = await load_sdk_file_text(
		SDKFile(data=b"image-bytes", filename="scan.png", mime_type="image/png"),
		chat_model=chat_model,
	)

	assert loaded.status == "unsupported"
	assert loaded.skipped_reason == "permanent_provider_error"
	assert loaded.metadata["provider_status"] == 400


async def test_api_auto_loader_reraises_transient_provider_failure(
	monkeypatch,
) -> None:
	"""a 5xx/transient failure propagates so the sweep can retry it."""
	monkeypatch.setattr(settings.assets.content_vectorization, "loader", "auto")
	chat_model = _image_chat_model(_RaisingChatAdapter(_StatusError(503)))

	with pytest.raises(_StatusError):
		await load_sdk_file_text(
			SDKFile(data=b"image-bytes", filename="scan.png", mime_type="image/png"),
			chat_model=chat_model,
		)


async def test_api_auto_loader_keeps_text_files_on_local_loader(monkeypatch) -> None:
	monkeypatch.setattr(settings.assets.content_vectorization, "loader", "auto")
	loaded = await load_sdk_file_text(
		SDKFile(
			data=b"# release notes\n\n- shipped file search",
			filename="notes.md",
			mime_type="text/markdown",
		)
	)

	assert loaded.status == "loaded"
	assert loaded.source == "plain"
	assert loaded.format == "markdown"
	assert "file search" in loaded.content


@pytest.mark.parametrize(
	("filename", "mime_type", "modality", "content_type"),
	[
		("scan.png", "image/png", "images", ImageContent),
		("meeting.mp3", "audio/mpeg", "audio", FileContent),
		("demo.mp4", "video/mp4", "video", FileContent),
	],
)
async def test_api_auto_loader_routes_media_shapes_to_chatmodel_extraction(
	monkeypatch,
	filename: str,
	mime_type: str,
	modality: str,
	content_type: type[ImageContent] | type[FileContent],
) -> None:
	monkeypatch.setattr(settings.assets.content_vectorization, "loader", "auto")
	chat_model, adapter = _task_chat_model(
		f"# extracted {modality}\n\ninvoice total: $42"
	)

	loaded = await load_sdk_file_text(
		SDKFile(data=b"binary media bytes", filename=filename, mime_type=mime_type),
		chat_model=chat_model,
	)

	assert loaded.status == "loaded"
	assert loaded.source == "chatmodel_loader"
	assert loaded.content.startswith(f"# extracted {modality}")
	assert loaded.metadata["input_modality"] == modality
	user_message = _user_message(adapter)
	assert any(isinstance(part, content_type) for part in user_message.content)


async def test_api_auto_loader_falls_back_to_chatmodel_for_large_scanned_pdf(
	monkeypatch,
) -> None:
	monkeypatch.setattr(settings.assets.content_vectorization, "loader", "auto")
	chat_model, adapter = _task_chat_model(
		"# extracted document\n\nOCR text from scanned annual report."
	)
	data = b"%PDF-1.7\n" + b"0" * (128 * 1024)

	loaded = await load_sdk_file_text(
		SDKFile(data=data, filename="scan.pdf", mime_type="application/pdf"),
		chat_model=chat_model,
	)

	assert loaded.status == "loaded"
	assert loaded.source == "chatmodel_loader"
	assert "OCR text" in loaded.content
	assert loaded.metadata["input_modality"] == "documents"
	user_message = _user_message(adapter)
	assert any(isinstance(part, FileContent) for part in user_message.content)


async def test_load_file_content_chunks_reads_storage_extracts_and_chunks_media(
	monkeypatch,
) -> None:
	monkeypatch.setattr(settings.assets.content_vectorization, "loader", "auto")
	monkeypatch.setattr(
		settings.assets.content_vectorization,
		"chunking_algorithm",
		"auto",
	)
	monkeypatch.setattr(settings.assets.content_vectorization, "target_tokens", 35)
	monkeypatch.setattr(settings.assets.content_vectorization, "overlap_tokens", 0)
	monkeypatch.setattr(settings.assets.content_vectorization, "max_chunks", 20)
	data = b"image bytes from storage"
	file = _file_record("receipt.png", "image/png", data)
	backend = _MemoryStorageBackend(data)
	chat_model, adapter = _task_chat_model(
		"# receipt\n\nmerchant: northwind\n\ntotal: $42"
	)

	async def resolve_chat_model(session: AsyncSession) -> TaskChatModel | None:
		return chat_model

	monkeypatch.setattr(
		content_vectorization_service,
		"get_storage_backend",
		lambda storage_backend: backend,
	)
	monkeypatch.setattr(
		content_vectorization_service,
		"resolve_content_loader_chat_model",
		resolve_chat_model,
	)

	async with AsyncSession() as session:
		batch = await load_file_content_chunks(file, session)

	assert batch.text_loadable
	assert batch.loader == "chatmodel_loader"
	assert batch.chunker == "markdown"
	assert batch.skipped_reason is None
	assert batch.chunks
	assert "northwind" in "\n".join(chunk.text for chunk in batch.chunks)
	assert batch.chunks[0].metadata["input_modality"] == "images"
	user_message = _user_message(adapter)
	assert any(isinstance(part, ImageContent) for part in user_message.content)


async def test_load_file_content_chunks_can_disable_byte_cap(monkeypatch) -> None:
	monkeypatch.setattr(settings.assets.content_vectorization, "loader", "auto")
	monkeypatch.setattr(settings.assets.content_vectorization, "max_bytes", None)
	data = b"full image bytes from storage"
	file = _file_record("receipt.png", "image/png", data)
	backend = _MemoryStorageBackend(data)
	chat_model, adapter = _task_chat_model("# receipt\n\nfull content")

	async def resolve_chat_model(session: AsyncSession) -> TaskChatModel | None:
		return chat_model

	monkeypatch.setattr(
		content_vectorization_service,
		"get_storage_backend",
		lambda storage_backend: backend,
	)
	monkeypatch.setattr(
		content_vectorization_service,
		"resolve_content_loader_chat_model",
		resolve_chat_model,
	)

	async with AsyncSession() as session:
		batch = await load_file_content_chunks(file, session)

	assert batch.text_loadable
	user_message = _user_message(adapter)
	image = next(
		part for part in user_message.content if isinstance(part, ImageContent)
	)
	assert image.base64 is not None
	assert base64.b64decode(image.base64) == data


async def test_vectorize_file_content_upserts_content_chunks(monkeypatch) -> None:
	file = _file_record("report.txt", "text/plain", b"ignored")
	file.description = "quarterly revenue report"
	content_chunks = [
		ContentChunk(
			index=0,
			total=2,
			text="northwind revenue increased",
			metadata={"line_start": 1, "line_end": 3},
		),
		ContentChunk(
			index=1,
			total=2,
			text="contoso revenue decreased",
			metadata={"line_start": 4, "line_end": 8},
		),
	]
	upserted_chunks: list[VectorChunk] = []
	removed: list[tuple[str, bool, bool]] = []

	async def remove_vectors(
		file_id: str,
		session: AsyncSession,
		include_file_vector: bool = True,
		include_content_vectors: bool = True,
	) -> None:
		_ = session
		removed.append((file_id, include_file_vector, include_content_vectors))

	async def fetch_acl(
		resource_id: str,
		resource_type: object,
		session: AsyncSession,
	) -> dict[str, object]:
		_ = resource_type, session
		return {"acl_resource_id": resource_id}

	async def embed(
		texts: list[str],
		session: AsyncSession,
		input_type: str | None = None,
		**kwargs: object,
	) -> list[list[float]]:
		_ = session
		return [[float(index), 0.0] for index, _text in enumerate(texts)]

	async def upsert_chunks(
		chunks: list[VectorChunk],
		session: AsyncSession,
	) -> None:
		_ = session
		upserted_chunks.extend(chunks)

	monkeypatch.setattr(
		content_vectorization_service,
		"remove_file_vectors",
		remove_vectors,
	)
	monkeypatch.setattr(
		content_vectorization_service,
		"fetch_acl_metadata",
		fetch_acl,
	)
	monkeypatch.setattr(content_vectorization_service, "embed_texts", embed)
	monkeypatch.setattr(
		content_vectorization_service.vectorstore_service,
		"upsert_chunks",
		upsert_chunks,
	)

	async with AsyncSession() as session:
		batch = await vectorize_file_content(file, session, content_chunks)

	assert batch.chunks == content_chunks
	assert batch.text_loadable
	assert removed == [(str(file.id), False, True)]
	assert len(upserted_chunks) == 2
	assert upserted_chunks[0].content.startswith("report.txt")
	assert "quarterly revenue report" in upserted_chunks[0].content
	assert "northwind revenue increased" in upserted_chunks[0].content
	assert upserted_chunks[0].embedding == [0.0, 0.0]
	assert upserted_chunks[1].embedding == [1.0, 0.0]
	metadata = upserted_chunks[0].metadata
	assert metadata["resource_type"] == FILE_CONTENT_RESOURCE_TYPE
	assert "resource_id" not in metadata
	assert metadata["parent_resource_type"] == FILE_RESOURCE_TYPE
	assert metadata["parent_resource_id"] == str(file.id)
	assert metadata["owner_id"] == str(file.owner_id)
	assert "chunk_source" not in metadata
	assert "filename" not in metadata
	assert "mime_type" not in metadata
	assert "status" not in metadata
	assert "project_ids" not in metadata
	assert metadata["chunk_index"] == 0
	assert metadata["chunk_count"] == 2
	assert metadata["line_start"] == 1
	assert metadata["line_end"] == 3
	assert metadata["text_loader"] == settings.assets.content_vectorization.loader
	assert metadata["chunking_algorithm"] == (
		settings.assets.content_vectorization.chunking_algorithm
	)
	assert metadata["acl_resource_id"] == str(file.id)
	# the same fingerprint is stamped on chunks and recorded on the file row so
	# a later verify pass can treat the file as already vectorized.
	assert isinstance(metadata["vec_fingerprint"], str)
	assert metadata["vec_fingerprint"]
	assert (
		file.metadata_[content_vectorization_service.CONTENT_VECTOR_FINGERPRINT_KEY]
		== metadata["vec_fingerprint"]
	)


def test_document_model_fallback_uses_extracted_text_density() -> None:
	assert should_try_model_text(
		"scan.pdf",
		"application/pdf",
		"invoice total 42",
		size_bytes=10 * 1024 * 1024,
	)
	assert not should_try_model_text(
		"report.pdf",
		"application/pdf",
		"word " * 3000,
		size_bytes=1024 * 1024,
	)
	assert not should_try_model_text(
		"note.pdf",
		"application/pdf",
		"this small exported pdf already has searchable text " * 3,
		size_bytes=8 * 1024,
	)


def test_description_caps_can_be_disabled(monkeypatch) -> None:
	monkeypatch.setattr(settings.assets.descriptions, "max_input_chars", None)
	monkeypatch.setattr(settings.assets.descriptions, "max_chars", None)
	chunks = [
		ContentChunk(index=0, total=2, text="alpha " * 100),
		ContentChunk(index=1, total=2, text="bravo " * 100),
	]
	description = "  ".join(["long"] * 1000)

	assert (
		_content_excerpt(chunks) == "\n\n".join(chunk.text for chunk in chunks).strip()
	)
	assert _truncate_description(description) == " ".join(description.split())


async def test_markdown_chunker_keeps_markdown_metadata(monkeypatch) -> None:
	monkeypatch.setattr(settings.assets.content_vectorization, "target_tokens", 35)
	monkeypatch.setattr(settings.assets.content_vectorization, "overlap_tokens", 0)
	monkeypatch.setattr(settings.assets.content_vectorization, "max_chunks", 20)
	monkeypatch.setattr(
		settings.assets.content_vectorization,
		"chunking_algorithm",
		"markdown",
	)
	text = "\n\n".join(
		(
			"# first\n" + "alpha " * 60,
			"# second\n" + "bravo " * 60,
			"# third\n" + "charlie " * 60,
		)
	)

	chunks = await chunk_loaded_text(
		Text(
			content=text,
			status="loaded",
			source="markitdown",
			format="markdown",
			metadata={"text_format": "markdown"},
		)
	)

	assert len(chunks) > 1
	assert {chunk.metadata["text_format"] for chunk in chunks} == {"markdown"}
	assert chunks[0].text.startswith("# first")


# content vectorization fingerprint + idempotency


def _content_file(checksum: str | None = "sum-1") -> File:
	file = _file_record("doc.txt", "text/plain", b"body")
	file.checksum_sha256 = checksum
	return file


def _stub_no_loader_model(monkeypatch) -> None:
	async def _resolve(session: AsyncSession) -> TaskChatModel | None:
		_ = session
		return None

	monkeypatch.setattr(
		content_vectorization_service,
		"resolve_content_loader_chat_model",
		_resolve,
	)


def _content_chunk(
	file_id: str,
	fingerprint: str,
	chunk_index: int = 0,
	chunk_count: int = 1,
) -> VectorChunk:
	return VectorChunk(
		id=f"{file_id}-{chunk_index}",
		content="body",
		embedding=[0.0, 0.0],
		metadata={
			"parent_resource_id": file_id,
			"vec_fingerprint": fingerprint,
			"chunk_index": chunk_index,
			"chunk_count": chunk_count,
		},
	)


async def test_file_content_fingerprint_is_stable(monkeypatch) -> None:
	_stub_no_loader_model(monkeypatch)
	file = _content_file()
	async with AsyncSession() as session:
		first = await content_vectorization_service.file_content_fingerprint(
			file, session
		)
		second = await content_vectorization_service.file_content_fingerprint(
			file, session
		)
	assert first == second


async def test_file_content_fingerprint_changes_with_checksum(monkeypatch) -> None:
	_stub_no_loader_model(monkeypatch)
	async with AsyncSession() as session:
		base = await content_vectorization_service.file_content_fingerprint(
			_content_file("sum-1"), session
		)
		other = await content_vectorization_service.file_content_fingerprint(
			_content_file("sum-2"), session
		)
	assert base != other


async def test_file_content_fingerprint_changes_with_settings(monkeypatch) -> None:
	_stub_no_loader_model(monkeypatch)
	file = _content_file()
	async with AsyncSession() as session:
		base = await content_vectorization_service.file_content_fingerprint(
			file, session
		)
		monkeypatch.setattr(settings.assets.content_vectorization, "target_tokens", 999)
		after_tokens = await content_vectorization_service.file_content_fingerprint(
			file, session
		)
		monkeypatch.setattr(settings.assets.content_vectorization, "loader", "plain")
		after_loader = await content_vectorization_service.file_content_fingerprint(
			file, session
		)
	assert base != after_tokens
	assert after_tokens != after_loader


async def test_file_content_fingerprint_changes_with_model(monkeypatch) -> None:
	file = _content_file()

	async def _no_model(session: AsyncSession) -> TaskChatModel | None:
		_ = session
		return None

	monkeypatch.setattr(
		content_vectorization_service,
		"resolve_content_loader_chat_model",
		_no_model,
	)
	async with AsyncSession() as session:
		without_model = await content_vectorization_service.file_content_fingerprint(
			file, session
		)

	model, _adapter = _task_chat_model("extracted")

	async def _with_model(session: AsyncSession) -> TaskChatModel | None:
		_ = session
		return model

	monkeypatch.setattr(
		content_vectorization_service,
		"resolve_content_loader_chat_model",
		_with_model,
	)
	async with AsyncSession() as session:
		with_model = await content_vectorization_service.file_content_fingerprint(
			file, session
		)
	assert without_model != with_model


async def test_filter_unvectorized_files_uses_recorded_fingerprint(monkeypatch) -> None:
	_stub_no_loader_model(monkeypatch)
	file = _content_file()

	async def _empty_scroll(*args: object, **kwargs: object) -> list[VectorChunk]:
		# no stored chunks (media file) - currency must come from the row.
		return []

	monkeypatch.setattr(
		content_vectorization_service.vectorstore_service,
		"scroll_chunks",
		_empty_scroll,
	)
	async with AsyncSession() as session:
		fingerprint = await content_vectorization_service.file_content_fingerprint(
			file, session
		)
		content_vectorization_service._record_content_fingerprint(file, fingerprint)
		pending = await content_vectorization_service.filter_unvectorized_files(
			[file], session
		)
	assert pending == []


async def test_filter_unvectorized_files_falls_back_to_chunks(monkeypatch) -> None:
	_stub_no_loader_model(monkeypatch)
	current = _content_file("sum-current")
	stale = _content_file("sum-stale")
	missing = _content_file("sum-missing")

	async with AsyncSession() as session:
		current_fp = await content_vectorization_service.file_content_fingerprint(
			current, session
		)

		stored = [
			_content_chunk(str(current.id), current_fp, chunk_index=0, chunk_count=2),
			_content_chunk(str(current.id), current_fp, chunk_index=1, chunk_count=2),
			_content_chunk(str(stale.id), "old-fingerprint"),
		]

		async def _scroll(*args: object, **kwargs: object) -> list[VectorChunk]:
			return stored

		monkeypatch.setattr(
			content_vectorization_service.vectorstore_service,
			"scroll_chunks",
			_scroll,
		)
		pending = await content_vectorization_service.filter_unvectorized_files(
			[current, stale, missing], session
		)
	pending_ids = {str(file.id) for file in pending}
	assert pending_ids == {str(stale.id), str(missing.id)}


async def test_filter_unvectorized_files_keeps_incomplete_chunk_set(
	monkeypatch,
) -> None:
	_stub_no_loader_model(monkeypatch)
	file = _content_file()

	async with AsyncSession() as session:
		fingerprint = await content_vectorization_service.file_content_fingerprint(
			file, session
		)

		# only one of two expected chunks made it to the store (partial upsert).
		stored = [
			_content_chunk(str(file.id), fingerprint, chunk_index=0, chunk_count=2),
		]

		async def _scroll(*args: object, **kwargs: object) -> list[VectorChunk]:
			return stored

		monkeypatch.setattr(
			content_vectorization_service.vectorstore_service,
			"scroll_chunks",
			_scroll,
		)
		pending = await content_vectorization_service.filter_unvectorized_files(
			[file], session
		)
	assert [str(f.id) for f in pending] == [str(file.id)]


# process_file orchestration


def _patch_process_file_collaborators(
	monkeypatch,
	file: File,
	*,
	vectorize_calls: list[bool],
	load_calls: list[str],
	described: list[str],
) -> None:
	async def _load_file(file_id: object, session: object) -> File:
		_ = (file_id, session)
		return file

	async def _vectorize(
		f: File,
		session: object,
		content_chunks: object = None,
		force: bool = False,
	) -> FileContentChunkBatch:
		_ = (f, session, content_chunks)
		vectorize_calls.append(force)
		return FileContentChunkBatch(
			chunks=[],
			text_loadable=False,
			loader="plain",
			chunker="recursive",
			skipped_reason="already_current",
		)

	async def _load_chunks(f: File, session: object = None) -> FileContentChunkBatch:
		_ = session
		load_calls.append(str(f.id))
		return FileContentChunkBatch(
			chunks=[ContentChunk(index=0, total=1, text="body text")],
			text_loadable=True,
			loader="plain",
			chunker="recursive",
			content="body text",
		)

	async def _update_description(
		f: File,
		session: object,
		content_chunks: object = None,
		full_content: str | None = None,
		**kwargs: object,
	) -> str:
		_ = (session, content_chunks, kwargs)
		described.append(full_content or "")
		f.description = "generated"
		return "generated"

	async def _noop(*args: object, **kwargs: object) -> None:
		_ = (args, kwargs)
		return None

	monkeypatch.setattr(processing_service, "_load_file", _load_file)
	monkeypatch.setattr(processing_service, "vectorize_file_content", _vectorize)
	monkeypatch.setattr(processing_service, "load_file_content_chunks", _load_chunks)
	monkeypatch.setattr(
		processing_service, "update_file_description", _update_description
	)
	monkeypatch.setattr(processing_service, "replace_file_description_vectors", _noop)
	monkeypatch.setattr(processing_service, "emit_file_event", _noop)
	monkeypatch.setattr(processing_service, "invalidate_resource_payload_cache", _noop)


async def test_process_file_reloads_chunks_when_description_owed(
	db_session: AsyncSession,
	monkeypatch,
) -> None:
	"""when content vectors are already current and only the description is
	owed, process_file reloads chunks to build it rather than force-rebuilding
	(re-embedding + re-upserting) vectors that already match."""
	file = _file_record("doc.txt", "text/plain", b"body")
	file.description = None
	vectorize_calls: list[bool] = []
	load_calls: list[str] = []
	described: list[str] = []
	_patch_process_file_collaborators(
		monkeypatch,
		file,
		vectorize_calls=vectorize_calls,
		load_calls=load_calls,
		described=described,
	)

	result = await processing_service.process_file(TypeID(file.id), db_session)

	# vectorization ran once without force; the description path reloaded chunks.
	assert vectorize_calls == [False]
	assert load_calls == [str(file.id)]
	assert described == ["body text"]
	assert result["content_chunks"] == 1
	assert result["skipped_reason"] is None


async def test_process_file_skips_description_work_when_present(
	db_session: AsyncSession,
	monkeypatch,
) -> None:
	"""a file that already has a description neither reloads chunks nor invokes
	description generation."""
	file = _file_record("doc.txt", "text/plain", b"body")
	file.description = "existing"
	vectorize_calls: list[bool] = []
	load_calls: list[str] = []
	described: list[str] = []
	_patch_process_file_collaborators(
		monkeypatch,
		file,
		vectorize_calls=vectorize_calls,
		load_calls=load_calls,
		described=described,
	)

	result = await processing_service.process_file(TypeID(file.id), db_session)

	assert vectorize_calls == [False]
	assert load_calls == []
	assert described == []
	assert result["skipped_reason"] == "already_current"
