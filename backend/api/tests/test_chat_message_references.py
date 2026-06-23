"""tests for chat message reference promises."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable

import pytest

from api.v1.service.chat import message_references


class _FakeRedisPipeline:
	def __init__(self, redis: _FakeRedis) -> None:
		self.redis = redis
		self.operations: list[tuple[str, str, bytes | int]] = []

	def lpush(self, key: str, value: bytes) -> None:
		self.operations.append(("lpush", key, value))

	def expire(self, key: str, seconds: int) -> None:
		self.operations.append(("expire", key, seconds))

	async def execute(self) -> None:
		async with self.redis.condition:
			for operation, key, value in self.operations:
				if operation == "lpush" and isinstance(value, bytes):
					self.redis.lists.setdefault(key, []).insert(0, value)
			self.redis.condition.notify_all()


class _FakeRedis:
	def __init__(self) -> None:
		self.values: dict[str, bytes] = {}
		self.lists: dict[str, list[bytes]] = {}
		self.condition = asyncio.Condition()

	async def get(self, key: str) -> bytes | None:
		return self.values.get(key)

	async def set(
		self,
		key: str,
		value: bytes,
		ex: int | None = None,
		nx: bool = False,
	) -> bool:
		_ = ex
		async with self.condition:
			if nx and key in self.values:
				return False
			self.values[key] = value
			self.condition.notify_all()
			return True

	def pipeline(self, transaction: bool = False) -> _FakeRedisPipeline:
		_ = transaction
		return _FakeRedisPipeline(self)

	async def blpop(
		self,
		keys: Iterable[str],
		timeout: int = 0,
	) -> tuple[str, bytes] | None:
		loop = asyncio.get_running_loop()
		deadline = loop.time() + timeout
		async with self.condition:
			while True:
				for key in keys:
					items = self.lists.get(key)
					if items:
						return key, items.pop(0)
				remaining = deadline - loop.time()
				if remaining <= 0:
					return None
				try:
					await asyncio.wait_for(self.condition.wait(), timeout=remaining)
				except TimeoutError:
					return None


@pytest.mark.asyncio
async def test_message_reference_waits_until_resolved(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""a waiter receives the persisted message id once the reference resolves."""
	fake_redis = _FakeRedis()
	monkeypatch.setattr(message_references.redis_client, "get", lambda: fake_redis)

	message_ref = message_references.new_message_reference()
	waiter = asyncio.create_task(
		message_references.wait_message_reference(message_ref, timeout_seconds=1)
	)
	await asyncio.sleep(0)
	assert not waiter.done()

	assert await message_references.resolve_message_reference(
		message_ref,
		"msg_final_123",
	)
	assert await waiter == "msg_final_123"
	assert (
		await message_references.wait_message_reference(message_ref, timeout_seconds=1)
		== "msg_final_123"
	)
