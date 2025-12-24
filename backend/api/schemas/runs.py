"""run (llm execution) schemas."""

from __future__ import annotations

from pydantic import BaseModel, model_validator

from api.schemas.message import Message
from nokodo_ai.utils.typeid import TypeID


class ThreadRunRequest(BaseModel):
	"""Payload to run a thread, optionally appending a new user message."""

	agent_id: TypeID | None = None
	model_id: TypeID | None = None
	model: str | None = None
	input: str | None = None
	temperature: float | None = None
	max_tokens: int | None = None

	@model_validator(mode="after")
	def _validate_selector(self) -> ThreadRunRequest:
		if self.agent_id is None and self.model_id is None and not self.model:
			raise ValueError("agent_id, model_id, or model is required")
		return self


class ThreadRunResponse(BaseModel):
	"""response containing all messages produced by a run.

	an agent run can produce multiple messages:
	- assistant message with tool calls
	- tool result messages
	- more assistant messages
	- ... repeat until final assistant message

	the messages list contains all new messages produced during the run.
	"""

	thread_id: TypeID
	user_message: Message | None = None
	messages: list[Message]
