"""file metadata helpers."""

from __future__ import annotations

from pathlib import PurePath

from ..types.json import JSONObject


def normalized_mime_type(mime_type: str | None) -> str:
	return (mime_type or "").split(";", 1)[0].strip().lower()


def file_extension(filename: str | None) -> str:
	return PurePath(filename or "").suffix.lower()


def file_metadata(
	filename: str | None,
	mime_type: str | None,
	metadata: JSONObject,
) -> JSONObject:
	return {
		**metadata,
		"mime_type": normalized_mime_type(mime_type),
		"extension": file_extension(filename),
	}
