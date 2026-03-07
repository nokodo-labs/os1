"""video model high-level interface - unified access to video generation."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable
from typing import Any, ClassVar, Literal, overload

from pydantic import Field

from .adapter_enabled import AdapterEnabledBase, AdapterResolver
from .adapters.base.video_generation import (
	VideoGenerationParams,
	VideoGenerationResult,
	VideoProgressEvent,
)
from .adapters.videos import VideoAdapter, resolve_video_adapter


class VideoModel(AdapterEnabledBase[VideoAdapter]):
	"""high-level unified interface for video generation models.

	usage:
		video_model = VideoModel.create(
			"sora",
			adapter={"type": "openai.videos", "api_key": "..."},
		)
		result = await video_model.generate("a cat in space")
	"""

	model_name: str = Field(..., description="model identifier")

	_adapter_resolver: ClassVar[AdapterResolver] = resolve_video_adapter

	@classmethod
	def create(
		cls,
		model_name: str,
		*,
		adapter: VideoAdapter | dict[str, Any],
		**fields: Any,
	) -> VideoModel:
		"""create a video model with explicit adapter configuration."""
		return super()._create(("model_name", model_name), adapter=adapter, **fields)

	@overload
	def generate(
		self,
		prompt: str,
		*,
		stream: Literal[False] = False,
		image: bytes | None = None,
		params: VideoGenerationParams | dict[str, object] | None = None,
	) -> Awaitable[VideoGenerationResult]: ...

	@overload
	def generate(
		self,
		prompt: str,
		*,
		stream: Literal[True],
		image: bytes | None = None,
		params: VideoGenerationParams | dict[str, object] | None = None,
	) -> AsyncIterator[VideoProgressEvent]: ...

	def generate(
		self,
		prompt: str,
		*,
		stream: bool = False,
		image: bytes | None = None,
		params: VideoGenerationParams | dict[str, object] | None = None,
	) -> Awaitable[VideoGenerationResult] | AsyncIterator[VideoProgressEvent]:
		"""generate a video from a text prompt.

		- stream=True = async iterator of progress events
		- image = optional reference image bytes
		"""
		effective = self._resolve_params(params)
		if stream:
			return self.adapter.generate(
				prompt,
				self.model_name,
				stream=True,
				image=image,
				params=effective,
			)
		return self.adapter.generate(
			prompt,
			self.model_name,
			image=image,
			params=effective,
		)

	def _resolve_params(
		self,
		params: VideoGenerationParams | dict[str, object] | None,
	) -> VideoGenerationParams:
		if params is None:
			return VideoGenerationParams()
		if isinstance(params, dict):
			return VideoGenerationParams.model_validate(params)
		return params
