"""run (llm execution) schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from api.schemas.message import Message
from nokodo_ai.utils.typeid import TypeID


class ClientContext(BaseModel):
	"""optional runtime context sent by the client with each agent run.

	the frontend collects device and environment data that the agent
	can use to personalise responses (e.g. timezone-aware greetings).
	all fields are optional — the backend gracefully handles missing data.
	"""

	timezone: str | None = Field(
		default=None,
		description="IANA timezone identifier, e.g. 'America/New_York'",
	)
	language: str | None = Field(
		default=None,
		description="BCP 47 language tag, e.g. 'en-US'",
	)
	os: str | None = Field(
		default=None,
		description="operating system name, e.g. 'Windows', 'macOS', 'Android'",
	)
	browser: str | None = Field(
		default=None,
		description="browser name, e.g. 'Chrome', 'Firefox', 'Safari'",
	)
	pwa_installed: bool | None = Field(
		default=None,
		alias="pwaInstalled",
		description="whether the app is running as an installed PWA",
	)
	screen_width: int | None = Field(
		default=None,
		alias="screenWidth",
		description="device screen width in pixels",
	)
	screen_height: int | None = Field(
		default=None,
		alias="screenHeight",
		description="device screen height in pixels",
	)
	is_mobile: bool | None = Field(
		default=None,
		alias="isMobile",
		description="whether the client is on a mobile device",
	)


class ThreadRunRequest(BaseModel):
	"""
	payload to run a thread with an agent,
	optionally appending a new user message.
	"""

	agent_id: TypeID
	stream: Literal[True] = True
	input: str | None = None
	parent_id: TypeID | None = None
	client_context: ClientContext | None = Field(
		default=None,
		alias="clientContext",
		description="optional device/environment context from the client",
	)


class ThreadRunResponse(BaseModel):
	"""
	response containing all messages produced by a run.

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
