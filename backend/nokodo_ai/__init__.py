"""
nokodo_ai SDK - AI execution abstractions.

a publishable, standalone library providing unified interfaces for chat models,
embeddings, vector stores, tools, and agents - with pluggable adapters for
different providers.

core principle: magic by default, explicitly customizable if needed.

usage:
	from nokodo_ai import ChatModel, EmbeddingModel

	chat_model = ChatModel.create(
		"gpt-4o",
		adapter={"type": "openai", "api_key": "..."},
	)
	response = await chat_model.generate(messages)

	embedder = EmbeddingModel.create(
		"text-embedding-3-large",
		adapter={"type": "openai", "api_key": "..."},
	)
	vectors = await embedder.embed(["hello", "world"])
"""

from __future__ import annotations

from .agents import Agent, AgentIterationState, AgentToolChoice
from .chat_models import ChatModel
from .context import AgentContext
from .deltas import AgentDelta, ChatModelDelta
from .embeddings import EmbeddingModel
from .filters import Filter
from .hooks import Hook
from .image_models import ImageModel
from .messages import (
	AssistantMessage,
	BaseMessage,
	ContentPart,
	FileContent,
	ImageContent,
	JsonContent,
	Message,
	RefusalContent,
	SystemMessage,
	TextContent,
	ToolCall,
	ToolMessage,
	Usage,
	UserMessage,
)
from .threads import Thread
from .tool import Tool, ToolDefinition, tool
from .types import JSONArray, JSONObject, JSONValue
from .vectorstores import Vectorstore


__all__ = [
	# high-level interfaces
	"ChatModel",
	"EmbeddingModel",
	"ImageModel",
	"Vectorstore",
	"Agent",
	"AgentIterationState",
	"AgentToolChoice",
	"ChatModelDelta",
	"AgentDelta",
	# tools
	"Tool",
	"ToolDefinition",
	"tool",
	# context, filters, and hooks
	"AgentContext",
	"Filter",
	"Hook",
	# domain models
	"Thread",
	"Message",
	"BaseMessage",
	"UserMessage",
	"AssistantMessage",
	"ToolMessage",
	"SystemMessage",
	"ToolCall",
	# content types
	"ContentPart",
	"TextContent",
	"JsonContent",
	"ImageContent",
	"FileContent",
	"RefusalContent",
	"Usage",
	# json types
	"JSONValue",
	"JSONObject",
	"JSONArray",
]
