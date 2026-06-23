"""helpers for user-visible run activity events."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from api.models.event import Event, EventScope
from api.models.event_types import EventType
from nokodo_ai.utils.typeid import TypeID, new_typeid


if TYPE_CHECKING:
	from api.v1.service.chat.context import AppContext

RunActivityOutcome = Literal["success", "error", "cancelled"]

EmitEvent = Callable[[Event], Awaitable[None]]

_RESERVED_DATA_KEYS = frozenset(
	{
		"run_id",
		"activity_id",
		"activity_type",
		"outcome",
	}
)


def _string_or_none(value: object) -> str | None:
	"""return value as a string when it exists."""
	return str(value) if value is not None else None


def _merge_activity_data(
	base: dict[str, object],
	extra: Mapping[str, object] | None,
) -> dict[str, object]:
	"""merge activity-specific public fields without overriding identity fields."""
	if extra is None:
		return base
	for key, value in extra.items():
		if key in _RESERVED_DATA_KEYS:
			raise ValueError(f"run activity data cannot override reserved key: {key}")
		base[key] = value
	return base


@dataclass(slots=True)
class RunActivityEmitter:
	"""emit lifecycle events for one run activity instance."""

	emit: EmitEvent
	user_id: str | None
	thread_id: TypeID
	message_id: TypeID
	run_id: TypeID
	activity_id: TypeID
	activity_type: str

	def _base_data(self) -> dict[str, object]:
		"""return the common public identity envelope."""
		return {
			"run_id": str(self.run_id),
			"activity_id": str(self.activity_id),
			"activity_type": self.activity_type,
		}

	async def _emit(
		self,
		event_type: EventType,
		data: dict[str, object],
	) -> None:
		"""emit one run activity event through the event emitter."""
		event = Event(
			scope=EventScope.THREAD,
			scope_id=str(self.thread_id),
			type=event_type,
			thread_id=str(self.thread_id),
			message_id=str(self.message_id),
			user_id=self.user_id,
			data=data,
		)
		await self.emit(event)

	async def started(
		self,
		title: str | None = None,
		message: str | None = None,
		data: Mapping[str, object] | None = None,
	) -> None:
		"""emit the activity start event."""
		payload = self._base_data()
		if title:
			payload["title"] = title
		if message:
			payload["message"] = message
		await self._emit(
			EventType.RUN_ACTIVITY_STARTED,
			_merge_activity_data(payload, data),
		)

	async def progress(
		self,
		message: str | None = None,
		progress: int | None = None,
		data: Mapping[str, object] | None = None,
	) -> None:
		"""emit an activity progress event."""
		if progress is not None and not 0 <= progress <= 100:
			raise ValueError("run activity progress must be between 0 and 100")
		payload = self._base_data()
		if message:
			payload["message"] = message
		if progress is not None:
			payload["progress"] = progress
		await self._emit(
			EventType.RUN_ACTIVITY_PROGRESS,
			_merge_activity_data(payload, data),
		)

	async def ended(
		self,
		outcome: RunActivityOutcome,
		message: str | None = None,
		error: str | None = None,
		data: Mapping[str, object] | None = None,
	) -> None:
		"""emit the activity terminal event."""
		payload = self._base_data()
		payload["outcome"] = outcome
		if message:
			payload["message"] = message
		if error:
			payload["error"] = error
		await self._emit(
			EventType.RUN_ACTIVITY_ENDED,
			_merge_activity_data(payload, data),
		)


async def start_run_activity(
	app_context: AppContext,
	activity_type: str,
	message_id: TypeID | str | None,
	title: str | None = None,
	message: str | None = None,
	data: Mapping[str, object] | None = None,
) -> RunActivityEmitter | None:
	"""create and start a run activity when run and message context exist."""
	if (
		app_context.thread_id is None
		or app_context.run_id is None
		or message_id is None
	):
		return None
	activity_type = activity_type.strip()
	if not activity_type:
		raise ValueError("run activity type is required")
	activity = RunActivityEmitter(
		emit=app_context.event_emitter,
		user_id=_string_or_none(app_context.user_id),
		thread_id=app_context.thread_id,
		message_id=TypeID(str(message_id)),
		run_id=app_context.run_id,
		activity_id=TypeID(new_typeid("activity")),
		activity_type=activity_type,
	)
	await activity.started(title=title, message=message, data=data)
	return activity


async def start_detached_run_activity(
	emit: EmitEvent,
	user_id: str | None,
	thread_id: TypeID | str | None,
	run_id: TypeID | str | None,
	activity_type: str,
	message_id: TypeID | str | None,
	title: str | None = None,
	message: str | None = None,
	data: Mapping[str, object] | None = None,
) -> RunActivityEmitter | None:
	"""start a run activity outside an AppContext (e.g. a background task)."""
	if thread_id is None or run_id is None or message_id is None:
		return None
	activity_type = activity_type.strip()
	if not activity_type:
		raise ValueError("run activity type is required")
	activity = RunActivityEmitter(
		emit=emit,
		user_id=user_id,
		thread_id=TypeID(str(thread_id)),
		message_id=TypeID(str(message_id)),
		run_id=TypeID(str(run_id)),
		activity_id=TypeID(new_typeid("activity")),
		activity_type=activity_type,
	)
	await activity.started(title=title, message=message, data=data)
	return activity
