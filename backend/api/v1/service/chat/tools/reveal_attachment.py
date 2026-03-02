"""reveal attachment tool - agent-initiated attachment reactivation.

validates file_ids, returns success JSON, and emits attachment.revealed
events so the frontend and filter can track the reveal persistently.

the tool call's existence as a ToolMessage in the thread is ALSO
read by the decay filter (via _find_reveals) as a fallback, ensuring
correctness even if the async event persist hasn't completed.
"""

from __future__ import annotations

import json

from pydantic import BaseModel, Field

from api.models.event import Event, EventScope
from api.models.event_types import EventType
from api.v1.service.chat.context import AppContext
from nokodo_ai.context import AgentContext
from nokodo_ai.messages import ToolMessage
from nokodo_ai.tool import Tool
from nokodo_ai.types.json import JSONObject


class RevealAttachmentInput(BaseModel):
	"""input schema for the reveal_attachment tool."""

	file_ids: list[str] = Field(
		...,
		min_length=1,
		description=(
			"list of attachment file ids to reveal. "
			"ids are found in the referenced attachments "
			"section of the system prompt."
		),
	)


class RevealAttachmentTool(Tool[AppContext]):
	"""re-activate referenced attachments so they appear in full context.

	when an attachment has decayed to reference state, the agent can
	call this tool to bring it back to active state. the tool itself
	just validates and returns success - the decay filter reads the
	tool call from the message history to reset the decay timer.
	"""

	name: str = Field(default="reveal_attachment")
	description: str = Field(
		default=(
			"re-activate one or more referenced attachments so you "
			"can see their full content on the next turn. only use "
			"this when the attachment summary is insufficient and you "
			"genuinely need to see the original file. check the "
			"referenced attachments list for available ids.\n\n"
			"IMPORTANT: before revealing, always check if the "
			"summary in the referenced attachments section answers "
			"your question. revealing costs tokens."
		)
	)
	parameters: JSONObject = Field(
		default_factory=lambda: RevealAttachmentInput.model_json_schema()
	)

	async def call(
		self,
		__agent_context__: AgentContext,
		__app_context__: AppContext | None,
		**kwargs: object,
	) -> ToolMessage:
		raw_ids = kwargs.get("file_ids")
		if not isinstance(raw_ids, list) or not raw_ids:
			return self.error(
				json.dumps({"error": "file_ids must be a non-empty list"}),
				__agent_context__,
			)

		file_ids = [str(fid) for fid in raw_ids if fid]
		if not file_ids:
			return self.error(
				json.dumps({"error": "no valid file ids provided"}),
				__agent_context__,
			)

		# emit attachment.revealed events for frontend + persistence
		if __app_context__ is not None:
			thread_id = (
				str(__app_context__.thread_id) if __app_context__.thread_id else None
			)
			for fid in file_ids:
				event = Event(
					scope=EventScope.THREAD,
					scope_id=thread_id,
					type=EventType.ATTACHMENT_REVEALED,
					thread_id=thread_id,
					data={"file_id": fid, "source": "agent"},
				)
				await __app_context__.event_emitter(event)

		return self.success(
			json.dumps({"revealed": file_ids}),
			__agent_context__,
		)
