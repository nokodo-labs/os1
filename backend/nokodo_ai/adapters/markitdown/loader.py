"""MarkItDown loader adapter."""

from __future__ import annotations

import importlib
import io
from types import ModuleType
from typing import Any, Literal

from nokodo_ai.adapters.base.loaders import (
	BaseLoaderAdapter,
	File,
	LoaderConfig,
	LoaderContext,
	Text,
)
from nokodo_ai.types.json import JSONObject
from nokodo_ai.utils.files import file_extension, file_metadata, normalized_mime_type


_MARKITDOWN_EXTENSIONS = {
	".pdf",
	".docx",
	".pptx",
	".xlsx",
	".xls",
	".html",
	".htm",
	".csv",
	".json",
	".xml",
	".md",
	".markdown",
	".txt",
	".text",
	".rst",
	".epub",
	".zip",
}

_MARKITDOWN_MIME_EXACT = {
	"application/pdf",
	"application/vnd.openxmlformats-officedocument.wordprocessingml.document",
	"application/vnd.openxmlformats-officedocument.presentationml.presentation",
	"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
	"application/vnd.ms-excel",
	"application/epub+zip",
	"application/zip",
}


class MarkItDownLoaderAdapter(BaseLoaderAdapter):
	"""MarkItDown-backed document-to-Markdown loader."""

	type: Literal["markitdown.loader"] = "markitdown.loader"
	name: Literal["markitdown"] = "markitdown"

	def supports(self, file: File, config: LoaderConfig) -> bool:
		return config.text_format in {"auto", "markdown"} and _is_markitdown_loadable(
			file
		)

	async def load(
		self,
		file: File,
		context: LoaderContext,
		config: LoaderConfig,
	) -> Text:
		metadata = file_metadata(file.filename, file.mime_type, file.metadata)
		if not self.supports(file, config):
			return Text(
				content="",
				status="unsupported",
				source=self.name,
				metadata=metadata,
				skipped_reason="unsupported_type",
			)
		module = _load_markitdown_module()
		if module is None:
			return _unsupported_text(metadata, "missing_markitdown")
		try:
			result = _convert_markitdown_stream(module, file)
		except Exception as exc:
			return _unsupported_text(metadata, _markitdown_failure_reason(exc))
		return Text(
			content=_normalize_markdown(_markdown_result_text(result)),
			status="loaded",
			source=self.name,
			format="markdown",
			metadata={**metadata, "text_format": "markdown"},
		)


def _is_markitdown_loadable(file: File) -> bool:
	mime = normalized_mime_type(file.mime_type)
	return (
		mime in _MARKITDOWN_MIME_EXACT
		or mime.startswith("text/")
		or file_extension(file.filename) in _MARKITDOWN_EXTENSIONS
	)


def _unsupported_text(metadata: JSONObject, reason: str) -> Text:
	return Text(
		content="",
		status="unsupported",
		source="markitdown",
		format="markdown",
		metadata={**metadata, "text_format": "markdown"},
		skipped_reason=reason,
	)


def _load_markitdown_module() -> ModuleType | None:
	try:
		return importlib.import_module("markitdown")
	except ImportError:
		return None


def _convert_markitdown_stream(
	module: ModuleType,
	file: File,
) -> object:
	markitdown_type: Any = getattr(module, "MarkItDown")
	stream_info_type: Any = getattr(module, "StreamInfo")
	converter = markitdown_type(enable_plugins=False)
	stream_info = stream_info_type(
		mimetype=normalized_mime_type(file.mime_type) or None,
		extension=file_extension(file.filename) or None,
		filename=file.filename,
	)
	return converter.convert_stream(io.BytesIO(file.data), stream_info=stream_info)


def _markdown_result_text(result: object) -> str:
	markdown = getattr(result, "markdown", "")
	return markdown if isinstance(markdown, str) else str(markdown)


def _markitdown_failure_reason(exc: Exception) -> str:
	name = type(exc).__name__
	if name == "UnsupportedFormatException":
		return "unsupported_type"
	if name == "MissingDependencyException":
		return "missing_dependency"
	if name == "FileConversionException":
		return "conversion_failed"
	return "conversion_failed"


def _normalize_markdown(text: str) -> str:
	return text.replace("\r\n", "\n").replace("\r", "\n").strip()
