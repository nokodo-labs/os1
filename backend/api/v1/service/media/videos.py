"""video generation service - generate videos via configured model + provider.

resolves the video model from the ORM (Model + Provider) and delegates
to the nokodo_ai VideoModel adapter architecture. creates File records
for each generated video via the file service.

usage:
    from api.v1.service.media.videos import generate_video
    results = await generate_video(
        session, "a cat skateboarding", owner_id="u123"
    )
"""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from api.models.file import FileSource
from api.settings import settings
from api.v1.service.chat.models import resolve_video_model
from api.v1.service.files import store_file
from api.v1.service.media.images import MediaError
from nokodo_ai.adapters.videos import VideoGenerationParams
from nokodo_ai.utils.typeid import TypeID


logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class VideoResult:
	"""result of a video generation request."""

	file_id: TypeID | None = None
	url: str | None = None
	b64_data: str | None = None
	mime_type: str = "video/mp4"
	duration_seconds: float | None = None
	prompt: str = ""
	revised_prompt: str | None = None


async def generate_video(
	session: AsyncSession,
	prompt: str,
	owner_id: TypeID,
	image: bytes | None = None,
	duration: float | None = None,
	size: str | None = None,
	aspect_ratio: str | None = None,
	model_id: TypeID | None = None,
	project_ids: list[TypeID] | None = None,
	message_id: TypeID | None = None,
	origin_session_id: str | None = None,
	agent_id: TypeID | None = None,
) -> list[VideoResult]:
	"""generate a video and persist it as a File record.

	args:
		session: database session for model resolution and file storage.
		prompt: text description of the video to generate.
		owner_id: user id who owns the generated files.
		image: optional reference image bytes for image-to-video.
		duration: target video duration in seconds.
		size: WIDTHxHEIGHT string.
		aspect_ratio: aspect ratio like "16:9".
		model_id: override model id.
		project_ids: optional projects to associate files with.
		message_id: optional message to associate files with.
		origin_session_id: SSE origin session for event dedup.
		agent_id: agent that triggered the generation (stored in file metadata).

	returns:
		list of VideoResult with file_id for each generated video.

	raises:
		MediaError: if generation fails or is not configured.
	"""
	vid_settings = settings.ai.media.videos

	if not vid_settings.enabled:
		raise MediaError("video generation is not enabled")

	effective_model_id = model_id or getattr(vid_settings, "model", None)
	if not effective_model_id:
		raise MediaError(
			"video generation model is not configured - "
			"set ai.media.videos.model to a model id"
		)

	try:
		video_model = await resolve_video_model(session, TypeID(effective_model_id))
	except Exception:
		logger.exception("failed to resolve video model %s", effective_model_id)
		raise MediaError("failed to resolve video generation model") from None

	param_kwargs: dict[str, object] = {}
	if duration is not None:
		param_kwargs["duration"] = duration
	if size is not None:
		param_kwargs["size"] = size
	if aspect_ratio is not None:
		param_kwargs["aspect_ratio"] = aspect_ratio
	params = VideoGenerationParams.model_validate(param_kwargs)

	try:
		async with video_model:
			result = await video_model.generate(prompt, image=image, params=params)
	except Exception:
		logger.exception("video generation failed for model %s", effective_model_id)
		raise MediaError("video generation failed") from None

	# persist each generated video as a File record
	results: list[VideoResult] = []
	for i, vid in enumerate(result.videos):
		file_bytes: bytes | None = None
		if vid.b64_data:
			file_bytes = base64.b64decode(vid.b64_data)

		if file_bytes is not None:
			ext = vid.mime_type.split("/")[-1] if "/" in vid.mime_type else "mp4"
			file = await store_file(
				session,
				data=file_bytes,
				owner_id=owner_id,
				filename=f"generated-{i + 1}.{ext}",
				content_type=vid.mime_type,
				source=FileSource.GENERATED,
				project_ids=project_ids,
				message_id=message_id,
				origin_session_id=origin_session_id,
			)
			# store generation metadata on the file record
			gen_meta: dict[str, str] = {"prompt": prompt}
			if agent_id:
				gen_meta["agent_id"] = str(agent_id)
			file.metadata_ = {**file.metadata_, **gen_meta}
			await session.flush()

			file_id = file.id
		else:
			file_id = None

		results.append(
			VideoResult(
				file_id=file_id,
				url=vid.url,
				b64_data=vid.b64_data,
				mime_type=vid.mime_type,
				duration_seconds=vid.duration_seconds,
				prompt=prompt,
				revised_prompt=vid.revised_prompt,
			)
		)

	return results
