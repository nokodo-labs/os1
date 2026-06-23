"""Tool ABC and implementations - callable capabilities for agents."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from functools import cached_property
from inspect import iscoroutinefunction
from typing import TYPE_CHECKING, Concatenate

from pydantic import Field

from .base import Base
from .context import AgentContext, ToolCallContext
from .messages import ToolMessage
from .types.json import JSONObject
from .utils.json_schema import schema_from_callable
from .utils.validators import validate_callable


if TYPE_CHECKING:
	from .agents import AgentIterationSnapshot


class ToolDefinition(Base):
	"""schema-only tool definition for chat model APIs.

	this contains just the metadata needed to describe a tool to a chat model,
	without the actual callable implementation. used by ChatModel/adapters
	which only need to send tool schemas, not execute them.
	"""

	name: str = Field(..., description="name of the tool")
	description: str = Field(..., description="description of the tool")
	parameters: JSONObject = Field(
		..., description="JSON schema of the tool parameters"
	)


class Tool[AppContextT = None](Base, ABC):
	"""abstract base class for agent tools.

	tools are typed capabilities that agents can invoke to perform actions
	or retrieve information. they are generic over AppContextT to allow
	application-specific context to be passed during execution.
	"""

	name: str = Field(...)
	description: str = Field(...)
	parameters: JSONObject | None = Field(default=None)

	@cached_property
	def parameters_resolved(self) -> JSONObject:
		"""resolve parameters schema from get_parameters() if not explicitly set."""
		if self.parameters is not None:
			return self.parameters

		schema = schema_from_callable(
			self.call,
			skip_self=True,
			skip_dunder=True,
		)
		return schema

	@property
	def definition(self) -> ToolDefinition:
		"""get the tool definition for chat model APIs.

		returns just the schema metadata (name, description, parameters)
		without the callable implementation.
		"""
		return ToolDefinition(
			name=self.name,
			description=self.description,
			parameters=self.parameters_resolved,
		)

	@abstractmethod
	async def call(
		self,
		__state__: AgentIterationSnapshot[AppContextT],
		__agent_context__: AgentContext,
		__tool_call_context__: ToolCallContext,
		__app_context__: AppContextT | None,
		**kwargs: object,
	) -> ToolMessage:
		"""execute the tool with the given arguments.

		args:
			__state__: read-only state for the current agent iteration
			__agent_context__: read-only context from the agent run
			__tool_call_context__: context for this tool invocation
			__app_context__: application-specific context
			**kwargs: tool-specific arguments matching get_parameters() schema

		returns:
			ToolMessage containing the result or error
		"""
		raise NotImplementedError(
			"call method must be implemented by concrete subclasses"
		)

	def success(
		self,
		output: str,
		tool_call_context: ToolCallContext,
	) -> ToolMessage:
		"""helper to create a successful tool response."""
		return ToolMessage(
			tool_call_id=tool_call_context.tool_call_id,
			tool_output=output,
			metadata=tool_call_context.metadata,
			is_error=False,
		)

	def error(
		self,
		message: str,
		tool_call_context: ToolCallContext,
	) -> ToolMessage:
		"""helper to create an error tool response."""
		return ToolMessage(
			tool_call_id=tool_call_context.tool_call_id,
			tool_output=message,
			metadata=tool_call_context.metadata,
			is_error=True,
		)


def tool[AppContextT = None](
	name: str | None = None, description: str | None = None
) -> Callable[
	[
		Callable[
			Concatenate[
				AgentIterationSnapshot[AppContextT],
				AgentContext,
				ToolCallContext,
				AppContextT | None,
				...,
			],
			ToolMessage,
		]
	],
	Tool[AppContextT],
]:
	"""decorator to define a function as a Tool subclass."""

	def decorator(
		func: Callable[
			Concatenate[
				AgentIterationSnapshot[AppContextT],
				AgentContext,
				ToolCallContext,
				AppContextT | None,
				...,
			],
			ToolMessage,
		],
	) -> Tool[AppContextT]:
		if iscoroutinefunction(func):
			raise TypeError("tool decorator requires a synchronous function")

		# validate structure only; application context is generic by design.
		validate_callable(
			func,
			expected_arg_types=[None, AgentContext, ToolCallContext],
			expected_arg_count={"min": 4, "max": None},
			expected_arg_names=[
				"__state__",
				"__agent_context__",
				"__tool_call_context__",
				"__app_context__",
			],
			expected_return_type=ToolMessage,
		)

		# pre-generate schema from original func to avoid generic resolution issues.
		schema = schema_from_callable(func, skip_self=False, skip_dunder=True)

		class FuncTool(Tool[AppContextT]):
			async def call(
				self,
				__state__: AgentIterationSnapshot[AppContextT],
				__agent_context__: AgentContext,
				__tool_call_context__: ToolCallContext,
				__app_context__: AppContextT | None,
				**kwargs: object,
			) -> ToolMessage:
				return func(
					__state__,
					__agent_context__,
					__tool_call_context__,
					__app_context__,
					**kwargs,
				)

		func_name = getattr(func, "__name__", "tool")
		func_doc = getattr(func, "__doc__", None)
		return FuncTool(
			name=name or func_name,
			description=description or func_doc or "no description provided.",
			parameters=schema or None,
		)

	return decorator
