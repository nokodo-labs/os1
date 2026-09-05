"""tests for distributed run-slot coordination against an unreachable bus."""

from functools import partial
from unittest.mock import MagicMock

import pytest
from fastapi import status
from redis.exceptions import RedisError

from api.v1.service.runs import bus
from nokodo_ai.utils.typeid import TypeID, new_typeid


@pytest.fixture
def unreachable_bus(monkeypatch: pytest.MonkeyPatch) -> None:
	"""every bus call in this module raises as if redis were down."""
	monkeypatch.setattr(bus.redis_client, "get", MagicMock(side_effect=RedisError()))


@pytest.mark.asyncio
@pytest.mark.parametrize(
	"operation",
	[
		"claim_run_slot",
		"wait_run_slot",
		"promote_run_slot",
		"abandon_run_slot",
		"release_run_slot",
		"refresh_run_slot",
		"register_run_route",
		"read_run_route",
		"cleanup_run_log",
	],
)
async def test_every_bus_operation_fails_loudly(
	unreachable_bus: None,
	operation: str,
) -> None:
	"""the bus is a hard dependency, so no call may quietly carry on locally."""
	_ = unreachable_bus
	run_id = TypeID(new_typeid("run"))
	calls = {
		"claim_run_slot": partial(
			bus.claim_run_slot,
			TypeID(new_typeid("thread")),
			None,
			TypeID(new_typeid("agent")),
		),
		"wait_run_slot": partial(bus.wait_run_slot, "slot"),
		"promote_run_slot": partial(bus.promote_run_slot, "slot", "token", run_id),
		"abandon_run_slot": partial(bus.abandon_run_slot, "slot", "token"),
		"release_run_slot": partial(bus.release_run_slot, run_id),
		"refresh_run_slot": partial(bus.refresh_run_slot, run_id),
		"register_run_route": partial(
			bus.register_run_route,
			run_id,
			bus.RunRoute(
				thread_id=TypeID(new_typeid("thread")),
				container_root_id=None,
				agent_id=TypeID(new_typeid("agent")),
				user_id=TypeID(new_typeid("user")),
				persist=True,
			),
		),
		"read_run_route": partial(bus.read_run_route, run_id),
		"cleanup_run_log": partial(bus.cleanup_run_log, run_id),
	}

	with pytest.raises(bus.RunBusUnavailableError) as excinfo:
		await calls[operation]()

	assert excinfo.value.operation == operation
	assert excinfo.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE


@pytest.mark.asyncio
async def test_no_client_facing_message_names_a_backend() -> None:
	"""the client learns "temporary, retry", never which mechanism broke."""
	from api.v1.service.runs.launch import _STEERING_UNAVAILABLE_DETAIL

	mechanisms = ("redis", "valkey", "cache", "bus", "backend")
	details = [
		str(bus.RunBusUnavailableError("claim_run_slot").detail),
		_STEERING_UNAVAILABLE_DETAIL,
	]

	for detail in details:
		assert not [word for word in mechanisms if word in detail.lower()], detail
		assert "try again" in detail.lower()


@pytest.mark.asyncio
async def test_slot_contention_is_not_reported_as_an_outage(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""the bus answered every round; another worker simply kept winning."""

	class _ChurningRedis:
		"""never grants the SET, and always reports the key already gone."""

		async def set(self, *_args: object, **_kwargs: object) -> None:
			return None

		async def get(self, *_args: object) -> None:
			return None

	monkeypatch.setattr(
		bus.redis_client, "get", MagicMock(return_value=_ChurningRedis())
	)

	with pytest.raises(bus.RunSlotContendedError) as excinfo:
		await bus.claim_run_slot(
			TypeID(new_typeid("thread")),
			None,
			TypeID(new_typeid("agent")),
		)

	assert excinfo.value.status_code == status.HTTP_409_CONFLICT
	assert not isinstance(excinfo.value, bus.RunBusUnavailableError)


@pytest.mark.asyncio
async def test_teardown_tolerates_an_unreachable_bus(unreachable_bus: None) -> None:
	"""a run that already ended cannot be un-ended by a failing release."""
	_ = unreachable_bus

	await bus.best_effort_teardown(
		partial(bus.release_run_slot, TypeID(new_typeid("run")))
	)


@pytest.mark.asyncio
async def test_teardown_does_not_swallow_other_failures(
	unreachable_bus: None,
) -> None:
	"""only the bus error is tolerated; a real bug still surfaces."""
	_ = unreachable_bus

	async def broken() -> None:
		raise ValueError("not a bus failure")

	with pytest.raises(ValueError, match="not a bus failure"):
		await bus.best_effort_teardown(broken)
