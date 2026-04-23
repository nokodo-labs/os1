"""base audio generation adapter - capability ABC for audio gen APIs."""

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
class GeneratedAudio:
	"""a single generated audio result."""

	url: str | None = None
	b64_data: str | None = None
	mime_type: str = "audio/mp3"
	duration_seconds: float | None = None
	revised_prompt: str | None = None


@dataclass(frozen=True, slots=True)
class AudioGenerationResult:
	"""result of an audio generation request."""

	clips: list[GeneratedAudio] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class AudioProgressEvent:
	"""progress event emitted during audio generation."""

	step: int
	total_steps: int | None = None
	progress: float | None = None
	partial_audio: GeneratedAudio | None = None


# --- parameter types ---


AudioOutputFormat = Literal["mp3", "wav", "flac", "opus", "aac"]


class AudioGenerationParams(Base):
	"""generation options shared across audio adapters."""

	model_config = ConfigDict(extra="forbid")

	voice: str | None = None
	speed: float | None = None
	output_format: AudioOutputFormat | None = None
	duration: float | None = None
	quality: Literal["standard", "hd"] | None = None


# --- base adapter ---


class BaseAudioAdapter(BaseAdapter, Base, ABC):
	"""capability ABC for audio generation APIs.

	adapters implementing this interface provide a single generate()
	method that handles text-to-speech and audio creation, with
	optional streaming support.

	- stream=True = async iterator of progress events
	"""

	@overload
	def generate(
		self,
		prompt: str,
		model: str,
		*,
		stream: Literal[False] = False,
		params: AudioGenerationParams | None = None,
	) -> Awaitable[AudioGenerationResult]: ...

	@overload
	def generate(
		self,
		prompt: str,
		model: str,
		*,
		stream: Literal[True],
		params: AudioGenerationParams | None = None,
	) -> AsyncIterator[AudioProgressEvent]: ...

	def generate(
		self,
		prompt: str,
		model: str,
		*,
		stream: bool = False,
		params: AudioGenerationParams | None = None,
	) -> Awaitable[AudioGenerationResult] | AsyncIterator[AudioProgressEvent]:
		"""generate audio from a text prompt.

		args:
			prompt: text description or script for synthesis.
			model: model identifier.
			stream: if True, returns an async iterator of progress events.
			params: generation parameters.
		"""
		params = params or AudioGenerationParams()
		if stream:
			return self._generate_stream(prompt, model, params=params)
		return self._create(prompt, model, params=params)

	@abstractmethod
	async def _create(
		self,
		prompt: str,
		model: str,
		*,
		params: AudioGenerationParams,
	) -> AudioGenerationResult:
		"""create audio from a text prompt."""
		raise NotImplementedError

	async def _generate_stream(
		self,
		prompt: str,
		model: str,
		*,
		params: AudioGenerationParams,
	) -> AsyncIterator[AudioProgressEvent]:
		"""streaming generation with progress events.

		default implementation wraps _create as a single event.
		adapters can override for true streaming support.
		"""
		result = await self._create(prompt, model, params=params)
		clip = result.clips[0] if result.clips else None
		yield AudioProgressEvent(step=1, total_steps=1, progress=1.0, partial_audio=clip)
