"""tests for SDK content loading and chunking primitives."""

from nokodo_ai import Chunker, File, Loader, Text
from nokodo_ai.adapters.markitdown.loaders import MarkItDownLoaderAdapter
from nokodo_ai.adapters.nokodo_ai.markdown import MarkdownChunkerAdapter
from nokodo_ai.adapters.nokodo_ai.plain import PlainLoaderAdapter
from nokodo_ai.loaders import LoaderConfig


def test_plain_loader_formats_json() -> None:
	loaded = Loader(adapter="plain").load(
		File(
			data=b'{"name":"report","count":2}',
			filename="report.json",
			mime_type="application/json",
		)
	)

	assert loaded.status == "loaded"
	assert loaded.source == "plain"
	assert '"name": "report"' in loaded.content


def test_auto_loader_keeps_markdown_on_plain_path() -> None:
	loaded = Loader(adapter="auto").load(
		File(data=b"# Notes\n\nBody", filename="notes.md", mime_type="text/markdown")
	)

	assert loaded.status == "loaded"
	assert loaded.source == "plain"
	assert loaded.format == "markdown"


def test_plain_loader_can_return_raw_text() -> None:
	loaded = Loader(adapter="plain", text_format="raw").load(
		File(data=b'{"name":"report"}', filename="report.json")
	)

	assert loaded.status == "loaded"
	assert loaded.format == "raw"
	assert loaded.content == '{"name":"report"}'


def test_plain_loader_keeps_empty_text_loaded() -> None:
	loaded = Loader(adapter="plain").load(
		File(data=b"", filename="empty.txt", mime_type="text/plain")
	)

	assert loaded.status == "loaded"
	assert loaded.content == ""
	assert loaded.skipped_reason is None
	assert Chunker(adapter="recursive").chunk(loaded) == []


def test_auto_loader_routes_images_to_ocr_required() -> None:
	loaded = Loader(adapter="auto").load(
		File(data=b"", filename="scan.jpg", mime_type="image/jpeg")
	)

	assert loaded.status == "ocr_required"
	assert loaded.metadata["ocr_required"] is True


def test_markitdown_adapter_supports_document_types() -> None:
	adapter = MarkItDownLoaderAdapter()
	config = LoaderConfig()

	assert adapter.supports(File(data=b"", filename="slides.pptx"), config)
	assert adapter.supports(
		File(data=b"", filename="report.pdf", mime_type="application/pdf"),
		config,
	)


def test_loader_accepts_concrete_adapter() -> None:
	loaded = Loader(adapter=PlainLoaderAdapter()).load(
		File(data=b"hello", filename="notes.txt", mime_type="text/plain")
	)

	assert loaded.status == "loaded"
	assert loaded.source == "plain"


def test_markdown_chunker_keeps_heading_boundaries() -> None:
	loaded = Text(
		content="\n\n".join(
			(
				"# alpha\n" + "alpha " * 60,
				"# bravo\n" + "bravo " * 60,
				"# charlie\n" + "charlie " * 60,
			)
		),
		status="loaded",
		source="markitdown",
		format="markdown",
		metadata={"text_format": "markdown"},
	)

	chunks = Chunker(
		adapter="auto",
		target_tokens=35,
		overlap_tokens=0,
		max_chunks=20,
	).chunk(loaded)

	assert len(chunks) > 1
	assert chunks[0].text.startswith("# alpha")
	assert {chunk.metadata["text_format"] for chunk in chunks} == {"markdown"}


def test_chunker_accepts_concrete_adapter() -> None:
	loaded = Text(
		content="# alpha\n" + "alpha " * 60,
		status="loaded",
		source="plain",
		format="markdown",
		metadata={"text_format": "markdown"},
	)

	chunks = Chunker(
		adapter=MarkdownChunkerAdapter(),
		target_tokens=35,
		overlap_tokens=0,
		max_chunks=20,
	).chunk(loaded)

	assert chunks
	assert chunks[0].text.startswith("# alpha")
