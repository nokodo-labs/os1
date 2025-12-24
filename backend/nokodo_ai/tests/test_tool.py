"""tests for SDK tool decorator and class."""

import pytest

from nokodo_ai import Tool, ToolExecutionContext, tool


def test_tool_decorator_basic() -> None:
	@tool(description="add two numbers")
	def add(a: int, b: int) -> int:
		return a + b

	assert isinstance(add, Tool)
	assert add.name == "add"
	assert add.description == "add two numbers"


def test_tool_decorator_custom_name() -> None:
	@tool(name="calculator", description="do math")
	def compute(expr: str) -> float:
		return 0.0

	assert compute.name == "calculator"


@pytest.mark.asyncio
async def test_tool_sync_call() -> None:
	@tool(description="multiply")
	def multiply(a: int, b: int) -> int:
		return a * b

	result = await multiply(a=3, b=4)
	assert result == 12


@pytest.mark.asyncio
async def test_tool_async_call() -> None:
	@tool(description="async add")
	async def async_add(a: int, b: int) -> int:
		return a + b

	result = await async_add(a=5, b=7)
	assert result == 12


@pytest.mark.asyncio
async def test_tool_context_forwarded_when_supported() -> None:
	received: dict[str, object] = {}

	@tool(description="needs context")
	def with_context(value: int, __context: ToolExecutionContext) -> int:
		received["call_id"] = __context.call_id
		return value

	ctx = ToolExecutionContext(call_id="call-1")
	result = await with_context(value=7, __context=ctx)
	assert result == 7
	assert received["call_id"] == "call-1"


@pytest.mark.asyncio
async def test_tool_context_forwarded_via_kwargs() -> None:
	received: dict[str, object] = {}

	@tool(description="kwargs context")
	def kwargs_tool(value: int, **kwargs: object) -> int:
		received["context"] = kwargs.get("__context")
		return value

	ctx = ToolExecutionContext(call_id="call-kw")
	assert await kwargs_tool(value=5, __context=ctx) == 5
	assert received["context"] is ctx


@pytest.mark.asyncio
async def test_tool_context_ignored_when_not_supported() -> None:
	@tool(description="no context")
	def without_context(value: int) -> int:
		return value

	ctx = ToolExecutionContext(call_id="call-2")
	assert await without_context(value=3, __context=ctx) == 3
