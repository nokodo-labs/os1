"""google predict image adapter - imagen via models.generate_images.

uses the predict-style API (models/{model}:predict under the hood).
supports text-to-image creation and mask-based editing with
reference images. best for bulk generation (sampleCount).
"""

from __future__ import annotations

import base64
import logging
from typing import Literal, cast

from google.genai.client import AsyncClient
from google.genai.types import (
	EditImageConfig,
	EditMode,
	GenerateImagesConfig,
	Image,
	MaskReferenceConfig,
	MaskReferenceImage,
	MaskReferenceMode,
	RawReferenceImage,
	SafetyFilterLevel,
	_ReferenceImageAPIOrDict,
)

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

	type: Literal["google.predict_images"] = "google.predict_images"

	async def _create(
		self,
		prompt: str,
		model: str,
		*,
		params: ImageGenerationParams,
	) -> ImageGenerationResult:
		client: AsyncClient = self._client

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

		# cast required: google genai SDK typing bug - RawReferenceImage
		# and MaskReferenceImage are not subclasses of _ReferenceImageAPI
		# despite being accepted at runtime by edit_image().
		ref_images: list[_ReferenceImageAPIOrDict] = [
			cast(
				_ReferenceImageAPIOrDict,
				RawReferenceImage(
					reference_image=Image(image_bytes=image),
					reference_id=0,
				),
			),
		]

		if mask is not None:
			ref_images.append(
				cast(
					_ReferenceImageAPIOrDict,
					MaskReferenceImage(
						reference_image=Image(image_bytes=mask),
						reference_id=0,
						config=MaskReferenceConfig(
							mask_mode=MaskReferenceMode.MASK_MODE_USER_PROVIDED,
						),
					),
				)
			)

		config = EditImageConfig(
			number_of_images=params.n,
			edit_mode=(
				EditMode.EDIT_MODE_INPAINT_INSERTION
				if mask
				else EditMode.EDIT_MODE_DEFAULT
			),
			output_mime_type=(
				f"image/{params.output_format}"
				if params.output_format is not None
				else None
			),
			safety_filter_level=_resolve_safety_filter(params.content_filter),
		)

		response = await client.models.edit_image(
			model=model,
			prompt=prompt,
			reference_images=ref_images,
			config=config,
		)

		return ImageGenerationResult(images=_extract_images(response))
