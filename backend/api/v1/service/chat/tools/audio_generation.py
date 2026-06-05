"""audio generation tool - generate audio/speech via configured engine.

delegates to the media generation service layer which handles
engine dispatch and settings resolution. generated audio clips are
persisted as File records and referenced through the attachments
system; the tool never inlines bytes itself.
"""

from __future__ import annotations

import json
import logging

from pydantic import BaseModel, ConfigDict, Field

from api.v1.service.chat.context import AppContext
from api.v1.service.chat.message_metadata import ATTACHMENTS_KEY
from api.v1.service.media import MediaError, generate_audio
from nokodo_ai.agents import AgentIterationSnapshot
from nokodo_ai.context import AgentContext, ToolCallContext
from nokodo_ai.messages import ToolMessage
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
		__state__: AgentIterationSnapshot[AppContext],
		__agent_context__: AgentContext,
		__tool_call_context__: ToolCallContext,
		__app_context__: AppContext | None,
		**kwargs: object,
	) -> ToolMessage:
		if __app_context__ is None:
			return self.error("app context is required", __tool_call_context__)
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
				__tool_call_context__,
			)

		count = len(results)
		label = "clip" if count == 1 else "clips"
		metadata = dict(__tool_call_context__.metadata or {})
		refs = [{"type": "file", "id": str(r.file_id)} for r in results if r.file_id]
		if refs:
			metadata[ATTACHMENTS_KEY] = refs
		return ToolMessage(
			tool_call_id=__tool_call_context__.tool_call_id,
			tool_output=json.dumps(
				{
					"status": "success",
					"message": f"generated {count} audio {label}",
					"count": count,
					"file_ids": [r.file_id for r in results if r.file_id],
				}
			),
			metadata=metadata,
			is_error=False,
		)
