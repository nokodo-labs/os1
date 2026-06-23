"""ChatModel-backed loader adapter."""

from __future__ import annotations

import base64
from typing import Literal

from nokodo_ai.adapters.base.loaders import (
	BaseLoaderAdapter,
	File,
	LoaderConfig,
	LoaderContext,
	Text,
)
from nokodo_ai.messages import (
	FileContent,
	ImageContent,
	SystemMessage,
	TextContent,
	UserMessage,
)
from nokodo_ai.threads import Thread
from nokodo_ai.types.json import JSONObject
from nokodo_ai.utils.files import file_extension, file_metadata, normalized_mime_type


_FILE_TEXT_SYSTEM_PROMPT = (
	"You convert files, documents, and media into useful searchable markdown text. "
	"Extract or transcribe readable text when present. For visual media without "
	"readable text, describe the important visible content. For audio or video, "
	"transcribe speech when possible and include concise relevant non-speech or "
	"visual context. Preserve structure, tables, and layout where useful. Output "
	"only the resulting file text, with no commentary about the task."
)
_FILE_TEXT_USER_PROMPT = "Convert the attached file, document, or media to text."

_IMAGE_EXTENSIONS = {
	".png",
	".jpg",
	".jpeg",
	".webp",
	".gif",
	".bmp",
	".tif",
	".tiff",
	".avif",
	".heic",
}
_DOCUMENT_EXTENSIONS = {
	".pdf",
	".docx",
	".pptx",
}
_MEDIA_EXTENSIONS = {
	".mp3",
	".wav",
	".m4a",
	".aac",
	".ogg",
	".flac",
	".mp4",
	".mov",
	".webm",
	".avi",
	".mkv",
}
_CHATMODEL_FILE_EXTENSIONS = {
	*_DOCUMENT_EXTENSIONS,
	*_IMAGE_EXTENSIONS,
	*_MEDIA_EXTENSIONS,
}
_CHATMODEL_FILE_MIME_EXACT = {
	"application/pdf",
	"application/vnd.openxmlformats-officedocument.wordprocessingml.document",
	"application/vnd.openxmlformats-officedocument.presentationml.presentation",
}
_CHATMODEL_FILE_MIME_PREFIXES = ("image/", "audio/", "video/")


class ChatModelLoaderAdapter(BaseLoaderAdapter):
	"""loader adapter that sends file bytes through an SDK ChatModel."""

	type: Literal["nokodo_ai.chatmodel_loader"] = "nokodo_ai.chatmodel_loader"
	name: Literal["chatmodel_loader"] = "chatmodel_loader"

	def supports(self, file: File, config: LoaderConfig) -> bool:
		mime = normalized_mime_type(file.mime_type)
		return mime.startswith(_CHATMODEL_FILE_MIME_PREFIXES) or (
			mime in _CHATMODEL_FILE_MIME_EXACT
			or file_extension(file.filename) in _CHATMODEL_FILE_EXTENSIONS
		)

	async def load(
		self,
		file: File,
		context: LoaderContext,
		config: LoaderConfig,
	) -> Text:
		metadata = _chatmodel_metadata(file, context)
		if not self.supports(file, config):
			return Text(
				content="",
				status="unsupported",
				source=self.name,
				format="markdown",
				metadata=metadata,
				skipped_reason="unsupported_type",
			)
		if context.chat_model is None:
			return Text(
				content="",
				status="unsupported",
				source=self.name,
				format="markdown",
				metadata=metadata,
				skipped_reason="missing_chat_model",
			)
		thread = Thread(
			messages=[
				SystemMessage.from_text(_FILE_TEXT_SYSTEM_PROMPT),
				UserMessage(
					content=[
						_content_part(file),
						TextContent(text=_FILE_TEXT_USER_PROMPT),
					]
				),
			]
		)
		assistant = await context.chat_model.generate(
			thread,
			stream=False,
			params={"temperature": 0},
		)
		return Text(
			content=assistant.text.strip(),
			status="loaded",
			source=self.name,
			format="markdown",
			metadata=metadata,
		)


def _content_part(file: File) -> ImageContent | FileContent:
	mime = normalized_mime_type(file.mime_type) or "application/octet-stream"
	data = base64.b64encode(file.data).decode("ascii")
	if mime.startswith("image/") or file_extension(file.filename) in _IMAGE_EXTENSIONS:
		return ImageContent(base64=data, media_type=mime, filename=file.filename)
	return FileContent(base64=data, media_type=mime, filename=file.filename)


def _chatmodel_metadata(file: File, context: LoaderContext) -> JSONObject:
	metadata = file_metadata(file.filename, file.mime_type, file.metadata)
	metadata.update(
		{
			"text_format": "markdown",
			"text_kind": "file_text",
			"text_provider": "chat_model" if context.chat_model is not None else "none",
		}
	)
	if context.chat_model is not None:
		metadata["text_model"] = context.chat_model.model_name
	return metadata
