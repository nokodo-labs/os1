"""media generation service package."""

from api.v1.service.media.audio import (
	AudioResult,
	generate_audio,
)
from api.v1.service.media.images import (
	ImageResult,
	MediaError,
	generate_image,
)
from api.v1.service.media.videos import (
	VideoResult,
	generate_video,
)


__all__ = [
	"AudioResult",
	"ImageResult",
	"MediaError",
	"VideoResult",
	"generate_audio",
	"generate_image",
	"generate_video",
]
