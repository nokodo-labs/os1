"""audio generation tool - generate audio/speech via configured engine.

delegates to the media generation service layer which handles
engine dispatch and settings resolution. generated audio clips are
persisted as File records and attached to the tool response.
"""

from __future__ import annotations

import json
import logging

from pydantic import BaseModel, ConfigDict, Field

from api.v1.service.chat.context import AppContext
from api.v1.service.media import MediaError, generate_audio
from api.v1.service.media.audio import AudioResult
from nokodo_ai.context import AgentContext
from nokodo_ai.messages import FileContent, ToolAttachment, ToolMessage
from nokodo_ai.tool import Tool
from nokodo_ai.types.json import JSONObject


logger = logging.getLogger(__name__)


class GenerateAudioInput(BaseModel):
	"""input schema for generate_audio tool."""

	model_config = ConfigDict(extra="forbid")

	prompt: str = Field(
		...,
		description=(
			"the text to synthesize into speech, or a description "
			"of the audio to generate."
		),
	)
	voice: str | None = Field(
		default=None,
		description="voice identifier for text-to-speech (engine-dependent).",
	)
	speed: float | None = Field(
		default=None,
		description="playback speed factor (e.g. 1.0 = normal, 1.5 = faster).",
		ge=0.25,
		le=4.0,
	)


def _build_attachments(
	results: list[AudioResult],
) -> list[ToolAttachment]:
	"""build FileContent attachments from generation results."""
	attachments: list[ToolAttachment] = []
	for clip in results:
		if clip.file_id:
			attachments.append(
				FileContent(
					url=f"/v1/files/{clip.file_id}/content",
					filename=f"generated.{clip.mime_type.split('/')[-1]}",
					media_type=clip.mime_type,
					metadata={"file_id": clip.file_id},
				)
			)
	return attachments


class GenerateAudioTool(Tool[AppContext]):
	"""generate audio or speech from text."""

	name: str = Field(default="generate_audio")
	description: str = Field(
		default=(
			"generate audio from text - either text-to-speech synthesis "
			"or audio content generation. use this when the user requests "
			"audio, voice, or speech generation."
		),
	)
	parameters: JSONObject = Field(
		default_factory=lambda: GenerateAudioInput.model_json_schema(),
	)

	async def call(
		self,
		__agent_context__: AgentContext,
		__app_context__: AppContext | None,
		**kwargs: object,
	) -> ToolMessage:
		if __app_context__ is None:
			return self.error("app context is required", __agent_context__)
		inp = GenerateAudioInput.model_validate(kwargs)

		try:
			results = await generate_audio(
				__app_context__.session,
				inp.prompt,
				owner_id=__app_context__.user_id,
				voice=inp.voice,
				speed=inp.speed,
				agent_id=__app_context__.agent_id,
			)
		except MediaError:
			logger.exception("audio generation failed")
			return self.error(
				"audio generation failed. please try again.",
				__agent_context__,
			)

		attachments = _build_attachments(results)
		count = len(results)
		label = "clip" if count == 1 else "clips"
		return ToolMessage(
			tool_call_id=__agent_context__.tool_call_id,
			tool_output=json.dumps(
				{
					"status": "success",
					"message": f"generated {count} audio {label}",
					"count": count,
					"file_ids": [r.file_id for r in results if r.file_id],
				}
			),
			metadata=__agent_context__.metadata,
			is_error=False,
			attachments=attachments,
		)
