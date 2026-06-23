"""base video generation adapter - capability ABC for video gen APIs."""

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
class GeneratedVideo:
	"""a single generated video result."""

	url: str | None = None
	b64_data: str | None = None
	mime_type: str = "video/mp4"
	duration_seconds: float | None = None
	revised_prompt: str | None = None


@dataclass(frozen=True, slots=True)
class VideoGenerationResult:
	"""result of a video generation request."""

	videos: list[GeneratedVideo] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class VideoProgressEvent:
	"""progress event emitted during video generation."""

	step: int
	total_steps: int | None = None
	progress: float | None = None
	partial_video: GeneratedVideo | None = None


# --- parameter types ---


class VideoGenerationParams(Base):
	"""generation options shared across video adapters."""

	model_config = ConfigDict(extra="forbid")

	duration: float | None = None
	size: str | None = None
	aspect_ratio: str | None = None
	fps: int | None = None
	quality: Literal["standard", "hd"] | None = None


# --- base adapter ---


class BaseVideoAdapter(BaseAdapter, Base, ABC):
	"""capability ABC for video generation APIs.

	adapters implementing this interface provide a single generate()
	method that handles both creation from text and creation from
	an image reference, with optional streaming progress support.

	- no image arg = create from text prompt
	- image arg = create video from reference image + prompt
	- stream=True = async iterator of progress events
	"""

	@overload
	def generate(
		self,
		prompt: str,
		model: str,
		stream: Literal[False] = False,
		image: bytes | None = None,
		params: VideoGenerationParams | None = None,
	) -> Awaitable[VideoGenerationResult]: ...

	@overload
	def generate(
		self,
		prompt: str,
		model: str,
		stream: Literal[True],
		image: bytes | None = None,
		params: VideoGenerationParams | None = None,
	) -> AsyncIterator[VideoProgressEvent]: ...

	def generate(
		self,
		prompt: str,
		model: str,
		stream: bool = False,
		image: bytes | None = None,
		params: VideoGenerationParams | None = None,
	) -> Awaitable[VideoGenerationResult] | AsyncIterator[VideoProgressEvent]:
		"""generate a video from a text prompt and optional reference image.

		args:
			prompt: text description.
			model: model identifier.
			stream: if True, returns an async iterator of progress events.
			image: optional reference image bytes.
			params: generation parameters.
		"""
		params = params or VideoGenerationParams()
		if stream:
			return self._generate_stream(prompt, model, image=image, params=params)
		return self._create(prompt, model, image=image, params=params)

	@abstractmethod
	async def _create(
		self,
		prompt: str,
		model: str,
		params: VideoGenerationParams,
		image: bytes | None = None,
	) -> VideoGenerationResult:
		"""create a video from a text prompt."""
		raise NotImplementedError

	async def _generate_stream(
		self,
		prompt: str,
		model: str,
		params: VideoGenerationParams,
		image: bytes | None = None,
	) -> AsyncIterator[VideoProgressEvent]:
		"""streaming generation with progress events.

		default implementation wraps _create as a single event.
		adapters can override for true streaming support.
		"""
		result = await self._create(prompt, model, image=image, params=params)
		video = result.videos[0] if result.videos else None
		yield VideoProgressEvent(
			step=1, total_steps=1, progress=1.0, partial_video=video
		)
