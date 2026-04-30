"""Event type constants for the system.

these define all the standard event types that can be emitted and consumed
throughout the platform. event types follow a hierarchical naming convention:
<domain>.<action> (e.g., thread.created, notification.custom)
"""

from __future__ import annotations

from enum import StrEnum


class EventType(StrEnum):
	"""Standard event types for the platform."""

	# stream control events (internal)
	STREAM_CONNECTED = "stream.connected"
	STREAM_PONG = "stream.pong"

	# thread events
	THREAD_CREATED = "thread.created"
	THREAD_UPDATED = "thread.updated"
	THREAD_DELETED = "thread.deleted"
	THREAD_READ = "thread.read"

	# message events
	MESSAGE_CREATED = "message.created"
	MESSAGE_UPDATED = "message.updated"
	MESSAGE_DELETED = "message.deleted"

	# typing indicators
	TYPING_USER_START = "typing.user.start"
	TYPING_USER_STOP = "typing.user.stop"

	# agent run lifecycle
	RUN_STARTED = "run.started"
	RUN_COMPLETED = "run.completed"
	RUN_ERROR = "run.error"

	# in-flight steering: a user injects an extra message into a run
	RUN_STEERING_QUEUED = "run.steering.queued"
	RUN_STEERING_INJECTED = "run.steering.injected"
	RUN_STEERING_DROPPED = "run.steering.dropped"

	# notification events
	NOTIFICATION_CUSTOM = "notification.custom"
	NOTIFICATION_AGENT = "notification.agent"

	# reminder events
	REMINDER_CREATED = "reminder.created"
	REMINDER_UPDATED = "reminder.updated"
	REMINDER_COMPLETED = "reminder.completed"
	REMINDER_DELETED = "reminder.deleted"
	REMINDER_LIST_CREATED = "reminder_list.created"
	REMINDER_LIST_UPDATED = "reminder_list.updated"
	REMINDER_LIST_DELETED = "reminder_list.deleted"

	# task events
	TASK_CREATED = "task.created"
	TASK_UPDATED = "task.updated"
	TASK_COMPLETED = "task.completed"
	TASK_FAILED = "task.failed"
	TASK_CANCELLED = "task.cancelled"

	# project events
	PROJECT_CREATED = "project.created"
	PROJECT_UPDATED = "project.updated"
	PROJECT_DELETED = "project.deleted"

	# file events
	FILE_CREATED = "file.created"
	FILE_UPDATED = "file.updated"
	FILE_DELETED = "file.deleted"
	FILE_PROCESSING = "file.processing"
	FILE_READY = "file.ready"

	# agent events
	AGENT_CREATED = "agent.created"
	AGENT_UPDATED = "agent.updated"
	AGENT_DELETED = "agent.deleted"

	# memory events
	MEMORY_CREATED = "memory.created"
	MEMORY_UPDATED = "memory.updated"
	MEMORY_DELETED = "memory.deleted"

	# note events
	NOTE_CREATED = "note.created"
	NOTE_UPDATED = "note.updated"
	NOTE_DELETED = "note.deleted"

	# group events ---
	GROUP_CREATED = "group.created"
	GROUP_UPDATED = "group.updated"
	GROUP_DELETED = "group.deleted"
	GROUP_MEMBER_ADDED = "group.member_added"
	GROUP_MEMBER_REMOVED = "group.member_removed"

	# friendship events
	FRIEND_REQUEST_SENT = "friend.request_sent"
	FRIEND_REQUEST_ACCEPTED = "friend.request_accepted"
	FRIEND_REQUEST_DECLINED = "friend.request_declined"
	FRIEND_REMOVED = "friend.removed"

	# settings events
	SETTINGS_UPDATED = "settings.updated"

	# user events
	USER_PREFERENCES_UPDATED = "user.preferences_updated"

	# role events
	ROLE_UPDATED = "role.updated"
	ROLE_DELETED = "role.deleted"

	# attachment lifecycle events
	ATTACHMENT_DECAYED = "attachment.decayed"
	ATTACHMENT_REVEALED = "attachment.revealed"

	# citation events
	CITATION_SOURCES = "citation.sources"

	# tool events (scoped to tool_call_id)
	TOOL_PROGRESS = "tool.progress"
	TOOL_CUSTOM = "tool.custom"  # generic tool event. can include custom UI components
	TOOL_NOTIFICATION = "tool.notification"


# event type groupings for easier filtering
THREAD_EVENTS = {
	EventType.THREAD_CREATED,
	EventType.THREAD_UPDATED,
	EventType.THREAD_DELETED,
	EventType.THREAD_READ,
}

MESSAGE_EVENTS = {
	EventType.MESSAGE_CREATED,
	EventType.MESSAGE_UPDATED,
	EventType.MESSAGE_DELETED,
}

TYPING_EVENTS = {
	EventType.TYPING_USER_START,
	EventType.TYPING_USER_STOP,
}

RUN_EVENTS = {
	EventType.RUN_STARTED,
	EventType.RUN_COMPLETED,
	EventType.RUN_ERROR,
	EventType.RUN_STEERING_QUEUED,
	EventType.RUN_STEERING_INJECTED,
	EventType.RUN_STEERING_DROPPED,
}

SETTINGS_EVENTS = {
	EventType.SETTINGS_UPDATED,
}

USER_EVENTS = {
	EventType.USER_PREFERENCES_UPDATED,
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

PROJECT_EVENTS = {
	EventType.PROJECT_CREATED,
	EventType.PROJECT_UPDATED,
	EventType.PROJECT_DELETED,
}

AGENT_EVENTS = {
	EventType.AGENT_CREATED,
	EventType.AGENT_UPDATED,
	EventType.AGENT_DELETED,
}

FILE_EVENTS = {
	EventType.FILE_CREATED,
	EventType.FILE_UPDATED,
	EventType.FILE_DELETED,
	EventType.FILE_PROCESSING,
	EventType.FILE_READY,
}

MEMORY_EVENTS = {
	EventType.MEMORY_CREATED,
	EventType.MEMORY_UPDATED,
	EventType.MEMORY_DELETED,
}

NOTE_EVENTS = {
	EventType.NOTE_CREATED,
	EventType.NOTE_UPDATED,
	EventType.NOTE_DELETED,
}

GROUP_EVENTS = {
	EventType.GROUP_CREATED,
	EventType.GROUP_UPDATED,
	EventType.GROUP_DELETED,
	EventType.GROUP_MEMBER_ADDED,
	EventType.GROUP_MEMBER_REMOVED,
}

FRIEND_EVENTS = {
	EventType.FRIEND_REQUEST_SENT,
	EventType.FRIEND_REQUEST_ACCEPTED,
	EventType.FRIEND_REQUEST_DECLINED,
	EventType.FRIEND_REMOVED,
}

REMINDER_EVENTS = {
	EventType.REMINDER_CREATED,
	EventType.REMINDER_UPDATED,
	EventType.REMINDER_COMPLETED,
	EventType.REMINDER_DELETED,
	EventType.REMINDER_LIST_CREATED,
	EventType.REMINDER_LIST_UPDATED,
	EventType.REMINDER_LIST_DELETED,
}

TASK_EVENTS = {
	EventType.TASK_CREATED,
	EventType.TASK_UPDATED,
	EventType.TASK_COMPLETED,
	EventType.TASK_FAILED,
	EventType.TASK_CANCELLED,
}

ATTACHMENT_EVENTS = {
	EventType.ATTACHMENT_DECAYED,
	EventType.ATTACHMENT_REVEALED,
}

CITATION_EVENTS = {
	EventType.CITATION_SOURCES,
}
