"""image generation tool - generate or edit images via configured engine.

delegates to the media generation service layer which handles
engine dispatch and settings resolution. generated images are
persisted as File records and referenced through the attachments
system; the model resolves them with a file tool or the inline
fallback, never inline bytes from this tool.

the tool supports both text-to-image creation and editing an
existing image: pass file_id to edit, omit for pure generation.
"""

from __future__ import annotations

import base64
import json
import logging

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.v1.service.auth import Principal
from api.v1.service.chat.context import AppContext
from api.v1.service.chat.message_metadata import ATTACHMENTS_KEY
from api.v1.service.files import read_file_base64
from api.v1.service.media import MediaError, generate_image
from nokodo_ai.agents import AgentIterationSnapshot
from nokodo_ai.context import AgentContext, ToolCallContext
from nokodo_ai.messages import ToolMessage
from nokodo_ai.tool import Tool
from nokodo_ai.types.json import JSONObject
from nokodo_ai.utils.typeid import TypeID


logger = logging.getLogger(__name__)


class GenerateImageInput(BaseModel):
	"""input schema for generate_image tool."""

	model_config = ConfigDict(extra="forbid")

	prompt: str = Field(
		...,
		description=(
			"a detailed description of the image to generate or the "
			"edits to make. be specific and descriptive for best results."
		),
	)
	file_id: TypeID | None = Field(
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


async def _load_file_bytes(
	file_id: TypeID, session: AsyncSession, principal: Principal
) -> bytes | None:
	"""load raw bytes for a stored file (access-checked)."""
	b64 = await read_file_base64(file_id, session, principal=principal)
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
		__state__: AgentIterationSnapshot[AppContext],
		__agent_context__: AgentContext,
		__tool_call_context__: ToolCallContext,
		__app_context__: AppContext | None,
		**kwargs: object,
	) -> ToolMessage:
		if __app_context__ is None:
			return self.error("app context is required", __tool_call_context__)
		inp = GenerateImageInput.model_validate(kwargs)

		# resolve source image bytes for editing, if requested
		image_bytes: bytes | None = None
		if inp.file_id:
			image_bytes = await _load_file_bytes(
				inp.file_id,
				__app_context__.session,
				principal=__app_context__.principal,
			)
			if image_bytes is None:
				return self.error(
					f"could not load image file '{inp.file_id}'.",
					__tool_call_context__,
				)

		try:
			results = await generate_image(
				__app_context__.session,
				inp.prompt,
				owner_id=__app_context__.user_id,
				image=image_bytes,
				negative_prompt=inp.negative_prompt,
				n=inp.n,
				size=inp.size,
				agent_id=__app_context__.agent_id,
			)
		except MediaError:
			logger.exception("image generation failed")
			return self.error(
				"image generation failed. please try again.",
				__tool_call_context__,
			)

		count = len(results)
		action = "edited" if inp.file_id else "generated"
		label = "image" if count == 1 else "images"
		metadata: dict = __tool_call_context__.metadata or {}
		refs = [{"type": "file", "id": str(r.file_id)} for r in results if r.file_id]
		if refs:
			metadata[ATTACHMENTS_KEY] = refs
		return ToolMessage(
			tool_call_id=__tool_call_context__.tool_call_id,
			tool_output=json.dumps(
				{
					"status": "success",
					"message": f"{action} {count} {label}",
					"count": count,
					"file_ids": [r.file_id for r in results if r.file_id],
				}
			),
			metadata=metadata,
			is_error=False,
		)
