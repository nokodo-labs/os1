"""tests for SDK tool decorator and class."""

import pytest

from nokodo_ai import Tool, tool


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
