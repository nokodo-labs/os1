"""run-steering filter: drains an external inbox into the agent's thread.

this is the API-side glue that turns the SDK's generic ``Filter`` primitive
into the run-steering feature. installed at the front of the per-run
agent's filter chain (via ``Agent.model_copy(update={"filters": ...})``)
so injected user messages are visible to all downstream context-aware
filters this iteration.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from pydantic import ConfigDict, Field, SkipValidation

from nokodo_ai.agents import AgentIterationState
from nokodo_ai.context import AgentContext
from nokodo_ai.filters import Filter
from nokodo_ai.messages import UserMessage as SDKUserMessage


logger = logging.getLogger(__name__)


# returns the user messages currently queued for injection. MUST be
# atomic with respect to concurrent drop requests so the filter cannot
# inject a message that was simultaneously flagged dropped.
SteeringClaimCallback = Callable[[], Awaitable[list[SDKUserMessage]]]
# receives the user messages just drained from the inbox and appended to
# the thread. used by the API to broadcast the ``run.steering.injected``
# lifecycle event and stamp persistent message metadata.
SteeringInjectedCallback = Callable[[list[SDKUserMessage]], Awaitable[None]]


class SteeringFilter[AppContextT = None](Filter[AppContextT]):
	"""drain an externally-fed inbox of user messages into the thread.

	an out-of-band caller (the /steer http handler) puts ``UserMessage``
	instances on a per-run inbox while the agent loop is running. this
	filter calls ``claim`` at every iteration boundary to atomically take
	ownership of any queued messages, appends them to the thread in
	order, and notifies ``on_injected`` with the batch.

	using a claim callback (rather than reading the queue directly) keeps
	the drain atomic with the run store's drop path - a concurrent drop
	either wins the lock and removes the message before claim sees it, or
	loses and finds the pending list empty. this eliminates the
	inject-then-drop race that would otherwise leave a message in the
	thread but flagged ``dropped`` in the DB.

	callback exceptions are caught + logged - steering must never break
	the main agent loop.
	"""

	name: str = "steering"
	description: str = (
		"drains externally-enqueued user messages into the thread between"
		" agent iterations"
	)
	model_config = ConfigDict(arbitrary_types_allowed=True)
	claim: SkipValidation[SteeringClaimCallback] = Field(
		...,
		description="async callback that atomically drains and returns"
		" the queued user messages",
	)
	on_injected: SkipValidation[SteeringInjectedCallback | None] = Field(
		default=None,
		description="async callback invoked with the drained batch when"
		" at least one message was injected",
	)

	async def process(
		self,
		state: AgentIterationState[AppContextT],
		agent_context: AgentContext,
		app_context: AppContextT | None,
	) -> AgentIterationState[AppContextT]:
		_ = (agent_context, app_context)  # steering is application-agnostic
		drained = await self.claim()
		if not drained:
			return state
		for msg in drained:
			state.thread.add(msg)
		if self.on_injected is not None:
			try:
				await self.on_injected(drained)
			except Exception:
				logger.exception("SteeringFilter on_injected callback raised")
		return state
