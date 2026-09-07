"""route steering commands to the worker that owns a run."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Final, Literal

from api.local_tasks import create_background_task
from api.redis import make_run_channel
from nokodo_ai.messages import Message as SDKMessage
from nokodo_ai.messages import MessageAdapter
from nokodo_ai.utils.typeid import TypeID, is_typeid


logger = logging.getLogger(__name__)

_STEERING_CHANNEL_SUFFIX: Final[str] = "steer"
"""per-run channel every command for that run is published on."""


@dataclass(frozen=True, slots=True)
class EnqueueSteeringCommand:
	"""one inbox item routed to the worker that owns a run."""

	message_id: TypeID
	"""the persisted row this injection finalizes."""
	messages: list[SDKMessage]
	"""what the agent reads when the run drains this."""
	retractable: bool
	"""whether an undelivered one leaves a row owing a resolution."""
	thread_id: TypeID
	"""conversation the message belongs to."""
	agent_id: TypeID
	"""agent being steered."""


@dataclass(frozen=True, slots=True)
class DropSteeringCommand:
	"""one queued-message drop routed to the run owner."""

	message_id: TypeID
	"""the queued row to retract before the agent reads it."""
	thread_id: TypeID
	"""conversation the message belongs to."""
	agent_id: TypeID
	"""agent whose run was holding it."""


@dataclass(frozen=True, slots=True)
class InvocationSteeringCommand:
	"""one persisted invocation routed to the run owner for catch-up."""

	message_id: TypeID
	"""the mention the run is being caught up to."""
	thread_id: TypeID
	"""conversation the mention belongs to."""
	agent_id: TypeID
	"""agent the mention addressed."""


@dataclass(frozen=True, slots=True)
class CancelRunCommand:
	"""one cancellation request routed to the worker that owns a run."""

	reason: str
	"""why it was cancelled, which becomes the run's terminal reason."""


type SteeringCommand = (
	EnqueueSteeringCommand
	| InvocationSteeringCommand
	| DropSteeringCommand
	| CancelRunCommand
)
"""anything one worker asks the worker owning a run to do."""
type SteeringCommandHandler = Callable[[SteeringCommand], Awaitable[None]]
"""applies one delivered command to the local run."""
type SteeringOperation = Literal["enqueue", "drop"]
"""wire tag naming which command a published payload carries."""


async def publish_steering_command(
	run_id: TypeID,
	command: SteeringCommand,
) -> int:
	"""publish one command to the run's owning worker."""
	if isinstance(command, EnqueueSteeringCommand):
		payload: dict[str, object] = {
			"operation": "enqueue",
			"message_id": str(command.message_id),
			"messages": [
				message.model_dump(mode="json") for message in command.messages
			],
			"retractable": command.retractable,
			"thread_id": str(command.thread_id),
			"agent_id": str(command.agent_id),
		}
	elif isinstance(command, InvocationSteeringCommand):
		payload = {
			"operation": "invoke",
			"message_id": str(command.message_id),
			"thread_id": str(command.thread_id),
			"agent_id": str(command.agent_id),
		}
	elif isinstance(command, DropSteeringCommand):
		payload = {
			"operation": "drop",
			"message_id": str(command.message_id),
			"thread_id": str(command.thread_id),
			"agent_id": str(command.agent_id),
		}
	else:
		payload = {"operation": "cancel", "reason": command.reason}
	return await make_run_channel(str(run_id), _STEERING_CHANNEL_SUFFIX).publish(
		payload
	)


def _decode_command(payload: dict[str, object]) -> SteeringCommand | None:
	"""rebuild one published command, or None if the payload is not one.

	returns None rather than raising: a malformed frame on a shared channel is
	dropped with a warning, never allowed to kill the subscriber.
	"""
	operation = payload.get("operation")
	if operation == "cancel":
		reason = payload.get("reason")
		return CancelRunCommand(reason=reason) if isinstance(reason, str) else None
	message_id = payload.get("message_id")
	thread_id = payload.get("thread_id")
	agent_id = payload.get("agent_id")
	# the prefix is checked, not just the type: a well-formed id of the wrong
	# kind would otherwise reach the message and branch queries as its own.
	if not (
		is_typeid(message_id, prefix="msg")
		and is_typeid(thread_id, prefix="thread")
		and is_typeid(agent_id, prefix="agent")
	):
		return None
	if operation == "drop":
		return DropSteeringCommand(
			message_id=TypeID(message_id),
			thread_id=TypeID(thread_id),
			agent_id=TypeID(agent_id),
		)
	if operation == "invoke":
		return InvocationSteeringCommand(
			message_id=TypeID(message_id),
			thread_id=TypeID(thread_id),
			agent_id=TypeID(agent_id),
		)
	messages = payload.get("messages")
	if operation != "enqueue" or not isinstance(messages, list):
		return None
	try:
		sdk_messages = [MessageAdapter.validate_python(message) for message in messages]
	except ValueError:
		return None
	return EnqueueSteeringCommand(
		message_id=TypeID(message_id),
		messages=sdk_messages,
		retractable=payload.get("retractable") is True,
		thread_id=TypeID(thread_id),
		agent_id=TypeID(agent_id),
	)


class SteeringUnavailableError(RuntimeError):
	"""raised when a run cannot attach its cross-worker command subscriber."""


async def start_steering_subscriber(
	run_id: TypeID,
	handler: SteeringCommandHandler,
) -> asyncio.Task[None]:
	"""attach the command subscriber on the worker that owns the run.

	the first attach is not retried: steering is what makes ``/steer`` and
	``/cancel`` reach the run from any worker, so a run that cannot attach is
	a run that must not start. reconnects after a successful attach keep
	backing off, because by then the run exists and is worth recovering.
	"""
	channel = make_run_channel(str(run_id), _STEERING_CHANNEL_SUFFIX)
	ready = asyncio.Event()
	attach_failure: BaseException | None = None
	attached_once = False

	async def _listen() -> None:
		"""hold the subscription open, reconnecting for the run's lifetime."""
		nonlocal attach_failure, attached_once
		backoff = 0.5
		while True:
			try:
				ready.clear()
				async with channel.attached() as messages:
					attached_once = True
					ready.set()
					async for payload in messages:
						command = _decode_command(payload)
						if command is None:
							logger.warning(
								"dropping malformed steering command for run %s",
								run_id,
							)
							continue
						try:
							await handler(command)
						except Exception:
							logger.exception(
								"steering command failed for run %s",
								run_id,
							)
				backoff = 0.5
			except asyncio.CancelledError:
				return
			except Exception as exc:
				logger.exception("steering subscriber failed for run %s", run_id)
				if not attached_once:
					attach_failure = exc
					ready.set()
					return
				await asyncio.sleep(backoff)
				backoff = min(backoff * 2, 5.0)

	task = create_background_task(_listen(), name=f"run-steering:{run_id}")
	try:
		async with asyncio.timeout(5):
			await ready.wait()
	except BaseException:
		task.cancel()
		raise
	if attach_failure is not None:
		raise SteeringUnavailableError(str(run_id)) from attach_failure
	return task
