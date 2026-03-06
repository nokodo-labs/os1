"""base image generation adapter - capability ABC for image gen APIs."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Awaitable
from dataclasses import dataclass, field
from typing import Literal, overload

from pydantic import ConfigDict

from ...base import Base
from .adapter import BaseAdapter


# --- result types ---


@dataclass(frozen=True, slots=True)
class GeneratedImage:
	"""a single generated image result."""

	url: str | None = None
	b64_data: str | None = None
	mime_type: str = "image/png"
	revised_prompt: str | None = None


@dataclass(frozen=True, slots=True)
class ImageGenerationResult:
	"""result of an image generation or edit request."""

	images: list[GeneratedImage] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ImageProgressEvent:
	"""progress event emitted during streaming generation."""

	step: int
	total_steps: int | None = None
	partial_image: GeneratedImage | None = None


# --- parameter types ---


ContentFilterLevel = Literal["none", "low", "medium", "high", "auto"]
ImageOutputFormat = Literal["png", "jpeg", "webp"]


class ImageGenerationParams(Base):
	"""generation options shared across image adapters.

	used for both creation and editing operations.
	edit-specific params (strength) are ignored for creation.
	"""

	model_config = ConfigDict(extra="forbid")

	n: int = 1
	size: str | None = None
	aspect_ratio: str | None = None
	quality: Literal["standard", "hd", "auto"] | None = None
	style: Literal["natural", "vivid"] | None = None
	output_format: ImageOutputFormat | None = None
	background: Literal["transparent", "opaque", "auto"] | None = None
	content_filter: ContentFilterLevel | None = None
	negative_prompt: str | None = None
	strength: float | None = None


# --- base adapter ---


class BaseImageAdapter(BaseAdapter, Base, ABC):
	"""capability ABC for image generation APIs.

	adapters implementing this interface provide a single generate()
	method that handles both creation and editing, with optional
	streaming support.

	- no image arg = create from text prompt
	- image arg = edit existing image (with optional mask)
	- stream=True = async iterator of progress events

	unsupported params are silently ignored by each adapter.
	"""

	@overload
	def generate(
		self,
		prompt: str,
		model: str,
		*,
		stream: Literal[False] = False,
		image: bytes | None = None,
		mask: bytes | None = None,
		params: ImageGenerationParams | None = None,
	) -> Awaitable[ImageGenerationResult]: ...

	@overload
	def generate(
		self,
		prompt: str,
		model: str,
		*,
		stream: Literal[True],
		image: bytes | None = None,
		mask: bytes | None = None,
		params: ImageGenerationParams | None = None,
	) -> AsyncIterator[ImageProgressEvent]: ...

	def generate(
		self,
		prompt: str,
		model: str,
		*,
		stream: bool = False,
		image: bytes | None = None,
		mask: bytes | None = None,
		params: ImageGenerationParams | None = None,
	) -> Awaitable[ImageGenerationResult] | AsyncIterator[ImageProgressEvent]:
		"""generate or edit images.

		args:
			prompt: text description.
			model: model identifier.
			stream: if True, returns an async iterator of progress events.
			image: source image bytes for editing (None = create).
			mask: optional mask for edit area (white = edit, black = keep).
			params: generation parameters.
		"""
		params = params or ImageGenerationParams()
		if stream:
			return self._generate_stream(
				prompt, model, image=image, mask=mask, params=params
			)
		if image is not None:
			return self._edit(prompt, model, image=image, mask=mask, params=params)
		return self._create(prompt, model, params=params)

	@abstractmethod
	async def _create(
		self,
		prompt: str,
		model: str,
		*,
		params: ImageGenerationParams,
	) -> ImageGenerationResult:
		"""create images from a text prompt."""
		raise NotImplementedError

	@abstractmethod
	async def _edit(
		self,
		prompt: str,
		model: str,
		*,
		image: bytes,
		mask: bytes | None = None,
		params: ImageGenerationParams,
	) -> ImageGenerationResult:
		"""edit an existing image with a text prompt."""
		raise NotImplementedError

	async def _generate_stream(
		self,
		prompt: str,
		model: str,
		*,
		image: bytes | None = None,
		mask: bytes | None = None,
		params: ImageGenerationParams,
	) -> AsyncIterator[ImageProgressEvent]:
		"""streaming generation with progress events.

		default implementation wraps _create/_edit as a single event.
		adapters can override for true streaming support.
		"""
		if image is not None:
			result = await self._edit(
				prompt, model, image=image, mask=mask, params=params
			)
		else:
			result = await self._create(prompt, model, params=params)
		yield ImageProgressEvent(
			step=1,
			total_steps=1,
			partial_image=(result.images[0] if result.images else None),
		)
