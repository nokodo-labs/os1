"""nokodo_ai plain text loader adapter."""

from __future__ import annotations

import csv
import io
import json
from html.parser import HTMLParser
from typing import Literal

from nokodo_ai.adapters.base.loaders import (
	BaseLoaderAdapter,
	File,
	LoaderConfig,
	LoaderContext,
	Text,
)
from nokodo_ai.types.json import JSONObject
from nokodo_ai.utils.files import file_extension, file_metadata, normalized_mime_type


_TEXT_EXTENSIONS = {
	".txt",
	".text",
	".md",
	".markdown",
	".rst",
	".json",
	".jsonl",
	".csv",
	".tsv",
	".html",
	".htm",
	".xml",
	".yaml",
	".yml",
	".toml",
	".ini",
	".log",
	".py",
	".js",
	".ts",
	".tsx",
	".jsx",
	".svelte",
	".css",
	".scss",
	".sql",
	".sh",
	".ps1",
	".bat",
	".dockerfile",
}

_TEXT_MIME_EXACT = {
	"application/json",
	"application/ld+json",
	"application/xml",
	"application/yaml",
	"application/x-yaml",
	"application/toml",
	"application/csv",
	"application/x-ndjson",
}

_TEXT_ENCODING = "utf-8"
_TEXT_DECODE_ERRORS = "replace"


class PlainLoaderAdapter(BaseLoaderAdapter):
	"""loader adapter for plain text-adjacent formats."""

	type: Literal["nokodo_ai.plain"] = "nokodo_ai.plain"
	name: Literal["plain"] = "plain"

	def supports(self, file: File, config: LoaderConfig) -> bool:
		return _is_plain_text_loadable(file)

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
		text = file.data.decode(_TEXT_ENCODING, errors=_TEXT_DECODE_ERRORS)
		return _format_plain_text(text, file, metadata, config)


def _is_plain_text_loadable(file: File) -> bool:
	mime = normalized_mime_type(file.mime_type)
	if mime.startswith("text/") or mime in _TEXT_MIME_EXACT:
		return True
	return file_extension(file.filename) in _TEXT_EXTENSIONS


class _PlainHTMLTextParser(HTMLParser):
	def __init__(self) -> None:
		super().__init__()
		self.parts: list[str] = []

	def handle_data(self, data: str) -> None:
		text = data.strip()
		if text:
			self.parts.append(text)

	def text(self) -> str:
		return "\n".join(self.parts)


def _format_plain_text(
	text: str,
	file: File,
	metadata: JSONObject,
	config: LoaderConfig,
) -> Text:
	if config.text_format == "raw":
		return Text(
			content=text,
			status="loaded",
			source="plain",
			format="raw",
			metadata={**metadata, "text_format": "raw"},
		)
	mime = normalized_mime_type(file.mime_type)
	suffix = file_extension(file.filename)
	if mime in {"application/json", "application/ld+json"} or suffix == ".json":
		return Text(
			content=_format_json_text(text),
			status="loaded",
			source="plain",
			metadata=metadata,
		)
	if suffix == ".jsonl" or mime == "application/x-ndjson":
		return Text(
			content=_format_jsonl_text(text),
			status="loaded",
			source="plain",
			metadata=metadata,
		)
	if suffix in {".csv", ".tsv"} or mime in {"text/csv", "application/csv"}:
		return Text(
			content=_format_delimited_text(text, suffix),
			status="loaded",
			source="plain",
			metadata=metadata,
		)
	if suffix in {".html", ".htm"} or mime == "text/html":
		parser = _PlainHTMLTextParser()
		parser.feed(text)
		return Text(
			content=parser.text(),
			status="loaded",
			source="plain",
			metadata=metadata,
		)
	if suffix in {".md", ".markdown"} and config.text_format != "plain":
		return Text(
			content=text,
			status="loaded",
			source="plain",
			format="markdown",
			metadata={**metadata, "text_format": "markdown"},
		)
	return Text(content=text, status="loaded", source="plain", metadata=metadata)


def _format_json_text(text: str) -> str:
	try:
		value = json.loads(text)
	except json.JSONDecodeError:
		return text
	return json.dumps(value, ensure_ascii=False, indent=2)


def _format_jsonl_text(text: str) -> str:
	formatted: list[str] = []
	for line in text.splitlines():
		stripped = line.strip()
		if not stripped:
			continue
		try:
			value = json.loads(stripped)
		except json.JSONDecodeError:
			formatted.append(stripped)
		else:
			formatted.append(json.dumps(value, ensure_ascii=False))
	return "\n".join(formatted)


def _format_delimited_text(text: str, suffix: str) -> str:
	dialect = "excel-tab" if suffix == ".tsv" else "excel"
	reader = csv.reader(io.StringIO(text), dialect=dialect)
	rows: list[str] = []
	for row_index, row in enumerate(reader, start=1):
		cells = [cell.strip() for cell in row if cell.strip()]
		if cells:
			rows.append(f"row {row_index}: " + "; ".join(cells))
	return "\n".join(rows)
