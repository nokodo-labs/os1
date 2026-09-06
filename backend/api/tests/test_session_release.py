"""the API frees its own database connections around SDK callbacks.

the SDK used to do this through a `ReleasesResources` protocol it sniffed on
the app context. that made freeing a caller's resources part of the contract
for running an agent, which it is not - so the release moved here, to the API's
own filter/hook boundary.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from api.v1.service.chat.context import AppContext
from api.v1.service.chat.filters.base import Filter
from api.v1.service.chat.hooks.base import Hook
from api.v1.service.chat.session_release import releasing_session
from api.v1.service.chat.tools.base import Tool
from nokodo_ai.agents import AgentIterationSnapshot, AgentIterationState
from nokodo_ai.chat_models import ChatModel
from nokodo_ai.context import AgentContext, ToolCallContext
from nokodo_ai.messages import ToolMessage
from nokodo_ai.threads import Thread
from nokodo_ai.types.json import JSONObject


pytestmark = pytest.mark.asyncio


def _app_context() -> tuple[AppContext, AsyncMock]:
	"""an app context plus the session mock, which its type otherwise hides."""
	principal = MagicMock()
	principal.user.id = "usr_release"
	session = AsyncMock()
	context = AppContext(
		session=session,
		principal=principal,
		event_emitter=AsyncMock(),
	)
	return context, session


def _agent_context() -> AgentContext:
	return AgentContext(model=ChatModel.model_construct(model_name="test"))


def _state() -> AgentIterationState[AppContext]:
	return AgentIterationState(thread=Thread(), tools=[])


async def test_filter_releases_its_session_after_running() -> None:
	class _Ok(Filter):
		name: str = "ok"

		async def run(
			self,
			state: AgentIterationState[AppContext],
			agent_context: AgentContext,
			app_context: AppContext | None,
		) -> AgentIterationState[AppContext]:
			_ = agent_context, app_context
			return state

	app_context, session = _app_context()

	await _Ok().process(_state(), _agent_context(), app_context)

	session.close.assert_awaited_once()


async def test_a_failing_filter_still_releases_and_keeps_its_own_error() -> None:
	"""the release must not swallow or replace what actually went wrong."""

	class _Boom(Filter):
		name: str = "boom"

		async def run(
			self,
			state: AgentIterationState[AppContext],
			agent_context: AgentContext,
			app_context: AppContext | None,
		) -> AgentIterationState[AppContext]:
			_ = state, agent_context, app_context
			raise RuntimeError("filter exploded")

	app_context, session = _app_context()

	with pytest.raises(RuntimeError, match="filter exploded"):
		await _Boom().process(_state(), _agent_context(), app_context)

	session.close.assert_awaited_once()


async def test_hook_releases_its_session_after_running() -> None:
	class _Ok(Hook):
		name: str = "ok"

		async def run(
			self,
			state: AgentIterationSnapshot[AppContext],
			agent_context: AgentContext,
			app_context: AppContext | None,
		) -> None:
			_ = state, agent_context, app_context

	app_context, session = _app_context()

	await _Ok().execute(_state().snapshot(), _agent_context(), app_context)

	session.close.assert_awaited_once()


def _tool_call_context() -> ToolCallContext:
	return ToolCallContext(tool_call_id="tc_release", tool_call_start_time=0.0)


async def test_tool_releases_its_session_after_running() -> None:
	class _Ok(Tool):
		name: str = "ok"
		description: str = "returns"
		parameters: JSONObject = {}

		async def run(
			self,
			__state__: AgentIterationSnapshot[AppContext],
			__agent_context__: AgentContext,
			__tool_call_context__: ToolCallContext,
			__app_context__: AppContext | None,
			**kwargs: object,
		) -> ToolMessage:
			_ = (__state__, __agent_context__, __app_context__, kwargs)
			return self.success("done", __tool_call_context__)

	app_context, session = _app_context()

	await _Ok().call(
		_state().snapshot(),
		_agent_context(),
		_tool_call_context(),
		app_context,
	)

	session.close.assert_awaited_once()


async def test_a_failing_tool_still_releases_and_keeps_its_own_error() -> None:
	"""the SDK turns this into an error tool result; the release must not
	replace what the tool actually raised on the way there."""

	class _Boom(Tool):
		name: str = "boom"
		description: str = "raises"
		parameters: JSONObject = {}

		async def run(
			self,
			__state__: AgentIterationSnapshot[AppContext],
			__agent_context__: AgentContext,
			__tool_call_context__: ToolCallContext,
			__app_context__: AppContext | None,
			**kwargs: object,
		) -> ToolMessage:
			_ = (
				__state__,
				__agent_context__,
				__tool_call_context__,
				__app_context__,
				kwargs,
			)
			raise RuntimeError("tool exploded")

	app_context, session = _app_context()

	with pytest.raises(RuntimeError, match="tool exploded"):
		await _Boom().call(
			_state().snapshot(),
			_agent_context(),
			_tool_call_context(),
			app_context,
		)

	session.close.assert_awaited_once()


async def test_a_failing_close_never_replaces_the_callers_exception() -> None:
	"""a connection we cannot return is not the story worth reporting."""
	app_context, session = _app_context()
	session.close.side_effect = RuntimeError("pool is gone")

	with pytest.raises(ValueError, match="the real problem"):
		async with releasing_session(app_context):
			raise ValueError("the real problem")


async def test_release_is_a_no_op_without_an_app_context() -> None:
	"""filters run without one in tests and in agent-less paths."""
	async with releasing_session(None):
		pass
