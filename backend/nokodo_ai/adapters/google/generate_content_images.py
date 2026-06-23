"""google generateContent image adapter - images via gemini API.

uses the generateContent API (models/{model}:generateContent) which
supports multimodal input for image editing via inline_data parts.
best for editing workflows where the source image is provided as
part of the conversation context.
"""

from __future__ import annotations

import base64
import logging
from typing import Literal

from google.genai.client import AsyncClient
from google.genai.types import GenerateContentConfig, Part

from ..base.image_generation import (
	BaseImageAdapter,
	GeneratedImage,
	ImageGenerationParams,
	ImageGenerationResult,
)
from .base import BaseGoogleAdapter


log = logging.getLogger(__name__)


class GoogleGenerateContentImageAdapter(BaseGoogleAdapter, BaseImageAdapter):
	"""google image generation via the generateContent API.

	uses models.generate_content (same API as gemini chat) with
	response_modalities=["IMAGE", "TEXT"]. supports multimodal
	editing by passing source images as inline_data parts.

	advantages over predict API:
	- native editing via inline image parts (no reference image config)
	- same API shape as gemini chat completions
	- supports conversational image refinement

	limitations vs predict API:
	- no sampleCount / multi-image generation
	- different response parsing (candidates.content.parts)
	"""

	type: Literal["google.generate_content_images"] = "google.generate_content_images"

	async def _create(
		self,
		prompt: str,
		model: str,
		params: ImageGenerationParams,
	) -> ImageGenerationResult:
		client: AsyncClient = self._client

		config = GenerateContentConfig(
			response_modalities=["IMAGE", "TEXT"],
		)

		if params.output_format is not None:
			config.response_mime_type = f"image/{params.output_format}"

		response = await client.models.generate_content(
			model=model,
			contents=[Part.from_text(text=prompt)],
			config=config,
		)

		return self._parse_response(response)

	async def _edit(
		self,
		prompt: str,
		model: str,
		image: bytes,
		params: ImageGenerationParams,
		mask: bytes | None = None,
	) -> ImageGenerationResult:
		"""edit an image by passing it as inline_data alongside the prompt.

		mask is not supported by generateContent - it is ignored
		with a warning if provided.
		"""
		if mask is not None:
			log.warning(
				"google generateContent API does not support masks; "
				"mask argument will be ignored"
			)

		client: AsyncClient = self._client

		config = GenerateContentConfig(
			response_modalities=["IMAGE", "TEXT"],
		)

		if params.output_format is not None:
			config.response_mime_type = f"image/{params.output_format}"

		# build multimodal content: image + text prompt
		image_part = Part.from_bytes(
			data=image,
			mime_type="image/png",
		)
		text_part = Part.from_text(text=prompt)

		response = await client.models.generate_content(
			model=model,
			contents=[image_part, text_part],
			config=config,
		)

		return self._parse_response(response)

	@staticmethod
	def _parse_response(response: object) -> ImageGenerationResult:
		"""extract images from a generateContent response."""
		images: list[GeneratedImage] = []

		candidates = getattr(response, "candidates", None)
		if not candidates:
			return ImageGenerationResult(images=images)

		for candidate in candidates:
			content = getattr(candidate, "content", None)
			if content is None:
				continue
			parts = getattr(content, "parts", None)
			if not parts:
				continue
			for part in parts:
				inline_data = getattr(part, "inline_data", None)
				if inline_data is None:
					continue
				raw_bytes = getattr(inline_data, "data", None)
				mime = getattr(inline_data, "mime_type", "image/png")
				if raw_bytes is None:
					continue
				b64 = base64.b64encode(raw_bytes).decode()
				images.append(
					GeneratedImage(
						b64_data=b64,
						mime_type=mime or "image/png",
					)
				)

		return ImageGenerationResult(images=images)
