"""API-side file modality and text extraction routing helpers."""

from __future__ import annotations

from api.models.model import InputModality
from nokodo_ai.utils.files import file_extension, normalized_mime_type


_DOCUMENT_EXTENSIONS = {".pdf", ".docx", ".pptx"}
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
_AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}
_VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm", ".avi", ".mkv"}
_DOCUMENT_MIME_EXACT = {
	"application/pdf",
	"application/vnd.openxmlformats-officedocument.wordprocessingml.document",
	"application/vnd.openxmlformats-officedocument.presentationml.presentation",
}

_MIN_DOCUMENT_TEXT_CHARS = 40
_MIN_DOCUMENT_TEXT_DENSITY_BYTES = 64 * 1024
_MIN_DOCUMENT_TEXT_CHARS_PER_KIB = 4.0


def file_input_modality(
	filename: str | None,
	mime_type: str | None,
) -> InputModality:
	"""classify a file for API model capability checks."""
	mime = normalized_mime_type(mime_type)
	extension = file_extension(filename)
	if mime in _DOCUMENT_MIME_EXACT or extension in _DOCUMENT_EXTENSIONS:
		return InputModality.DOCUMENTS
	if mime.startswith("image/") or extension in _IMAGE_EXTENSIONS:
		return InputModality.IMAGES
	if mime.startswith("audio/") or extension in _AUDIO_EXTENSIONS:
		return InputModality.AUDIO
	if mime.startswith("video/") or extension in _VIDEO_EXTENSIONS:
		return InputModality.VIDEO
	return InputModality.TEXT


def is_direct_model_text_candidate(
	filename: str | None,
	mime_type: str | None,
) -> bool:
	"""return whether local text loaders should be skipped."""
	return file_input_modality(filename, mime_type) in {
		InputModality.IMAGES,
		InputModality.AUDIO,
		InputModality.VIDEO,
	}


def should_try_model_text(
	filename: str | None,
	mime_type: str | None,
	extracted_text: str,
	size_bytes: int | None = None,
) -> bool:
	"""return whether API policy should try model-backed file text extraction."""
	modality = file_input_modality(filename, mime_type)
	if modality in {InputModality.IMAGES, InputModality.AUDIO, InputModality.VIDEO}:
		return True
	if modality != InputModality.DOCUMENTS:
		return False
	meaningful_chars = len(_meaningful_text(extracted_text))
	if meaningful_chars < _MIN_DOCUMENT_TEXT_CHARS:
		return True
	if size_bytes is None or size_bytes < _MIN_DOCUMENT_TEXT_DENSITY_BYTES:
		return False
	chars_per_kib = meaningful_chars / (size_bytes / 1024)
	return chars_per_kib < _MIN_DOCUMENT_TEXT_CHARS_PER_KIB


def _meaningful_text(text: str) -> str:
	"""return only alphanumeric characters for density heuristics."""
	return "".join(char for char in text if char.isalnum())


_IMAGE_PREFIXES = ("image/",)
_AUDIO_PREFIXES = ("audio/",)
_VIDEO_PREFIXES = ("video/",)

# map media category -> model InputModality value. media whose category
# isn't in the model's input_modalities can't be shown natively.
_CATEGORY_TO_MODALITY: dict[str, str] = {
	"image": "images",
	"audio": "audio",
	"video": "video",
}


def classify_media(media_type: str | None) -> str:
	"""classify a mime type into image/audio/video/other."""
	if not media_type:
		return "other"
	lower = media_type.lower()
	if any(lower.startswith(p) for p in _IMAGE_PREFIXES):
		return "image"
	if any(lower.startswith(p) for p in _AUDIO_PREFIXES):
		return "audio"
	if any(lower.startswith(p) for p in _VIDEO_PREFIXES):
		return "video"
	return "other"


def modality_supported(media_type: str | None, supported: set[str] | None) -> bool:
	"""check whether the model can natively consume this media category.

	fails open (true) when modalities are unknown. categories with no modality
	mapping ("other", e.g. pdf/text files) also return true: such files are
	carried as their derived text content, so they are kept native within the
	image protection window rather than released.
	"""
	if supported is None:
		return True
	category = classify_media(media_type)
	modality = _CATEGORY_TO_MODALITY.get(category)
	if modality is None:
		return True
	return modality in supported
