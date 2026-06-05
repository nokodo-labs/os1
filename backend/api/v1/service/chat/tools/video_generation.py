"""video generation tool - generate videos via configured engine.

delegates to the media generation service layer which handles
engine dispatch and settings resolution. generated videos are
persisted as File records and referenced through the attachments
system; the tool never inlines bytes itself.
"""

from __future__ import annotations

import json
import logging

from pydantic import BaseModel, ConfigDict, Field

from api.v1.service.chat.context import AppContext
from api.v1.service.chat.message_metadata import ATTACHMENTS_KEY
from api.v1.service.media import MediaError, generate_video
from nokodo_ai.agents import AgentIterationSnapshot
from nokodo_ai.context import AgentContext, ToolCallContext
from nokodo_ai.messages import ToolMessage
from nokodo_ai.tool import Tool
from nokodo_ai.types.json import JSONObject


logger = logging.getLogger(__name__)


class GenerateVideoInput(BaseModel):
	"""input schema for generate_video tool."""

	model_config = ConfigDict(extra="forbid")

	prompt: str = Field(
		...,
		description=(
			"a detailed description of the video to generate. "
			"be specific about motion, scene, and style."
		),
	)
	duration: float | None = Field(
		default=None,
		description="target video duration in seconds.",
	)
	size: str | None = Field(
		default=None,
		description=(
			"video size in WIDTHxHEIGHT format (e.g. '1280x720'). omit for default."
		),
	)
	aspect_ratio: str | None = Field(
		default=None,
		description="aspect ratio like '16:9' (omit for default).",
	)


class GenerateVideoTool(Tool[AppContext]):
	"""generate videos from text descriptions."""

	name: str = Field(default="generate_video")
	description: str = Field(
		default=(
			"generate a video from a text description. use this when the "
			"user requests video generation or wants to create animated "
			"visual content."
		),
	)
	parameters: JSONObject = Field(
		default_factory=lambda: GenerateVideoInput.model_json_schema(),
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
		inp = GenerateVideoInput.model_validate(kwargs)

		try:
			results = await generate_video(
				__app_context__.session,
				inp.prompt,
				owner_id=__app_context__.user_id,
				duration=inp.duration,
				size=inp.size,
				aspect_ratio=inp.aspect_ratio,
				agent_id=__app_context__.agent_id,
			)
		except MediaError:
			logger.exception("video generation failed")
			return self.error(
				"video generation failed. please try again.",
				__tool_call_context__,
			)

		count = len(results)
		label = "video" if count == 1 else "videos"
		metadata = dict(__tool_call_context__.metadata or {})
		refs = [{"type": "file", "id": str(r.file_id)} for r in results if r.file_id]
		if refs:
			metadata[ATTACHMENTS_KEY] = refs
		return ToolMessage(
			tool_call_id=__tool_call_context__.tool_call_id,
			tool_output=json.dumps(
				{
					"status": "success",
					"message": f"generated {count} {label}",
					"count": count,
					"file_ids": [r.file_id for r in results if r.file_id],
				}
			),
			metadata=metadata,
			is_error=False,
		)
