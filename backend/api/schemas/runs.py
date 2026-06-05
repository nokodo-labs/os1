"""run (chat model execution) schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from api.schemas.message import Message, ResourceAttachment
from nokodo_ai.utils.typeid import TypeID


class ClientContext(BaseModel):
	"""optional runtime context sent by the client with each agent run.

	the frontend collects device and environment data that the agent
	can use to personalise responses (e.g. timezone-aware greetings).
	all fields are optional - the backend gracefully handles missing data.
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
	user_agent: str | None = Field(
		default=None,
		alias="userAgent",
		description="raw browser user-agent string",
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
	offline: bool | None = Field(
		default=None,
		description="whether the device is currently offline",
	)
	display_mode: str | None = Field(
		default=None,
		alias="displayMode",
		description="browser display mode (browser, standalone, fullscreen, etc)",
	)
	preferred_color_scheme: str | None = Field(
		default=None,
		alias="preferredColorScheme",
		description="preferred color scheme (dark, light, or no-preference)",
	)
	prefers_reduced_motion: bool | None = Field(
		default=None,
		alias="prefersReducedMotion",
		description="whether the user prefers reduced motion",
	)
	prefers_contrast: str | None = Field(
		default=None,
		alias="prefersContrast",
		description="contrast preference (more, less, or no-preference)",
	)
	idle_state: str | None = Field(
		default=None,
		alias="idleState",
		description="activity state detected by the client (active or idle)",
	)
	gamepad_count: int | None = Field(
		default=None,
		alias="gamepadCount",
		description="number of currently connected gamepads",
	)
	gamepads: list[str] | None = Field(
		default=None,
		description="connected gamepad identifiers",
	)
	connection_type: str | None = Field(
		default=None,
		alias="connectionType",
		description="network connection type",
	)
	connection_effective_type: str | None = Field(
		default=None,
		alias="connectionEffectiveType",
		description="effective network type hint (e.g. 4g, 3g)",
	)
	connection_downlink_mbps: float | None = Field(
		default=None,
		alias="connectionDownlinkMbps",
		description="estimated downlink speed in Mbps",
	)
	connection_rtt_ms: float | None = Field(
		default=None,
		alias="connectionRttMs",
		description="estimated round-trip time in milliseconds",
	)
	connection_save_data: bool | None = Field(
		default=None,
		alias="connectionSaveData",
		description="whether data saver mode is enabled",
	)
	battery_supported: bool | None = Field(
		default=None,
		alias="batterySupported",
		description="whether battery status API is supported",
	)
	battery_charging: bool | None = Field(
		default=None,
		alias="batteryCharging",
		description="whether the device is currently charging",
	)
	battery_level: int | None = Field(
		default=None,
		alias="batteryLevel",
		description="battery percentage from 0 to 100",
	)
	battery_charging_time_seconds: float | None = Field(
		default=None,
		alias="batteryChargingTimeSeconds",
		description="seconds until full charge when available",
	)
	battery_discharging_time_seconds: float | None = Field(
		default=None,
		alias="batteryDischargingTimeSeconds",
		description="seconds until empty when available",
	)
	latitude: float | None = Field(
		default=None,
		description="device latitude from browser geolocation API",
	)
	longitude: float | None = Field(
		default=None,
		description="device longitude from browser geolocation API",
	)
	location_label: str | None = Field(
		default=None,
		alias="locationLabel",
		description="human-readable location label (e.g. 'San Francisco, CA')",
	)


class RunInput(BaseModel):
	"""structured input for an agent run.

	supports plain text, resource attachments, or both.
	"""

	text: str | None = Field(
		default=None,
		description="user message text content",
	)
	attachments: list[ResourceAttachment] = Field(
		default_factory=list,
		description="resource references to attach to the message.",
	)


# allowed tool_choice values - only specific tools can be forced by the client
ToolChoice = Literal["agentic_web_search", "think", "generate_image"]


# base run fields shared across request types


class _RunBase(BaseModel):
	"""fields common to every run request."""

	agent_id: TypeID
	input: RunInput | None = Field(
		default=None,
		description="structured user input with text and/or attachment IDs. "
		"omit for regeneration/retry on an existing thread.",
	)
	tool_choice: ToolChoice | None = Field(
		default=None,
		description="optional tool choice override for this run. "
		"only specific tools can be forced.",
	)
	extra_plugins: list[str] = Field(
		default_factory=list,
		description="extra tool plugin ids to include for this run only.",
	)
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
	"""POST /runs - run on an existing thread, or ephemeral (no thread).

	when ``thread_id`` is present the run continues that thread.
	when omitted the run is **ephemeral** - no thread is created or persisted.

	``input`` is required for ephemeral runs and optional when continuing
	an existing thread (omit for regeneration / retry).

	``persist`` controls whether messages and metadata are saved to the
	database. defaults to True; set to False for ephemeral inference.
	"""

	thread_id: TypeID | None = None
	parent_id: TypeID | None = None
	persist: bool = True


class ThreadCreateAndRunRequest(_RunBase):
	"""POST /threads/create_and_run - create a thread then run immediately.

	``input`` is required (a new thread needs at least one user message).
	the SSE stream emits a ``thread_created`` event before normal run events.

	``thread_id`` is an optional client-generated TypeID. if provided, the
	backend will attempt to use it. on conflict, a server-generated ID is
	used instead - the client must read the ``thread_created`` event to
	get the canonical ID.
	"""

	thread_id: TypeID | None = None
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

	run_id: TypeID
	thread_id: TypeID | None = None
	agent_id: TypeID
	user_id: TypeID
	state: Literal["running", "completed", "error"]
	started_at: datetime
	updated_at: datetime


class SteerRunRequest(BaseModel):
	"""inject a user message into a running agent loop.

	the message is persisted immediately and queued for delivery at the
	next iteration boundary of the SDK loop.
	"""

	input: RunInput
	parent_id: TypeID | None = Field(
		default=None,
		description="parent message id for the persisted user message. "
		"defaults to the current branch tip if omitted.",
	)
	client_steering_id: str | None = Field(
		default=None,
		min_length=1,
		max_length=128,
		description="client-generated id used to reconcile optimistic queued messages.",
	)


class SteerRunResponse(BaseModel):
	"""response from a successful steering enqueue."""

	message_id: TypeID
	state: Literal["queued", "dropped"] = Field(
		description="'queued' if the run accepted the message, 'dropped' if "
		"the run terminated before the message could be enqueued.",
	)
