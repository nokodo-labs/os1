"""audio generation service - generate audio via configured model + provider.

resolves the audio model from the ORM (Model + Provider) and delegates
to the nokodo_ai AudioModel adapter architecture. creates File records
for each generated audio clip via the file service.

usage:
    from api.v1.service.media.audio import generate_audio
    results = await generate_audio(
        session, "hello world", owner_id="u123"
    )
"""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from api.models.file import FileSource
from api.settings import settings
from api.v1.service.chat.models import resolve_audio_model
from api.v1.service.files import store_file
from api.v1.service.media.images import MediaError
from nokodo_ai.adapters.audio import AudioGenerationParams
from nokodo_ai.utils.typeid import TypeID


logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class AudioResult:
	"""result of an audio generation request."""

	file_id: TypeID | None = None
	url: str | None = None
	b64_data: str | None = None
	mime_type: str = "audio/mp3"
	duration_seconds: float | None = None
	prompt: str = ""
	revised_prompt: str | None = None


async def generate_audio(
	session: AsyncSession,
	prompt: str,
	owner_id: TypeID,
	voice: str | None = None,
	speed: float | None = None,
	output_format: str | None = None,
	model_id: TypeID | None = None,
	project_ids: list[TypeID] | None = None,
	message_id: TypeID | None = None,
	origin_session_id: str | None = None,
	agent_id: TypeID | None = None,
) -> list[AudioResult]:
	"""generate audio and persist it as a File record.

	args:
		session: database session for model resolution and file storage.
		prompt: text to synthesize or description of audio to generate.
		owner_id: user id who owns the generated files.
		voice: voice identifier for TTS.
		speed: playback speed factor.
		output_format: output audio format (mp3, wav, etc).
		model_id: override model id.
		project_ids: optional projects to associate files with.
		message_id: optional message to associate files with.
		origin_session_id: SSE origin session for event dedup.
		agent_id: agent that triggered the generation (stored in file metadata).

	returns:
		list of AudioResult with file_id for each generated audio clip.

	raises:
		MediaError: if generation fails or is not configured.
	"""
	audio_settings = settings.ai.media.audio

	if not audio_settings.enabled:
		raise MediaError("audio generation is not enabled")

	effective_model_id = model_id or getattr(audio_settings, "model", None)
	if not effective_model_id:
		raise MediaError(
			"audio generation model is not configured - "
			"set ai.media.audio.model to a model id"
		)

	try:
		audio_model = await resolve_audio_model(session, TypeID(effective_model_id))
	except Exception:
		logger.exception("failed to resolve audio model %s", effective_model_id)
		raise MediaError("failed to resolve audio generation model") from None

	param_kwargs: dict[str, object] = {}
	if voice is not None:
		param_kwargs["voice"] = voice
	if speed is not None:
		param_kwargs["speed"] = speed
	if output_format is not None:
		param_kwargs["output_format"] = output_format
	params = AudioGenerationParams.model_validate(param_kwargs)

	try:
		async with audio_model:
			result = await audio_model.generate(prompt, params=params)
	except Exception:
		logger.exception("audio generation failed for model %s", effective_model_id)
		raise MediaError("audio generation failed") from None

	# persist each generated audio clip as a File record
	results: list[AudioResult] = []
	for i, clip in enumerate(result.clips):
		file_bytes: bytes | None = None
		if clip.b64_data:
			file_bytes = base64.b64decode(clip.b64_data)

		if file_bytes is not None:
			ext = clip.mime_type.split("/")[-1] if "/" in clip.mime_type else "mp3"
			file = await store_file(
				session,
				data=file_bytes,
				owner_id=owner_id,
				filename=f"generated-{i + 1}.{ext}",
				content_type=clip.mime_type,
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
			AudioResult(
				file_id=file_id,
				url=clip.url,
				b64_data=clip.b64_data,
				mime_type=clip.mime_type,
				duration_seconds=clip.duration_seconds,
				prompt=prompt,
				revised_prompt=clip.revised_prompt,
			)
		)

	return results
