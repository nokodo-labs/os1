"""resource payload cache coverage."""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from api.permissions import ResourceType
from api.v1.service import resource_payload_cache
from nokodo_ai.utils.typeid import new_typeid


class Payload(BaseModel):
	name: str


class FakeCache:
	def __init__(self) -> None:
		self.values: dict[str, object] = {}
		self.tags: dict[str, list[str]] = {}
		self.invalidated: list[str] = []
		self.deleted: list[str] = []

	async def get(self, key: str) -> object | None:
		return self.values.get(key)

	async def set(
		self,
		key: str,
		value: object,
		ttl: int = 60,
		tags: list[str] | None = None,
	) -> None:
		self.values[key] = value
		self.tags[key] = tags or []

	async def delete(self, key: str) -> None:
		self.deleted.append(key)
		self.values.pop(key, None)

	async def invalidate_tag(self, tag: str) -> None:
		self.invalidated.append(tag)


async def test_resource_payload_cache_round_trips_by_resource_tag(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	fake_cache = FakeCache()
	monkeypatch.setattr(resource_payload_cache, "cache", fake_cache)
	resource_id = new_typeid("agent")
	payload = Payload(name="cached agent")

	await resource_payload_cache.set_cached_resource_payload(
		ResourceType.AGENT,
		resource_id,
		payload,
	)
	cached = await resource_payload_cache.get_cached_resource_payload(
		ResourceType.AGENT,
		resource_id,
		Payload,
	)
	await resource_payload_cache.invalidate_resource_payload_cache(
		ResourceType.AGENT,
		resource_id,
	)

	key = next(iter(fake_cache.values))
	tag = f"resource-payload:agent:{resource_id}"
	assert cached == payload
	assert key.startswith(f"resource-payload:agent:{resource_id}:")
	assert fake_cache.values[key] == {"name": "cached agent"}
	assert fake_cache.tags[key] == [tag]
	assert fake_cache.invalidated == [tag]


async def test_resource_payload_cache_deletes_invalid_payload(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	fake_cache = FakeCache()
	monkeypatch.setattr(resource_payload_cache, "cache", fake_cache)
	resource_id = new_typeid("agent")
	await resource_payload_cache.set_cached_resource_payload(
		ResourceType.AGENT,
		resource_id,
		Payload(name="valid"),
	)
	key = next(iter(fake_cache.values))
	fake_cache.values[key] = {"unexpected": "value"}

	assert (
		await resource_payload_cache.get_cached_resource_payload(
			ResourceType.AGENT,
			resource_id,
			Payload,
		)
		is None
	)
	assert fake_cache.deleted == [key]


async def test_resource_payload_get_or_set_uses_cached_payload(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	fake_cache = FakeCache()
	monkeypatch.setattr(resource_payload_cache, "cache", fake_cache)
	resource_id = new_typeid("agent")
	await resource_payload_cache.set_cached_resource_payload(
		ResourceType.AGENT,
		resource_id,
		Payload(name="cached"),
	)
	called = False

	async def factory() -> Payload:
		nonlocal called
		called = True
		return Payload(name="fresh")

	payload = await resource_payload_cache.get_or_set_resource_payload_cache(
		ResourceType.AGENT,
		resource_id,
		Payload,
		factory,
	)

	assert payload == Payload(name="cached")
	assert called is False
