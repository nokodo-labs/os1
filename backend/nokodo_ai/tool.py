"""Tool decorator and class - callable capabilities for agents."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, ParamSpec

from nokodo_ai.types.json import JSONObject


P = ParamSpec("P")


@dataclass(frozen=True, slots=True)
class ToolExecutionContext:
	"""context provided to a tool during execution."""

	call_id: str
	thread: Thread | None = None


if TYPE_CHECKING:
	from nokodo_ai.thread import Thread


@dataclass
class Tool:
	"""a callable tool that can be used by an agent.

	tools are functions with metadata that agents can invoke
	to perform actions or retrieve information.
	"""

	name: str
	description: str
	func: Callable[..., object]
	parameters: JSONObject = field(default_factory=dict)
	metadata: JSONObject | None = None

	async def call(
		self,
		**kwargs: object,
	) -> object:
		"""execute the tool with the given arguments.

		a reserved kwarg `__context` may be provided and will be forwarded to the
		tool function only if it explicitly accepts it (or accepts **kwargs).
		"""
		context = None
		if "__context" in kwargs:
			context = kwargs.pop("__context")

		call_kwargs = dict(kwargs)
		if context is not None:
			sig = inspect.signature(self.func)
			params = sig.parameters
			accepts_context = "__context" in params or any(
				p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()
			)
			if accepts_context:
				call_kwargs["__context"] = context

		result = self.func(**call_kwargs)
		# handle async functions
		if isinstance(result, Awaitable):
			return await result
		return result

	async def __call__(self, **kwargs: object) -> object:
		return await self.call(**kwargs)


def tool(
	name: str | None = None,
	description: str = "",
	parameters: JSONObject | None = None,
) -> Callable[[Callable[P, object]], Tool]:
	"""decorator to create a tool from a function.

	usage:
		@tool(description="add two numbers together")
		def add(a: int, b: int) -> int:
			return a + b

		@tool(name="calculator", description="perform math operations")
		async def calculate(expression: str) -> float:
			...
	"""

	def decorator(func: Callable[P, object]) -> Tool:
		tool_name = name or func.__name__
		tool_desc = description or func.__doc__ or ""
		tool_parameters = parameters or {}
		return Tool(
			name=tool_name,
			description=tool_desc,
			func=func,
			parameters=tool_parameters,
		)

	return decorator
