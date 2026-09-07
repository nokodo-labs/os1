"""the API refuses to boot against a valkey that could evict version counters.

the accessible-user cache is an authorization gate whose entries are addressed
by a monotonic per-resource counter held in this instance with NO TTL. an
evicted counter restarts at 0, which makes an entry invalidated at version N
addressable again once N more bumps land inside its 24h TTL - a revoked
principal served from cache, with nothing to notice it.

we own the instance, so the requirement is ENFORCED rather than documented:
the boot check reads the live config and refuses anything that could evict
these keys.
"""

from __future__ import annotations

from typing import Any

import pytest

from api.redis import client as redis_client_module
from api.redis.client import (
	_ALLOWED_MAXMEMORY_POLICIES,
	require_safe_eviction_policy,
)


class _FakeRedis:
	"""answers `config_get` with a fixed policy, or raises."""

	def __init__(self, policy: str | bytes | None, error: Exception | None = None):
		self._policy = policy
		self._error = error

	async def config_get(self, parameter: str) -> dict[str, Any]:
		if self._error is not None:
			raise self._error
		assert parameter == "maxmemory-policy"
		return {} if self._policy is None else {parameter: self._policy}


def _serve(monkeypatch: pytest.MonkeyPatch, conn: _FakeRedis) -> None:
	monkeypatch.setattr(redis_client_module.redis_client, "get", lambda: conn)


@pytest.mark.asyncio
@pytest.mark.parametrize("policy", sorted(_ALLOWED_MAXMEMORY_POLICIES))
async def test_a_non_evicting_policy_boots(
	policy: str,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""`noeviction` and every `volatile-*` policy pass.

	the `volatile-*` family is admitted because it only ever considers keys
	that carry a TTL, and these counters never do - so they are not eviction
	candidates under it.
	"""
	_serve(monkeypatch, _FakeRedis(policy))
	await require_safe_eviction_policy()


@pytest.mark.asyncio
@pytest.mark.parametrize(
	"policy",
	["allkeys-lru", "allkeys-lfu", "allkeys-random"],
)
async def test_an_evicting_policy_refuses_to_boot(
	policy: str,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""every `allkeys-*` policy can evict a TTL-less counter, so it is refused.

	the message names the requirement: an operator reading it must be able to
	fix the instance without reading this code.
	"""
	_serve(monkeypatch, _FakeRedis(policy))

	with pytest.raises(RuntimeError) as refusal:
		await require_safe_eviction_policy()

	message = str(refusal.value)
	assert policy in message
	for allowed in _ALLOWED_MAXMEMORY_POLICIES:
		assert allowed in message


@pytest.mark.asyncio
async def test_an_unreadable_config_refuses_to_boot(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""an unverified policy is not a safe one.

	treating a failed read as "probably fine" would make the whole check
	decorative on exactly the instance least likely to be healthy.
	"""
	_serve(monkeypatch, _FakeRedis(None, error=OSError("connection reset")))

	with pytest.raises(RuntimeError) as refusal:
		await require_safe_eviction_policy()

	assert "could not read" in str(refusal.value)
	assert isinstance(refusal.value.__cause__, OSError)


@pytest.mark.asyncio
async def test_a_missing_or_bytes_policy_is_handled(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""redis-py may answer in bytes, and a key may be absent entirely.

	bytes must be decoded rather than stringified - `str(b"noeviction")` is
	`"b'noeviction'"`, which would refuse a correctly configured instance. an
	absent key is refused, since nothing was verified.
	"""
	_serve(monkeypatch, _FakeRedis(b"noeviction"))
	await require_safe_eviction_policy()

	_serve(monkeypatch, _FakeRedis(b"allkeys-lru"))
	with pytest.raises(RuntimeError):
		await require_safe_eviction_policy()

	_serve(monkeypatch, _FakeRedis(None))
	with pytest.raises(RuntimeError):
		await require_safe_eviction_policy()


@pytest.mark.asyncio
async def test_the_policy_comparison_ignores_case(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""a config value's case is not a reason to take the stack down."""
	_serve(monkeypatch, _FakeRedis("NoEviction"))
	await require_safe_eviction_policy()
