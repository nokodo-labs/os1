"""tests for SDK Tool base class and decorator."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable

import pytest

from nokodo_ai import AgentContext, ChatModel, Tool, ToolMessage, tool
from nokodo_ai.adapters.base.chat import (
	BaseChatAdapter,
	ChatGenerationParams,
)
from nokodo_ai.messages import AssistantMessage, Message
from nokodo_ai.threads import Thread
from nokodo_ai.tool import ToolDefinition
from nokodo_ai.types.json import JSONObject


class _NoopChatAdapter(BaseChatAdapter):
	def generate(  # type: ignore[override]
		self,
		messages: list[Message],
		model: str,
		stream: bool = False,
		tools: list[ToolDefinition] = [],
		params: ChatGenerationParams | None = None,
	) -> Awaitable[AssistantMessage] | AsyncIterator[AssistantMessage]:
		raise AssertionError("adapter.generate should not be called in tool tests")


def _make_agent_context(
	tool_call_id: str = "tc1",
	*,
	metadata: JSONObject | None = None,
) -> AgentContext:
	chat_model = ChatModel.model_construct(
		api=None,
		model_name="stub",
		adapter=_NoopChatAdapter(),
	)
	return AgentContext(
		thread=Thread(),
		model=chat_model,
		iteration=0,
		tool_call_id=tool_call_id,
		metadata=metadata or {},
	)


class _AddTool(Tool[None]):
	async def call(  # type: ignore[override]
		self,
		__agent_context__: AgentContext,
		__app_context__: None,
		*,
		a: int = 0,
		b: int = 0,
	) -> ToolMessage:
		return self.success(str(a + b), __agent_context__)


class _CallsSuperTool(Tool[None]):
	async def call(  # type: ignore[override]
		self,
		__agent_context__: AgentContext,
		__app_context__: None,
		**kwargs: object,
	) -> ToolMessage:
		return await super().call(__agent_context__, __app_context__, **kwargs)  # type: ignore[safe-super]


def test_tool_definition_uses_explicit_parameters() -> None:
	params: JSONObject = {
		"type": "object",
		"properties": {"a": {"type": "integer"}},
		"required": ["a"],
	}
	add_tool = _AddTool(
		name="add",
		description="add two numbers",
		parameters=params,
	)
	definition = add_tool.definition
	assert isinstance(definition, ToolDefinition)
	assert definition.name == "add"
	assert definition.description == "add two numbers"
	assert definition.parameters == params
	assert add_tool.parameters_resolved == params


def test_tool_parameters_resolved_is_cached() -> None:
	add_tool = _AddTool(name="add", description="add")
	first = add_tool.parameters_resolved
	second = add_tool.parameters_resolved
	assert first is second
	assert "properties" in first


def test_tool_success_and_error_helpers_include_metadata() -> None:
	ctx = _make_agent_context("call-1", metadata={"x": "y"})
	add_tool = _AddTool(name="add", description="add")

	ok = add_tool.success("ok", ctx)
	assert ok.tool_call_id == "call-1"
	assert ok.tool_output == "ok"
	assert ok.is_error is False
	assert ok.metadata == {"x": "y"}

	err = add_tool.error("no", ctx)
	assert err.tool_call_id == "call-1"
	assert err.tool_output == "no"
	assert err.is_error is True
	assert err.metadata == {"x": "y"}


@pytest.mark.asyncio
async def test_tool_call_returns_tool_message() -> None:
	ctx = _make_agent_context("call-2")
	add_tool = _AddTool(name="add", description="add")
	result = await add_tool.call(ctx, None, a=2, b=3)
	assert result.tool_output == "5"
	assert result.is_error is False


def test_tool_decorator_creates_tool_instance_and_schema() -> None:
	@tool(name="decorated", description="a decorated tool")
	def decorated(
		__agent_context__: AgentContext,
		__app_context__: None,
		*,
		value: int,
	) -> ToolMessage:
		return ToolMessage(
			tool_call_id=__agent_context__.tool_call_id,
			tool_output=str(value * 2),
		)

	assert isinstance(decorated, Tool)
	assert decorated.name == "decorated"
	assert decorated.description == "a decorated tool"
	params = decorated.parameters_resolved
	assert "properties" in params


@pytest.mark.asyncio
async def test_tool_decorator_executes_function() -> None:
	ctx = _make_agent_context("call-3")

	@tool(description="uses function name")
	def auto_named(
		__agent_context__: AgentContext,
		__app_context__: None,
		*,
		text: str,
	) -> ToolMessage:
		return ToolMessage(
			tool_call_id=__agent_context__.tool_call_id,
			tool_output=text,
		)

	assert auto_named.name == "auto_named"
	result = await auto_named.call(ctx, None, text="ok")
	assert result.tool_output == "ok"


def test_tool_decorator_validates_signature() -> None:
	with pytest.raises(TypeError, match="parameter 0 must be named"):

		@tool(description="bad")
		def bad(
			agent_context: AgentContext,
			app_context: None,
		) -> ToolMessage:
			return ToolMessage(tool_call_id="x", tool_output="y")


@pytest.mark.asyncio
async def test_tool_call_base_raises_not_implemented() -> None:
	ctx = _make_agent_context("call-4")
	t = _CallsSuperTool(name="super", description="calls super")
	with pytest.raises(NotImplementedError, match="call method must be implemented"):
		await t.call(ctx, None)
