from __future__ import annotations

import asyncio

import pytest

from api.v1.service import event_bus
from api.v1.service import events as event_service
from nokodo_ai.utils.typeid import TypeID


@pytest.mark.asyncio
async def test_event_bus_publish_includes_routing(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""event fanout publishes routing metadata with a process-specific id."""
	published: list[dict[str, object]] = []

	class _Channel:
		async def publish(self, payload: dict[str, object]) -> int:
			published.append(payload)
			return 1

	monkeypatch.setattr(event_bus, "_CHANNEL", _Channel())

	await event_bus.publish_event(
		{"type": "thread.updated", "data": {"id": "thread_1"}},
		recipient_ids=[TypeID("user_1"), TypeID("user_2")],
	)

	assert published == [
		{
			"publisher_id": event_bus._publisher_id(),
			"event": {"type": "thread.updated", "data": {"id": "thread_1"}},
			"broadcast": False,
			"recipient_ids": ["user_1", "user_2"],
		}
	]


@pytest.mark.asyncio
async def test_event_fanout_skips_empty_resource_recipients(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""resource-routed events with no recipients are not mirrored or broadcast."""
	published: list[dict[str, object]] = []

	class _Channel:
		async def publish(self, payload: dict[str, object]) -> int:
			published.append(payload)
			return 1

	monkeypatch.setattr(event_bus, "_CHANNEL", _Channel())

	await event_service._fanout_event_data(
		{"type": "thread.updated"},
		recipient_ids=[],
		user_id=None,
		broadcast=False,
	)

	assert published == []


@pytest.mark.asyncio
async def test_event_bus_subscriber_rebroadcasts_remote_event(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""remote fanout events are rebroadcast to their resolved users."""
	sent: list[tuple[list[str], dict[str, object]]] = []

	class _Channel:
		async def subscribe(self):
			yield {
				"publisher_id": "remote-process",
				"event": {"type": "thread.updated"},
				"recipient_ids": ["user_1"],
				"broadcast": False,
			}
			await asyncio.sleep(10)

	class _Manager:
		async def send_to_users(
			self,
			user_ids: list[TypeID],
			data: dict[str, object],
			exclude_user_id: TypeID | None = None,
		) -> None:
			_ = exclude_user_id
			sent.append(([str(user_id) for user_id in user_ids], data))

		async def send_to_user(self, user_id: TypeID, data: dict[str, object]) -> None:
			sent.append(([str(user_id)], data))

		async def broadcast(self, data: dict[str, object]) -> None:
			sent.append(([], data))

	monkeypatch.setattr(event_bus, "_CHANNEL", _Channel())
	monkeypatch.setattr(event_service, "event_connections", _Manager())

	task = await event_service.start_event_subscriber()
	try:
		for _ in range(20):
			if sent:
				break
			await asyncio.sleep(0.01)
	finally:
		task.cancel()

	assert sent == [(["user_1"], {"type": "thread.updated"})]


@pytest.mark.asyncio
async def test_event_bus_subscriber_skips_local_event(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""events published by this process are not delivered back to itself."""
	sent: list[dict[str, object]] = []

	class _Channel:
		async def subscribe(self):
			yield {
				"publisher_id": event_bus._publisher_id(),
				"event": {"type": "thread.updated"},
				"user_id": "user_1",
				"broadcast": False,
			}
			await asyncio.sleep(10)

	class _Manager:
		async def send_to_users(
			self,
			user_ids: list[TypeID],
			data: dict[str, object],
			exclude_user_id: TypeID | None = None,
		) -> None:
			_ = (user_ids, exclude_user_id)
			sent.append(data)

		async def send_to_user(self, user_id: TypeID, data: dict[str, object]) -> None:
			_ = user_id
			sent.append(data)

		async def broadcast(self, data: dict[str, object]) -> None:
			sent.append(data)

	monkeypatch.setattr(event_bus, "_CHANNEL", _Channel())
	monkeypatch.setattr(event_service, "event_connections", _Manager())

	task = await event_service.start_event_subscriber()
	try:
		await asyncio.sleep(0.05)
	finally:
		task.cancel()

	assert sent == []


@pytest.mark.asyncio
async def test_event_bus_subscriber_rebroadcasts_remote_broadcast(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""remote broadcast envelopes are delivered through the raw broadcast path."""
	sent: list[dict[str, object]] = []

	class _Channel:
		async def subscribe(self):
			yield {
				"publisher_id": "remote-process",
				"event": {"type": "thread.updated"},
				"broadcast": True,
			}
			await asyncio.sleep(10)

	class _Manager:
		async def send_to_users(
			self,
			user_ids: list[TypeID],
			data: dict[str, object],
			exclude_user_id: TypeID | None = None,
		) -> None:
			_ = (user_ids, exclude_user_id)
			sent.append(data)

		async def send_to_user(self, user_id: TypeID, data: dict[str, object]) -> None:
			_ = user_id
			sent.append(data)

		async def broadcast(self, data: dict[str, object]) -> None:
			sent.append(data)

	monkeypatch.setattr(event_bus, "_CHANNEL", _Channel())
	monkeypatch.setattr(event_service, "event_connections", _Manager())

	task = await event_service.start_event_subscriber()
	try:
		await asyncio.sleep(0.05)
	finally:
		task.cancel()

	assert sent == [{"type": "thread.updated"}]
