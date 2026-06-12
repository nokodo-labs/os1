"""tests for file metadata helpers."""

from __future__ import annotations

from nokodo_ai.utils.files import corrected_mime_type, sniff_mime_type


def test_sniff_png() -> None:
	assert sniff_mime_type(b"\x89PNG\r\n\x1a\n\x00\x00") == "image/png"


def test_sniff_jpeg() -> None:
	assert sniff_mime_type(b"\xff\xd8\xff\xe0\x00\x10JFIF") == "image/jpeg"


def test_sniff_gif() -> None:
	assert sniff_mime_type(b"GIF89a\x01\x00") == "image/gif"
	assert sniff_mime_type(b"GIF87a\x01\x00") == "image/gif"


def test_sniff_webp() -> None:
	assert sniff_mime_type(b"RIFF\x00\x00\x00\x00WEBPVP8 ") == "image/webp"


def test_sniff_tiff() -> None:
	assert sniff_mime_type(b"II*\x00\x08\x00\x00\x00") == "image/tiff"
	assert sniff_mime_type(b"MM\x00*\x00\x00\x00\x08") == "image/tiff"


def test_sniff_pdf() -> None:
	assert sniff_mime_type(b"%PDF-1.7\n") == "application/pdf"


def test_sniff_text_not_detected() -> None:
	assert sniff_mime_type(b"col_a,col_b\n1,2\n") is None


def test_sniff_empty() -> None:
	assert sniff_mime_type(b"") is None


def test_corrected_fixes_mislabeled_image() -> None:
	# the reported bug: a jpeg uploaded as image/png. anthropic rejects it.
	jpeg = b"\xff\xd8\xff\xe0\x00\x10JFIF"
	assert corrected_mime_type("image/png", jpeg) == "image/jpeg"


def test_corrected_keeps_matching_type() -> None:
	png = b"\x89PNG\r\n\x1a\n\x00\x00"
	assert corrected_mime_type("image/png", png) is None


def test_corrected_upgrades_generic_declared() -> None:
	assert (
		corrected_mime_type("application/octet-stream", b"%PDF-1.7\n")
		== "application/pdf"
	)


def test_corrected_keeps_specific_office_doc() -> None:
	# zip-container office docs all share the PK signature and puremagic
	# only guesses between them, so a correctly declared specific type must
	# never be overridden by an ambiguous detection.
	xlsx_mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
	assert corrected_mime_type(xlsx_mime, b"PK\x03\x04\x14\x00\x06\x00") is None


def test_corrected_keeps_undetectable_text() -> None:
	assert corrected_mime_type("text/csv", b"col_a,col_b\n1,2\n") is None
