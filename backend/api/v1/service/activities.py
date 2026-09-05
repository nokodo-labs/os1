"""helpers for user-visible activity events."""

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Literal

from api.models.event import Event, EventScope
from api.models.event_types import EventType
from nokodo_ai.utils.typeid import TypeID, new_typeid


ActivityOutcome = Literal["success", "error", "cancelled"]
EmitEvent = Callable[[Event], Awaitable[None]]

_RESERVED_DATA_KEYS = frozenset({"run_id", "activity_id", "activity_type", "outcome"})


def _merge_activity_data(
	base: dict[str, object],
	extra: Mapping[str, object] | None,
) -> dict[str, object]:
	if extra is None:
		return base
	for key, value in extra.items():
		if key in _RESERVED_DATA_KEYS:
			raise ValueError(f"activity data cannot override reserved key: {key}")
		base[key] = value
	return base


@dataclass(slots=True)
class ActivityEmitter:
	"""emit lifecycle events for one activity instance."""

	emit: EmitEvent
	user_id: str | None
	thread_id: TypeID
	message_id: TypeID
	run_id: TypeID
	activity_id: TypeID
	activity_type: str

	def _base_data(self) -> dict[str, object]:
		return {
			"run_id": str(self.run_id),
			"activity_id": str(self.activity_id),
			"activity_type": self.activity_type,
		}

	async def _emit(self, event_type: EventType, data: dict[str, object]) -> None:
		await self.emit(
			Event(
				scope=EventScope.THREAD,
				scope_id=str(self.thread_id),
				type=event_type,
				thread_id=str(self.thread_id),
				message_id=str(self.message_id),
				user_id=self.user_id,
				data=data,
			)
		)

	async def started(
		self,
		title: str | None = None,
		message: str | None = None,
		data: Mapping[str, object] | None = None,
	) -> None:
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
		if progress is not None and not 0 <= progress <= 100:
			raise ValueError("activity progress must be between 0 and 100")
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
		outcome: ActivityOutcome,
		message: str | None = None,
		error: str | None = None,
		data: Mapping[str, object] | None = None,
	) -> None:
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


async def start_activity(
	emit: EmitEvent,
	user_id: str | None,
	thread_id: TypeID | str | None,
	run_id: TypeID | str | None,
	activity_type: str,
	message_id: TypeID | str | None,
	title: str | None = None,
	message: str | None = None,
	data: Mapping[str, object] | None = None,
) -> ActivityEmitter | None:
	"""start an activity when all persisted identity coordinates exist."""
	if thread_id is None or run_id is None or message_id is None:
		return None
	activity_type = activity_type.strip()
	if not activity_type:
		raise ValueError("activity type is required")
	activity = ActivityEmitter(
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
