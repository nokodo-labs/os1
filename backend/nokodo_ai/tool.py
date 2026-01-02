"""Tool ABC and implementations - callable capabilities for agents."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from functools import cached_property
from typing import Concatenate

from pydantic import Field

from nokodo_ai.base import Base
from nokodo_ai.context import AgentContext
from nokodo_ai.messages import ToolMessage
from nokodo_ai.types.json import JSONObject
from nokodo_ai.utils.json_schema import schema_from_callable
from nokodo_ai.utils.validators import validate_callable


class ToolDefinition(Base):
	"""schema-only tool definition for LLM APIs.

	this contains just the metadata needed to describe a tool to an LLM,
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
		"""get the tool definition for LLM APIs.

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
		__agent_context__: AgentContext,
		__app_context__: AppContextT,
		**kwargs: object,
	) -> ToolMessage:
		"""execute the tool with the given arguments.

		args:
			__agent_context__: runtime context from the agent execution
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
		agent_context: AgentContext,
	) -> ToolMessage:
		"""helper to create a successful tool response."""
		return ToolMessage(
			tool_call_id=agent_context.tool_call_id,
			tool_output=output,
			metadata=agent_context.metadata,
			is_error=False,
		)

	def error(
		self,
		message: str,
		agent_context: AgentContext,
	) -> ToolMessage:
		"""helper to create an error tool response."""
		return ToolMessage(
			tool_call_id=agent_context.tool_call_id,
			tool_output=message,
			metadata=agent_context.metadata,
			is_error=True,
		)


def tool[AppContextT = None](name: str | None = None, description: str | None = None):
	"""decorator to define a function as a Tool subclass."""

	def decorator(
		func: Callable[Concatenate[AgentContext, AppContextT, ...], ToolMessage],
	) -> Tool[AppContextT]:
		# validate structure only - skip type check on __app_context__ since it's
		# a TypeVar that can be any type
		validate_callable(
			func,
			expected_arg_types=[AgentContext],
			expected_arg_count={"min": 2, "max": None},
			expected_arg_names=["__agent_context__", "__app_context__"],
			expected_return_type=ToolMessage,
		)

		# pre-generate schema from original func to avoid TypeVar resolution issues
		schema = schema_from_callable(func, skip_self=False, skip_dunder=True)

		class FuncTool(Tool[AppContextT]):
			async def call(
				self,
				__agent_context__: AgentContext,
				__app_context__: AppContextT,
				**kwargs: object,
			) -> ToolMessage:
				return func(
					__agent_context__,
					__app_context__,
					**kwargs,
				)

		return FuncTool(
			name=name or func.__name__,
			description=description or func.__doc__ or "No description provided.",
			parameters=schema or None,
		)

	return decorator
