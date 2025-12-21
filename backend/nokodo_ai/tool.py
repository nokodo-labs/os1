"""Tool decorator and class - callable capabilities for agents."""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import ParamSpec, TypeVar


P = ParamSpec("P")
R = TypeVar("R")


@dataclass
class Tool:
	"""a callable tool that can be used by an agent.

	tools are functions with metadata that agents can invoke
	to perform actions or retrieve information.
	"""

	name: str
	description: str
	func: Callable[..., object]
	parameters: dict[str, object] = field(default_factory=dict)

	async def __call__(self, **kwargs: object) -> object:
		"""execute the tool with the given arguments."""
		result = self.func(**kwargs)
		# handle async functions
		if hasattr(result, "__await__"):
			return await result
		return result


def tool(
	name: str | None = None,
	description: str = "",
) -> Callable[[Callable[P, R]], Tool]:
	"""decorator to create a tool from a function.

	usage:
		@tool(description="add two numbers together")
		def add(a: int, b: int) -> int:
			return a + b

		@tool(name="calculator", description="perform math operations")
		async def calculate(expression: str) -> float:
			...
	"""

	def decorator(func: Callable[P, R]) -> Tool:
		tool_name = name or func.__name__
		tool_desc = description or func.__doc__ or ""

		# extract parameter info from function signature
		# (full implementation would use inspect module)
		parameters: dict[str, object] = {}

		return Tool(
			name=tool_name,
			description=tool_desc,
			func=func,
			parameters=parameters,
		)

	return decorator
