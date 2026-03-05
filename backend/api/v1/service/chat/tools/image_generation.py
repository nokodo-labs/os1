"""image generation tool - generate or edit images via configured engine.

delegates to the media generation service layer which handles
engine dispatch and settings resolution. generated images are
persisted as File records and attached to the tool response.

the tool supports both text-to-image creation and editing an
existing image: pass file_id to edit, omit for pure generation.
the agent sees all attached image file_ids from the conversation context.
"""

from __future__ import annotations

import base64
import logging
from collections.abc import Sequence

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.v1.service.chat.context import AppContext
from api.v1.service.files import resolve_file_data
from api.v1.service.media import MediaError, generate_image
from api.v1.service.media.images import ImageResult
from nokodo_ai.context import AgentContext
from nokodo_ai.messages import ImageContent, ToolAttachment, ToolMessage
from nokodo_ai.tool import Tool
from nokodo_ai.types.json import JSONObject


logger = logging.getLogger(__name__)


class GenerateImageInput(BaseModel):
	"""input schema for generate_image tool."""

	prompt: str = Field(
		...,
		description=(
			"a detailed description of the image to generate or the "
			"edits to make. be specific and descriptive for best results."
		),
	)
	file_id: str | None = Field(
		default=None,
		description=(
			"file ID of an existing image to edit. "
			"omit for text-to-image generation. "
			"use one of the image attachment file IDs or search a file ID."
		),
	)
	negative_prompt: str | None = Field(
		default=None,
		description=(
			"description of what should NOT appear in the result (engine-dependent)."
		),
	)
	n: int = Field(
		default=1,
		description="number of images to generate (1-4).",
		ge=1,
		le=4,
	)
	size: str | None = Field(
		default=None,
		description=(
			"image size in WIDTHxHEIGHT format (e.g. '1024x1024'). omit for default."
		),
	)


def _build_attachments(results: Sequence[ImageResult]) -> list[ToolAttachment]:
	"""build ImageContent attachments from generation results."""
	attachments: list[ToolAttachment] = []
	for img in results:
		if img.file_id:
			attachments.append(
				ImageContent(
					url=f"/v1/files/{img.file_id}/content",
					media_type=img.mime_type,
					metadata={"file_id": img.file_id},
				)
			)
	return attachments


async def _load_file_bytes(file_id: str, session: AsyncSession) -> bytes | None:
	"""load raw bytes for a stored file (no access check - tool context)."""
	_, b64 = await resolve_file_data(file_id, session)
	if b64:
		return base64.b64decode(b64)
	return None


class GenerateImageTool(Tool[AppContext]):
	"""generate images from text, or edit an existing image."""

	name: str = Field(default="generate_image")
	description: str = Field(
		default=(
			"generate images from a text description, or edit an existing "
			"image using a text prompt. use this when the user requests image "
			"generation or wants to modify an existing image. "
			"pass file_id to edit a specific image already in context."
		),
	)
	parameters: JSONObject = Field(
		default_factory=lambda: GenerateImageInput.model_json_schema(),
	)

	async def call(
		self,
		__agent_context__: AgentContext,
		__app_context__: AppContext | None,
		**kwargs: object,
	) -> ToolMessage:
		if __app_context__ is None:
			return self.error("app context is required", __agent_context__)
		inp = GenerateImageInput.model_validate(kwargs)

		# resolve source image bytes for editing, if requested
		image_bytes: bytes | None = None
		if inp.file_id:
			image_bytes = await _load_file_bytes(inp.file_id, __app_context__.session)
			if image_bytes is None:
				return self.error(
					f"could not load image file '{inp.file_id}'.",
					__agent_context__,
				)

		try:
			results = await generate_image(
				__app_context__.session,
				inp.prompt,
				owner_id=str(__app_context__.user_id),
				image=image_bytes,
				negative_prompt=inp.negative_prompt,
				n=inp.n,
				size=inp.size,
			)
		except MediaError as exc:
			return self.error(str(exc), __agent_context__)

		attachments = _build_attachments(results)
		count = len(results)
		action = "edited" if inp.file_id else "generated"
		summary = (
			f"{action} {count} image{'s' if count != 1 else ''}. "
			"images are attached above this message."
		)

		return ToolMessage(
			tool_call_id=__agent_context__.tool_call_id,
			tool_output=summary,
			metadata=__agent_context__.metadata,
			is_error=False,
			attachments=attachments,
		)
