"""run (llm execution) schemas."""

from __future__ import annotations

from datetime import datetime

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


# base run fields shared across request types


class _RunBase(BaseModel):
	"""fields common to every run request."""

	agent_id: TypeID
	input: str | None = None
	stream: bool = Field(
		default=True,
		description="when true (default) the response is an SSE stream; "
		"when false a JSON response is returned (not yet implemented).",
	)
	client_context: ClientContext | None = Field(
		default=None,
		alias="clientContext",
		description="optional device/environment context from the client",
	)


# run request variants


class RunRequest(_RunBase):
	"""POST /runs — run on an existing thread, or ephemeral (no thread).

	when ``thread_id`` is present the run continues that thread.
	when omitted the run is **ephemeral** — no thread is created or
	persisted (not yet implemented).

	``input`` is required for ephemeral runs and optional when continuing
	an existing thread (omit for regeneration / retry).
	"""

	thread_id: TypeID | None = None
	parent_id: TypeID | None = None


class ThreadCreateAndRunRequest(_RunBase):
	"""POST /threads/create_and_run — create a thread then run immediately.

	``input`` is required (a new thread needs at least one user message).
	the SSE stream emits a ``thread_created`` event before normal run events.
	"""

	is_temporary: bool = False
	tags: list[str] = Field(default_factory=list)
	project_ids: list[TypeID] = Field(default_factory=list)


# response schemas


class ThreadRunResponse(BaseModel):
	"""response containing all messages produced by a run.

	an agent run can produce multiple messages:
	- assistant message with tool calls
	- tool result messages
	- more assistant messages
	- … repeat until final assistant message

	the messages list contains all new messages produced during the run.
	"""

	thread_id: TypeID
	user_message: Message | None = None
	messages: list[Message]


class ActiveRunOut(BaseModel):
	"""lightweight snapshot of an in-memory active run."""

	run_id: str
	thread_id: str
	agent_id: str
	user_id: str
	state: str
	started_at: datetime
	updated_at: datetime
