"""audio adapter union - single entry point for all audio adapters.

no concrete audio adapters are implemented yet. this module provides
the scaffolding for future provider-specific implementations.
"""

from __future__ import annotations

from .base.audio_generation import (
	AudioGenerationParams,
	AudioGenerationResult,
	AudioOutputFormat,
	AudioProgressEvent,
	BaseAudioAdapter,
	GeneratedAudio,
)


# placeholder union - expand as concrete adapters are added
AudioAdapter = BaseAudioAdapter


def resolve_audio_adapter(provider: str, adapter: str | None) -> str | None:
	"""resolve the adapter type string from provider and adapter variant."""
	# no concrete adapters yet
	return None


__all__ = [
	"AudioAdapter",
	"AudioGenerationParams",
	"AudioGenerationResult",
	"AudioOutputFormat",
	"AudioProgressEvent",
	"BaseAudioAdapter",
	"GeneratedAudio",
	"resolve_audio_adapter",
]
