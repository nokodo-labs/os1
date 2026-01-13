"""
nokodo_ai SDK - AI execution abstractions.

a publishable, standalone library providing unified interfaces for LLMs, embeddings,
vector stores, tools, and agents - with pluggable adapters for different providers.

core principle: magic by default, explicitly customizable if needed.

usage (simple):
	from nokodo_ai import LLM, EmbeddingModel

	llm = LLM("gpt-4o")
	response = await llm.generate(messages)

	embedder = EmbeddingModel(model="openai:text-embedding-3-large")
	vectors = await embedder.embed(["hello", "world"])

usage (explicit adapter):
	from nokodo_ai import LLM
	from nokodo_ai.adapters.openai import OpenAIResponsesAdapter

	adapter = OpenAIResponsesAdapter(api_key="...", base_url="https://custom-proxy.com")
	llm = LLM(adapter=adapter)
"""

from __future__ import annotations

from .agents import Agent
from .chat_models import ChatModel
from .context import AgentContext
from .deltas import AgentDelta, ChatModelDelta
from .embeddings import EmbeddingModel
from .filters import Filter
from .hooks import Hook
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
	"Vectorstore",
	"Agent",
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
