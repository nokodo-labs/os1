"""openai image generation adapter - DALL-E / gpt-image APIs."""

from __future__ import annotations

import logging
from typing import Literal, cast

import openai
from openai import AsyncOpenAI

from ...utils.validators import warn_known_model
from ..base.image_generation import (
	BaseImageAdapter,
	GeneratedImage,
	ImageGenerationParams,
	ImageGenerationResult,
	ImageOutputFormat,
)
from .base import BaseOpenAIAdapter
from .types import OpenAIImageModel, OpenAIImagesResponse


log = logging.getLogger(__name__)


# --- openai-specific type aliases ---

OpenAIImageGenerateSize = Literal[
	"auto",
	"1024x1024",
	"1536x1024",
	"1024x1536",
	"256x256",
	"512x512",
	"1792x1024",
	"1024x1792",
]

OpenAIImageEditSize = Literal[
	"256x256",
	"512x512",
	"1024x1024",
	"1536x1024",
	"1024x1536",
	"auto",
]

OpenAIImageQuality = Literal[
	"low",
	"medium",
	"high",
	"auto",
]


# --- helpers ---


# aspect ratio to openai size mapping (all valid openai sizes)
_ASPECT_TO_SIZE: dict[str, OpenAIImageGenerateSize] = {
	"1:1": "1024x1024",
	"16:9": "1536x1024",
	"9:16": "1024x1536",
	"4:3": "1536x1024",
	"3:4": "1024x1536",
}


def _resolve_size(
	params: ImageGenerationParams,
) -> OpenAIImageGenerateSize | None:
	"""resolve size from explicit size or aspect_ratio."""
	if params.size is not None:
		# user-provided sizes come as str; cast since we
		# trust the user or SDK to validate on the API side
		return cast(OpenAIImageGenerateSize, params.size)
	if params.aspect_ratio is not None:
		return _ASPECT_TO_SIZE.get(params.aspect_ratio)
	return None


def _map_quality(
	quality: str | None,
) -> OpenAIImageQuality | None:
	"""map our quality enum to openai quality values."""
	if quality is None:
		return None
	match quality:
		case "standard":
			return "medium"
		case "hd":
			return "high"
		case _:
			return "auto"


def _map_output_format(
	fmt: ImageOutputFormat | None,
) -> Literal["png", "jpeg", "webp"] | None:
	if fmt is None:
		return None
	return fmt


def _parse_response(
	response: OpenAIImagesResponse,
	output_format: str | None,
) -> ImageGenerationResult:
	"""convert openai ImagesResponse to our result type."""
	images: list[GeneratedImage] = []
	mime = f"image/{output_format or 'png'}"
	if response.data:
		for item in response.data:
			images.append(
				GeneratedImage(
					b64_data=item.b64_json,
					url=item.url,
					mime_type=mime,
					revised_prompt=item.revised_prompt,
				)
			)
	return ImageGenerationResult(images=images)


def _is_legacy_dalle(model: str) -> bool:
	"""return True for DALL-E models that use response_format (not output_format)."""
	return model.startswith("dall-e")


class OpenAIImageAdapter(BaseOpenAIAdapter, BaseImageAdapter):
	"""openai image generation via images.generate / images.edit.

	supports DALL-E 2, DALL-E 3, and gpt-image-1 models.
	"""

	type: Literal["openai.images"] = "openai.images"

	async def _create(
		self,
		prompt: str,
		model: str,
		params: ImageGenerationParams,
	) -> ImageGenerationResult:
		client: AsyncOpenAI = self._client
		size = _resolve_size(params)
		quality = _map_quality(params.quality)
		fmt = _map_output_format(params.output_format)

		if _is_legacy_dalle(model):
			# DALL-E 2/3: uses response_format; output_format not supported
			response = await client.images.generate(
				prompt=prompt,
				model=warn_known_model(model, OpenAIImageModel),
				n=params.n,
				size=size if size else openai.omit,
				quality=quality if quality else openai.omit,
				style=(params.style if params.style else openai.omit),
				response_format="b64_json",
			)
		else:
			# gpt-image-1+: uses output_format; response_format not supported
			response = await client.images.generate(
				prompt=prompt,
				model=warn_known_model(model, OpenAIImageModel),
				n=params.n,
				size=size if size else openai.omit,
				quality=quality if quality else openai.omit,
				style=(params.style if params.style else openai.omit),
				output_format=fmt if fmt else openai.omit,
				background=(params.background if params.background else openai.omit),
			)

		return _parse_response(response, fmt)

	async def _edit(
		self,
		prompt: str,
		model: str,
		image: bytes,
		params: ImageGenerationParams,
		mask: bytes | None = None,
	) -> ImageGenerationResult:
		client: AsyncOpenAI = self._client
		size = _resolve_size(params)
		quality = _map_quality(params.quality)
		fmt = _map_output_format(params.output_format)

		if _is_legacy_dalle(model):
			# DALL-E 2: uses response_format; output_format not supported
			response = await client.images.edit(
				prompt=prompt,
				image=image,
				model=warn_known_model(model, OpenAIImageModel),
				n=params.n,
				mask=mask if mask is not None else openai.omit,
				size=(cast(OpenAIImageEditSize, size) if size else openai.omit),
				response_format="b64_json",
			)
		else:
			# gpt-image-1+: uses output_format; response_format not supported
			response = await client.images.edit(
				prompt=prompt,
				image=image,
				model=warn_known_model(model, OpenAIImageModel),
				n=params.n,
				mask=mask if mask is not None else openai.omit,
				size=(cast(OpenAIImageEditSize, size) if size else openai.omit),
				quality=quality if quality else openai.omit,
				output_format=fmt if fmt else openai.omit,
			)

		return _parse_response(response, fmt)
