"""image model high-level interface - unified access to image generation."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable
from typing import Any, ClassVar, Literal, overload

from pydantic import Field

from .adapter_enabled import AdapterEnabledBase, AdapterResolver
from .adapters.base.image_generation import (
	ImageGenerationParams,
	ImageGenerationResult,
	ImageProgressEvent,
)
from .adapters.images import ImageAdapter, resolve_image_adapter


class ImageModel(AdapterEnabledBase[ImageAdapter]):
	"""high-level unified interface for image generation models.

	usage:
		image_model = ImageModel.create(
			"dall-e-3",
			adapter={"type": "openai.images", "api_key": "..."},
		)
		# create
		result = await image_model.generate("a cat in space")
		# edit
		result = await image_model.generate("remove bg", image=img_bytes)
		# stream
		async for event in image_model.generate("a cat", stream=True):
			...
	"""

	model_name: str = Field(..., description="model identifier")

	_adapter_resolver: ClassVar[AdapterResolver] = resolve_image_adapter

	@classmethod
	def create(
		cls,
		model_name: str,
		*,
		adapter: ImageAdapter | dict[str, Any],
		**fields: Any,
	) -> ImageModel:
		"""create an image model with explicit adapter configuration."""
		return super()._create(("model_name", model_name), adapter=adapter, **fields)

	@overload
	def generate(
		self,
		prompt: str,
		*,
		stream: Literal[False] = False,
		image: bytes | None = None,
		mask: bytes | None = None,
		params: ImageGenerationParams | dict[str, object] | None = None,
	) -> Awaitable[ImageGenerationResult]: ...

	@overload
	def generate(
		self,
		prompt: str,
		*,
		stream: Literal[True],
		image: bytes | None = None,
		mask: bytes | None = None,
		params: ImageGenerationParams | dict[str, object] | None = None,
	) -> AsyncIterator[ImageProgressEvent]: ...

	def generate(
		self,
		prompt: str,
		*,
		stream: bool = False,
		image: bytes | None = None,
		mask: bytes | None = None,
		params: ImageGenerationParams | dict[str, object] | None = None,
	) -> Awaitable[ImageGenerationResult] | AsyncIterator[ImageProgressEvent]:
		"""generate or edit images.

		- no image = create from text prompt
		- image = edit existing image (with optional mask)
		- stream=True = async iterator of progress events
		"""
		effective = self._resolve_params(params)
		return self.adapter.generate(
			prompt,
			self.model_name,
			stream=stream,
			image=image,
			mask=mask,
			params=effective,
		)

	def _resolve_params(
		self,
		params: ImageGenerationParams | dict[str, object] | None,
	) -> ImageGenerationParams:
		if params is None:
			return ImageGenerationParams()
		if isinstance(params, dict):
			return ImageGenerationParams.model_validate(params)
		return params
