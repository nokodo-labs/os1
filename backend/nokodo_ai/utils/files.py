"""file metadata helpers."""

from __future__ import annotations

from pathlib import PurePath

import puremagic

from ..types.json import JSONObject


# detected mimes too generic to be worth overriding a declared type with.
_GENERIC_DETECTED_MIME = frozenset(
	{
		"application/octet-stream",
		"application/zip",
		"application/x-empty",
	}
)

# declared mimes safe to replace with any specific detected type.
_GENERIC_DECLARED_MIME = frozenset(
	{
		"",
		"application/octet-stream",
		"binary/octet-stream",
	}
)

# detected mime prefixes whose signatures are authoritative enough to override
# a conflicting specific declared type. image and pdf mislabeling is what breaks
# downstream model APIs, and these signatures are unambiguous.
_TRUSTED_OVERRIDE_PREFIXES = ("image/", "application/pdf")


def normalized_mime_type(mime_type: str | None) -> str:
	return (mime_type or "").split(";", 1)[0].strip().lower()


def file_extension(filename: str | None) -> str:
	return PurePath(filename or "").suffix.lower()


def sniff_mime_type(data: bytes) -> str | None:
	"""detect a mime type from the content bytes, or None if undetectable.

	uses puremagic's signature table so detection reflects the actual bytes
	rather than a declared (client-supplied) mime type.
	"""
	if not data:
		return None
	try:
		detected = puremagic.from_string(data, mime=True)
	except puremagic.PureError, ValueError:
		return None
	return normalized_mime_type(detected) or None


def corrected_mime_type(declared: str | None, data: bytes) -> str | None:
	"""return a mime type to replace declared with, or None to keep declared.

	overrides declared when the content bytes authoritatively identify a
	different type (images, pdf), and upgrades a generic or missing declared
	type to a detected specific one. ambiguous detections (e.g. zip-container
	office docs, which puremagic guesses between docx/xlsx) never override a
	specific declared type, so a correct declared type is not corrupted.
	"""
	detected = sniff_mime_type(data)
	if detected is None or detected in _GENERIC_DETECTED_MIME:
		return None
	declared_norm = normalized_mime_type(declared)
	if detected == declared_norm:
		return None
	if declared_norm in _GENERIC_DECLARED_MIME:
		return detected
	if detected.startswith(_TRUSTED_OVERRIDE_PREFIXES):
		return detected
	return None


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
