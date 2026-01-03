"""run (llm execution) schemas."""

from __future__ import annotations

from pydantic import BaseModel

from api.schemas.message import Message
from nokodo_ai.utils.typeid import TypeID


class ThreadRunRequest(BaseModel):
	"""Payload to run a thread with an agent, optionally appending a new user message."""

	agent_id: TypeID
	input: str | None = None


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
