"""video adapter union - single entry point for all video adapters.

no concrete video adapters are implemented yet. this module provides
the scaffolding for future provider-specific implementations.
"""

from __future__ import annotations

from .base.video_generation import (
	BaseVideoAdapter,
	GeneratedVideo,
	VideoGenerationParams,
	VideoGenerationResult,
	VideoProgressEvent,
)


# placeholder union - expand as concrete adapters are added
VideoAdapter = BaseVideoAdapter


def resolve_video_adapter(provider: str, adapter: str | None) -> str | None:
	"""resolve the adapter type string from provider and adapter variant."""
	# no concrete adapters yet
	return None


__all__ = [
	"BaseVideoAdapter",
	"GeneratedVideo",
	"VideoAdapter",
	"VideoGenerationParams",
	"VideoGenerationResult",
	"VideoProgressEvent",
	"resolve_video_adapter",
]
