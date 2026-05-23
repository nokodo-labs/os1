"""tests for file content vectorization primitives."""

from __future__ import annotations

from api.models.file import File, FileSource, FileStatus
from api.settings import settings
from api.v1.service.files.content_vectorization import (
	chunk_loaded_text,
)
from api.v1.service.files.metadata import CONTENT_CHUNK_SOURCE
from api.v1.service.files.vectorization import _build_file_chunk
from nokodo_ai import File as SDKFile
from nokodo_ai import Loader, Text
from nokodo_ai.utils.typeid import new_typeid


def test_content_chunks_are_indexed_with_total(monkeypatch) -> None:
	monkeypatch.setattr(settings.assets.content_vectorization, "target_tokens", 50)
	monkeypatch.setattr(settings.assets.content_vectorization, "overlap_tokens", 5)
	monkeypatch.setattr(settings.assets.content_vectorization, "max_chunks", 20)
	monkeypatch.setattr(
		settings.assets.content_vectorization,
		"chunking_algorithm",
		"recursive",
	)
	text = "\n\n".join(f"paragraph {index} " + "word " * 80 for index in range(8))

	chunks = chunk_loaded_text(
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


def test_file_vector_chunk_metadata_hard_links_resource() -> None:
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

	chunk = _build_file_chunk(
		file=file,
		content="body text",
		embedding=[0.1, 0.2],
		chunk_source=CONTENT_CHUNK_SOURCE,
		chunk_index=2,
		chunk_count=7,
		extra_metadata={"line_start": 10, "line_end": 20},
	)

	assert chunk.metadata["resource_type"] == "file"
	assert chunk.metadata["resource_id"] == str(file_id)
	assert chunk.metadata["owner_id"] == str(owner_id)
	assert chunk.metadata["chunk_source"] == CONTENT_CHUNK_SOURCE
	assert chunk.metadata["chunk_index"] == 2
	assert chunk.metadata["chunk_count"] == 7
	assert chunk.metadata["line_start"] == 10
	assert chunk.metadata["line_end"] == 20


def test_auto_loader_routes_images_to_ocr_required() -> None:
	loaded = Loader(adapter="auto").load(
		SDKFile(data=b"", filename="scan.png", mime_type="image/png")
	)

	assert loaded.status == "ocr_required"
	assert loaded.skipped_reason == "ocr_required"
	assert loaded.metadata["ocr_required"] is True


def test_markdown_chunker_keeps_markdown_metadata(monkeypatch) -> None:
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

	chunks = chunk_loaded_text(
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
