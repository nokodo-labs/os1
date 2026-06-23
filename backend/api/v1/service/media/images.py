"""image generation service - generate images via configured model + provider.

resolves the image model from the ORM (Model + Provider) and delegates
to the nokodo_ai ImageModel adapter architecture. creates File records
for each generated image via the file service.

usage:
    from api.v1.service.media.images import generate_image
    results = await generate_image(
        session, "a cat on a skateboard", owner_id="u123"
    )
"""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from api.models.file import FileSource
from api.settings import settings
from api.v1.service.chat.models import resolve_image_model
from api.v1.service.files import ingest_file
from nokodo_ai.adapters.images import ImageGenerationParams
from nokodo_ai.utils.typeid import TypeID


logger = logging.getLogger(__name__)


class MediaError(Exception):
	"""raised when a media generation operation fails."""


@dataclass(frozen=True, slots=True)
class ImageResult:
	"""result of an image generation request."""

	file_id: TypeID | None = None
	url: str | None = None
	b64_data: str | None = None
	mime_type: str = "image/png"
	prompt: str = ""
	revised_prompt: str | None = None


async def generate_image(
	session: AsyncSession,
	prompt: str,
	owner_id: TypeID,
	image: bytes | None = None,
	mask: bytes | None = None,
	negative_prompt: str | None = None,
	n: int | None = None,
	size: str | None = None,
	aspect_ratio: str | None = None,
	quality: str | None = None,
	model_id: TypeID | None = None,
	project_ids: list[TypeID] | None = None,
	message_id: TypeID | None = None,
	origin_session_id: str | None = None,
	agent_id: TypeID | None = None,
) -> list[ImageResult]:
	"""generate or edit images and persist them as File records.

	when no image is provided, creates images from the text prompt.
	when image bytes are provided, edits the image according to the prompt.

	args:
		session: database session for model resolution and file storage.
		prompt: text description / edit instruction.
		owner_id: user id who owns the generated files.
		image: source image bytes for editing (None = create).
		mask: optional mask bytes for edit area (white = edit, black = keep).
		negative_prompt: what to avoid (engine-dependent).
		n: number of images (None = use settings default).
		size: WIDTHxHEIGHT string (None = use settings default).
		aspect_ratio: aspect ratio like "16:9" (None = use default).
		quality: quality level (None = use default).
		model_id: override model id (None = use settings default).
		project_ids: optional projects to associate files with.
		message_id: optional message to associate files with.
		origin_session_id: SSE origin session for event dedup.
		agent_id: agent that triggered the generation (stored in file metadata).

	returns:
		list of ImageResult with file_id for each generated image.

	raises:
		MediaError: if generation fails or is not configured.
	"""
	img_settings = settings.ai.media.images

	if not img_settings.enabled:
		raise MediaError("image generation is not enabled")

	effective_model_id = model_id or img_settings.model
	if not effective_model_id:
		raise MediaError(
			"image generation model is not configured - "
			"set ai.media.images.model to a model id"
		)

	try:
		image_model = await resolve_image_model(session, TypeID(effective_model_id))
	except Exception:
		logger.exception("failed to resolve image model %s", effective_model_id)
		raise MediaError("failed to resolve image generation model") from None

	effective_n = min(n or img_settings.default_n, img_settings.max_n)

	param_kwargs: dict[str, object] = {
		"n": effective_n,
		"size": size or img_settings.default_size,
	}
	if aspect_ratio is not None:
		param_kwargs["aspect_ratio"] = aspect_ratio
	if quality is not None:
		param_kwargs["quality"] = quality
	if negative_prompt is not None:
		param_kwargs["negative_prompt"] = negative_prompt
	params = ImageGenerationParams.model_validate(param_kwargs)

	try:
		async with image_model:
			result = await image_model.generate(
				prompt, image=image, mask=mask, params=params
			)
	except Exception:
		logger.exception("image generation failed for model %s", effective_model_id)
		raise MediaError("image generation failed") from None

	# persist each generated image as a File record
	results: list[ImageResult] = []
	for i, img in enumerate(result.images):
		file_bytes: bytes | None = None
		if img.b64_data:
			file_bytes = base64.b64decode(img.b64_data)

		if file_bytes is not None:
			file = await ingest_file(
				session,
				data=file_bytes,
				owner_id=owner_id,
				filename=f"generated-{i + 1}.{img.mime_type.split('/')[-1]}",
				content_type=img.mime_type,
				source=FileSource.GENERATED,
				project_ids=project_ids,
				message_id=message_id,
				origin_session_id=origin_session_id,
			)
			# store generation metadata on the file record
			gen_meta: dict[str, str] = {
				"prompt": prompt,
				"_model_id": str(effective_model_id),
			}
			if agent_id:
				gen_meta["agent_id"] = str(agent_id)
			file.metadata_ = {**file.metadata_, **gen_meta}
			await session.flush()

			file_id = file.id
		else:
			file_id = None

		results.append(
			ImageResult(
				file_id=file_id,
				url=img.url,
				b64_data=img.b64_data,
				mime_type=img.mime_type,
				prompt=prompt,
				revised_prompt=img.revised_prompt,
			)
		)

	return results
