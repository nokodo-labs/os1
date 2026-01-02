"""SDK-level filters for pre and post processing of agent messages."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Literal

from pydantic import Field

from nokodo_ai.base import Base
from nokodo_ai.thread import Thread


class BaseFilter[AppContextT, PhaseT: Literal["pre", "post"]](Base, ABC):
	"""base class for all filters.

	filters process messages at specific points in the agent execution:
	- pre-filters run BEFORE sending messages to the model
	- post-filters run AFTER receiving messages from the model

	filters are generic over AppContextT, allowing application-specific
	context to be passed through the entire agent execution pipeline.
	"""

	phase: PhaseT = Field(..., description="the filter phase: 'pre' or 'post'")

	@abstractmethod
	async def process(
		self,
		thread: Thread,
		app_context: AppContextT,
	) -> ...:
		"""process messages through this filter.

		args:
			messages: the messages to process
			agent_context: runtime context from the agent
			app_context: application-specific context

		returns:
			processed messages (may be modified, augmented, or filtered)
		"""
		raise NotImplementedError("process method must be implemented by subclasses")


class PreFilter[AppContextT](BaseFilter[AppContextT, Literal["pre"]], ABC):
	"""base class for pre-processing filters.

	pre-filters run BEFORE an agent sends messages to the model.
	they can modify, augment, or filter the input messages.

	common uses:
	- injecting context (memories, user preferences)
	- modifying system prompts
	- adding retrieval-augmented context
	"""

	@abstractmethod
	async def process(
		self,
		thread: Thread,
		app_context: AppContextT,
	) -> Thread:
		"""process messages through this pre-filter.

		args:
			thread: the current conversation thread
			agent_context: runtime context from the agent
			app_context: application-specific context
		returns:
			processed thread (may be modified, augmented, or filtered)
		"""
		raise NotImplementedError("process method must be implemented by subclasses")


class PostFilter[AppContextT](BaseFilter[AppContextT, Literal["post"]], ABC):
	"""base class for post-processing filters.

	post-filters run AFTER an agent receives messages from the model.
	they can modify, validate, or extract information from responses.

	common uses:
	- extracting structured data
	- validating responses
	- logging or analytics
	- memory extraction
	"""

	@abstractmethod
	async def process(
		self,
		thread: Thread,
		app_context: AppContextT,
	) -> None:
		"""process messages through this post-filter.

		args:
			thread: the current conversation thread
			agent_context: runtime context from the agent
			app_context: application-specific context

		returns:
			None: since agents might be streaming data, post-filters cannot modify
			or return messages. they can perform side effects like logging or
			analytics.
		"""
		raise NotImplementedError("process method must be implemented by subclasses")


Filter = PreFilter | PostFilter
