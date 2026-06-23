"""application context for SDK execution.

AppContext is injected into tools and filters during agent execution.
it provides access to session, auth, and an event_emitter callback.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from api.models.event import Event
from api.schemas.message import Citation
from api.v1.service.auth import Principal
from nokodo_ai.utils.typeid import TypeID


EventEmitter = Callable[[Event], Awaitable[None]]


@dataclass
class RetrievalContext:
	"""shared retrieval state for a single agent run.

	populated explicitly in agents.py before the filter loop using
	thread.recent_turns(). filters read from this context rather than
	computing their own queries or embeddings.
	"""

	query_text: str | None = None
	query_embedding: list[float] | None = None


@dataclass(frozen=True, slots=True)
class AppContext:
	"""application context passed to SDK tools and filters.

	provides:
	- session: database access
	- principal: authenticated user
	- event_emitter: function to broadcast events in real-time
	- run_id: active API run id, when the SDK is running inside a persisted run
	- context_window: model context window in tokens (from Model ORM)
	- retrieval: shared embedding cache for the current run

	usage in a tool:
		async def call(self, agent_ctx, app_ctx: AppContext | None, **kwargs):
			if app_ctx is None:
				raise ValueError("AppContext is required for MyTool")
			event = Event(...)
			await app_ctx.event_emitter(event)
			return self.success("done", agent_ctx)
	"""

	session: AsyncSession
	principal: Principal
	event_emitter: EventEmitter
	run_id: TypeID | None = None
	agent_id: TypeID | None = None
	thread_id: TypeID | None = None
	final_assistant_message_ref: str | None = None
	context_window: int | None = None
	retrieval: RetrievalContext = field(default_factory=RetrievalContext)
	citations: list[Citation] = field(
		default_factory=list,
	)

	@property
	def user_id(self) -> TypeID:
		return self.principal.user_id

	def with_emitter(self, emitter: EventEmitter) -> AppContext:
		"""create a new context with a specific emitter."""
		return AppContext(
			session=self.session,
			principal=self.principal,
			run_id=self.run_id,
			agent_id=self.agent_id,
			thread_id=self.thread_id,
			final_assistant_message_ref=self.final_assistant_message_ref,
			event_emitter=emitter,
			context_window=self.context_window,
			retrieval=self.retrieval,
			citations=self.citations,
		)
