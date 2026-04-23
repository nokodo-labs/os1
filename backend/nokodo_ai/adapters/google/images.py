"""google predict image adapter - imagen via models.generate_images.

uses the predict-style API (models/{model}:predict under the hood).
supports text-to-image creation and mask-based editing with
reference images. best for bulk generation (sampleCount).
"""

from __future__ import annotations

import base64
import logging
from typing import Literal

from google.genai.client import AsyncClient
from google.genai.types import SafetyFilterLevel

from ..base.image_generation import (
	BaseImageAdapter,
	GeneratedImage,
	ImageGenerationParams,
	ImageGenerationResult,
)
from .base import BaseGoogleAdapter


log = logging.getLogger(__name__)


# google imagen safety filter mapping
_FILTER_MAP: dict[str, str] = {
	"none": "BLOCK_NONE",
	"low": "BLOCK_ONLY_HIGH",
	"medium": "BLOCK_MEDIUM_AND_ABOVE",
	"high": "BLOCK_LOW_AND_ABOVE",
	"auto": "BLOCK_MEDIUM_AND_ABOVE",
}


def _resolve_safety_filter(
	level: str | None,
) -> SafetyFilterLevel | None:
	"""resolve safety filter level to google SafetyFilterLevel enum."""
	if level is None:
		return None
	name = _FILTER_MAP.get(level, "BLOCK_MEDIUM_AND_ABOVE")
	return SafetyFilterLevel(name)


def _extract_images(response: object) -> list[GeneratedImage]:
	"""extract GeneratedImage list from a generate_images response."""
	images: list[GeneratedImage] = []
	generated = getattr(response, "generated_images", None)
	if not generated:
		return images
	for img in generated:
		b64 = None
		if img.image and img.image.image_bytes:
			b64 = base64.b64encode(img.image.image_bytes).decode()
		images.append(
			GeneratedImage(
				b64_data=b64,
				mime_type=(
					img.image.mime_type
					if img.image and img.image.mime_type
					else "image/png"
				),
			)
		)
	return images


class GooglePredictImageAdapter(BaseGoogleAdapter, BaseImageAdapter):
	"""google image generation via the genai predict/generate_images API.

	uses models.generate_images (predict endpoint). supports imagen-3.0
	and future imagen models. good for text-to-image with sampleCount
	and mask-based editing with reference images.
	"""

	type: Literal["google.images"] = "google.images"

	async def _create(
		self,
		prompt: str,
		model: str,
		*,
		params: ImageGenerationParams,
	) -> ImageGenerationResult:
		client: AsyncClient = self._client

		from google.genai.types import GenerateImagesConfig

		config = GenerateImagesConfig(
			number_of_images=params.n,
			aspect_ratio=params.aspect_ratio,
			negative_prompt=params.negative_prompt,
			output_mime_type=(
				f"image/{params.output_format}" if params.output_format else None
			),
			safety_filter_level=_resolve_safety_filter(params.content_filter),
		)

		response = await client.models.generate_images(
			model=model,
			prompt=prompt,
			config=config,
		)

		return ImageGenerationResult(images=_extract_images(response))

	async def _edit(
		self,
		prompt: str,
		model: str,
		*,
		image: bytes,
		mask: bytes | None = None,
		params: ImageGenerationParams,
	) -> ImageGenerationResult:
		client: AsyncClient = self._client

		config: dict[str, object] = {
			"number_of_images": params.n,
			"edit_mode": (
				"EDIT_MODE_INPAINT_INSERTION" if mask else "EDIT_MODE_DEFAULT"
			),
		}

		if params.output_format is not None:
			config["output_mime_type"] = f"image/{params.output_format}"

		safety = _resolve_safety_filter(params.content_filter)
		if safety is not None:
			config["safety_filter_level"] = safety

		from google.genai.types import (
			Image,
			MaskReferenceConfig,
			MaskReferenceImage,
			MaskReferenceMode,
			RawReferenceImage,
		)

		ref_images: list[RawReferenceImage | MaskReferenceImage] = []
		ref_images.append(
			RawReferenceImage(
				reference_image=Image(image_bytes=image),
				reference_id=0,
			)
		)

		if mask is not None:
			ref_images.append(
				MaskReferenceImage(
					reference_image=Image(image_bytes=mask),
					reference_id=0,
					config=MaskReferenceConfig(
						mask_mode=MaskReferenceMode.MASK_MODE_USER_PROVIDED,
					),
				)
			)

		config["reference_images"] = ref_images

		response = await client.models.generate_images(
			model=model,
			prompt=prompt,
			config=config,  # type: ignore[arg-type]
		)

		return ImageGenerationResult(images=_extract_images(response))
