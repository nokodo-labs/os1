"""audio model high-level interface - unified access to audio generation."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable
from typing import Any, ClassVar, Literal, overload

from pydantic import Field

from .adapter_enabled import AdapterEnabledBase, AdapterResolver
from .adapters.audio import AudioAdapter, resolve_audio_adapter
from .adapters.base.audio_generation import (
	AudioGenerationParams,
	AudioGenerationResult,
	AudioProgressEvent,
)


class AudioModel(AdapterEnabledBase[AudioAdapter]):
	"""high-level unified interface for audio generation models.

	usage:
		audio_model = AudioModel.create(
			"tts-1",
			adapter={"type": "openai.audio", "api_key": "..."},
		)
		result = await audio_model.generate("hello world")
	"""

	model_name: str = Field(..., description="model identifier")

	_adapter_resolver: ClassVar[AdapterResolver] = resolve_audio_adapter

	@classmethod
	def create(
		cls,
		model_name: str,
		*,
		adapter: AudioAdapter | dict[str, Any],
		**fields: Any,
	) -> AudioModel:
		"""create an audio model with explicit adapter configuration."""
		return super()._create(("model_name", model_name), adapter=adapter, **fields)

	@overload
	def generate(
		self,
		prompt: str,
		*,
		stream: Literal[False] = False,
		params: AudioGenerationParams | dict[str, object] | None = None,
	) -> Awaitable[AudioGenerationResult]: ...

	@overload
	def generate(
		self,
		prompt: str,
		*,
		stream: Literal[True],
		params: AudioGenerationParams | dict[str, object] | None = None,
	) -> AsyncIterator[AudioProgressEvent]: ...

	def generate(
		self,
		prompt: str,
		*,
		stream: bool = False,
		params: AudioGenerationParams | dict[str, object] | None = None,
	) -> Awaitable[AudioGenerationResult] | AsyncIterator[AudioProgressEvent]:
		"""generate audio from a text prompt.

		- stream=True = async iterator of progress events
		"""
		effective = self._resolve_params(params)
		if stream:
			return self.adapter.generate(
				prompt,
				self.model_name,
				stream=True,
				params=effective,
			)
		return self.adapter.generate(
			prompt,
			self.model_name,
			params=effective,
		)

	def _resolve_params(
		self,
		params: AudioGenerationParams | dict[str, object] | None,
	) -> AudioGenerationParams:
		if params is None:
			return AudioGenerationParams()
		if isinstance(params, dict):
			return AudioGenerationParams.model_validate(params)
		return params
