"""image adapter union - single entry point for all image adapters."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from .base.image_generation import (
	BaseImageAdapter,
	ContentFilterLevel,
	GeneratedImage,
	ImageGenerationParams,
	ImageGenerationResult,
	ImageOutputFormat,
	ImageProgressEvent,
)
from .google.generate_content_images import GoogleGenerateContentImageAdapter
from .google.predict_images import GooglePredictImageAdapter
from .openai.images import OpenAIImageAdapter


ImageAdapter = Annotated[
	OpenAIImageAdapter | GooglePredictImageAdapter | GoogleGenerateContentImageAdapter,
	Field(discriminator="type"),
]


def resolve_image_adapter(provider: str, adapter: str | None) -> str | None:
	"""resolve the adapter type string from provider and adapter variant."""
	match provider:
		case "openai":
			return "openai.images"
		case "google":
			# 'generate_content_images' selects the gemini generateContent path
			# (multimodal editing); anything else defaults to the predict/imagen path
			if adapter == "generate_content_images":
				return "google.generate_content_images"
			return "google.predict_images"
	return None


__all__ = [
	"BaseImageAdapter",
	"ContentFilterLevel",
	"GeneratedImage",
	"GoogleGenerateContentImageAdapter",
	"GooglePredictImageAdapter",
	"ImageAdapter",
	"ImageGenerationParams",
	"ImageGenerationResult",
	"ImageOutputFormat",
	"ImageProgressEvent",
	"resolve_image_adapter",
]
