"""tests for SDK content loading and chunking primitives."""

from collections.abc import AsyncIterator, Awaitable
from typing import Literal, overload

from pydantic import PrivateAttr

from nokodo_ai import Chunker, Loader
from nokodo_ai.adapters.base.chat import BaseChatAdapter, ChatGenerationParams
from nokodo_ai.adapters.markitdown.loader import MarkItDownLoaderAdapter
from nokodo_ai.adapters.nokodo_ai.markdown import MarkdownChunkerAdapter
from nokodo_ai.adapters.nokodo_ai.plain import PlainLoaderAdapter
from nokodo_ai.chat_models import ChatModel
from nokodo_ai.loaders import File, LoaderConfig, Text
from nokodo_ai.messages import (
	AssistantMessage,
	FileContent,
	ImageContent,
	Message,
	UserMessage,
)
from nokodo_ai.tool import ToolDefinition


class _FileTextChatAdapter(BaseChatAdapter):
	type: Literal["test.file_text"] = "test.file_text"
	_messages: list[Message] = PrivateAttr(default_factory=list)

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
			return AssistantMessage.from_text("invoice total: $42")

		return response()


async def test_plain_loader_formats_json() -> None:
	loaded = await Loader.create(adapter="plain").load(
		File(
			data=b'{"name":"report","count":2}',
			filename="report.json",
			mime_type="application/json",
		)
	)

	assert loaded.status == "loaded"
	assert loaded.source == "plain"
	assert '"name": "report"' in loaded.content


async def test_plain_loader_keeps_markdown_format() -> None:
	loaded = await Loader.create(adapter="plain").load(
		File(data=b"# Notes\n\nBody", filename="notes.md", mime_type="text/markdown")
	)

	assert loaded.status == "loaded"
	assert loaded.source == "plain"
	assert loaded.format == "markdown"


async def test_plain_loader_can_return_raw_text() -> None:
	loaded = await Loader.create(adapter="plain", text_format="raw").load(
		File(data=b'{"name":"report"}', filename="report.json")
	)

	assert loaded.status == "loaded"
	assert loaded.format == "raw"
	assert loaded.content == '{"name":"report"}'


async def test_plain_loader_keeps_empty_text_loaded() -> None:
	loaded = await Loader.create(adapter="plain").load(
		File(data=b"", filename="empty.txt", mime_type="text/plain")
	)

	assert loaded.status == "loaded"
	assert loaded.content == ""
	assert loaded.skipped_reason is None
	assert await Chunker.create(adapter="recursive").chunk(loaded) == []


async def test_chatmodel_loader_requires_chat_model_fact() -> None:
	loaded = await Loader.create(adapter="chatmodel").load(
		File(data=b"", filename="scan.jpg", mime_type="image/jpeg")
	)

	assert loaded.status == "unsupported"
	assert loaded.skipped_reason == "missing_chat_model"


async def test_chatmodel_loader_uses_chat_model_for_image_text() -> None:
	adapter = _FileTextChatAdapter()
	chat_model = ChatModel.model_construct(model_name="vision", adapter=adapter)

	loaded = await Loader.create(adapter="chatmodel", chat_model=chat_model).load(
		File(data=b"image-bytes", filename="scan.jpg", mime_type="image/jpeg")
	)

	assert loaded.status == "loaded"
	assert loaded.source == "chatmodel_loader"
	assert loaded.content == "invoice total: $42"
	assert loaded.metadata["text_kind"] == "file_text"
	assert loaded.metadata["text_model"] == "vision"
	user_message = adapter.messages[1]
	assert isinstance(user_message, UserMessage)
	assert any(isinstance(part, ImageContent) for part in user_message.content)


async def test_chatmodel_loader_uses_file_content_for_documents() -> None:
	adapter = _FileTextChatAdapter()
	chat_model = ChatModel.model_construct(model_name="document-model", adapter=adapter)

	loaded = await Loader.create(adapter="chatmodel", chat_model=chat_model).load(
		File(data=b"%PDF", filename="report.pdf", mime_type="application/pdf")
	)

	assert loaded.status == "loaded"
	user_message = adapter.messages[1]
	assert isinstance(user_message, UserMessage)
	assert any(isinstance(part, FileContent) for part in user_message.content)


def test_markitdown_adapter_supports_document_types() -> None:
	adapter = MarkItDownLoaderAdapter()
	config = LoaderConfig()

	assert adapter.supports(File(data=b"", filename="slides.pptx"), config)
	assert adapter.supports(
		File(data=b"", filename="report.pdf", mime_type="application/pdf"),
		config,
	)


async def test_loader_accepts_concrete_adapter() -> None:
	loaded = await Loader(adapter=PlainLoaderAdapter()).load(
		File(data=b"hello", filename="notes.txt", mime_type="text/plain")
	)

	assert loaded.status == "loaded"
	assert loaded.source == "plain"


async def test_markdown_chunker_keeps_heading_boundaries() -> None:
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

	chunks = await Chunker.create(
		adapter="markdown",
		target_tokens=35,
		overlap_tokens=0,
		max_chunks=20,
	).chunk(loaded)

	assert len(chunks) > 1
	assert chunks[0].text.startswith("# alpha")
	assert {chunk.metadata["text_format"] for chunk in chunks} == {"markdown"}


async def test_chunker_accepts_concrete_adapter() -> None:
	loaded = Text(
		content="# alpha\n" + "alpha " * 60,
		status="loaded",
		source="plain",
		format="markdown",
		metadata={"text_format": "markdown"},
	)

	chunks = await Chunker(
		adapter=MarkdownChunkerAdapter(),
		target_tokens=35,
		overlap_tokens=0,
		max_chunks=20,
	).chunk(loaded)

	assert chunks
	assert chunks[0].text.startswith("# alpha")


async def test_recursive_chunker_can_disable_chunk_cap() -> None:
	loaded = Text(
		content="\n\n".join(f"section {index} " + "word " * 80 for index in range(8)),
		status="loaded",
		source="plain",
		metadata={},
	)

	capped = await Chunker.create(
		adapter="recursive",
		target_tokens=35,
		overlap_tokens=0,
		max_chunks=2,
	).chunk(loaded)
	unlimited = await Chunker.create(
		adapter="recursive",
		target_tokens=35,
		overlap_tokens=0,
		max_chunks=None,
	).chunk(loaded)

	assert len(capped) == 2
	assert len(unlimited) > len(capped)
