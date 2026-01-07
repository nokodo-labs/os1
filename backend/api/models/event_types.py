"""Event type constants for the system.

these define all the standard event types that can be emitted and consumed
throughout the platform. event types follow a hierarchical naming convention:
<domain>.<action> (e.g., thread.created, notification.custom)
"""

from __future__ import annotations

from enum import StrEnum


class EventType(StrEnum):
	"""Standard event types for the platform."""

	# --- stream control events (internal) ---
	STREAM_CONNECTED = "stream.connected"
	STREAM_PONG = "stream.pong"

	# --- thread events ---
	THREAD_CREATED = "thread.created"
	THREAD_UPDATED = "thread.updated"
	THREAD_DELETED = "thread.deleted"

	# --- message events ---
	MESSAGE_CREATED = "message.created"
	MESSAGE_UPDATED = "message.updated"
	MESSAGE_DELETED = "message.deleted"

	# --- typing indicators ---
	TYPING_USER_START = "typing.user.start"
	TYPING_USER_STOP = "typing.user.stop"
	TYPING_AGENT_START = "typing.agent.start"
	TYPING_AGENT_STOP = "typing.agent.stop"

	# --- notification events ---
	NOTIFICATION_CUSTOM = "notification.custom"
	NOTIFICATION_AGENT = "notification.agent"

	# --- task events ---
	TASK_CREATED = "task.created"
	TASK_UPDATED = "task.updated"
	TASK_COMPLETED = "task.completed"
	TASK_FAILED = "task.failed"

	# --- project events ---
	PROJECT_CREATED = "project.created"
	PROJECT_UPDATED = "project.updated"
	PROJECT_DELETED = "project.deleted"

	# --- file events ---
	FILE_UPLOADED = "file.uploaded"
	FILE_DELETED = "file.deleted"
	FILE_PROCESSING = "file.processing"
	FILE_READY = "file.ready"

	# --- agent events ---
	AGENT_CREATED = "agent.created"
	AGENT_UPDATED = "agent.updated"
	AGENT_DELETED = "agent.deleted"

	# --- memory events ---
	MEMORY_CREATED = "memory.created"
	MEMORY_UPDATED = "memory.updated"
	MEMORY_DELETED = "memory.deleted"

	# --- tool events (scoped to tool_call_id) ---
	TOOL_PROGRESS = "tool.progress"
	TOOL_CUSTOM = "tool.custom"  # generic tool event. can include custom UI components
	TOOL_NOTIFICATION = "tool.notification"


# event type groupings for easier filtering
THREAD_EVENTS = {
	EventType.THREAD_CREATED,
	EventType.THREAD_UPDATED,
	EventType.THREAD_DELETED,
}

MESSAGE_EVENTS = {
	EventType.MESSAGE_CREATED,
	EventType.MESSAGE_UPDATED,
	EventType.MESSAGE_DELETED,
}

TYPING_EVENTS = {
	EventType.TYPING_USER_START,
	EventType.TYPING_USER_STOP,
	EventType.TYPING_AGENT_START,
	EventType.TYPING_AGENT_STOP,
}

NOTIFICATION_EVENTS = {
	EventType.NOTIFICATION_CUSTOM,
	EventType.NOTIFICATION_AGENT,
}

TOOL_EVENTS = {
	EventType.TOOL_PROGRESS,
	EventType.TOOL_CUSTOM,
	EventType.TOOL_NOTIFICATION,
}
