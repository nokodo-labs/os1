"""
nokodo_ai SDK - AI execution abstractions.

a publishable, standalone library providing unified interfaces for LLMs, embeddings,
vector stores, tools, and agents — with pluggable adapters for different providers.

core principle: magic by default, explicitly customizable if needed.

usage (simple):
	from nokodo_ai import LLM, EmbeddingModel

	llm = LLM("gpt-4o")
	response = await llm.generate(messages)

	embedder = EmbeddingModel("openai:text-embedding-3-large")
	vectors = await embedder.embed(["hello", "world"])

usage (explicit adapter):
	from nokodo_ai import LLM
	from nokodo_ai.adapters.openai import OpenAIResponsesAdapter

	adapter = OpenAIResponsesAdapter(api_key="...", base_url="https://custom-proxy.com")
	llm = LLM(adapter=adapter)
"""

from __future__ import annotations

from nokodo_ai.agent import Agent
from nokodo_ai.embedding import EmbeddingModel
from nokodo_ai.llm import LLM
from nokodo_ai.message import (
	AssistantMessage,
	Message,
	SystemMessage,
	ToolCall,
	ToolMessage,
	ToolResult,
	UserMessage,
)
from nokodo_ai.thread import Thread
from nokodo_ai.tool import Tool, tool
from nokodo_ai.vectorstore import Vectorstore


__all__ = [
	# high-level interfaces
	"LLM",
	"EmbeddingModel",
	"Vectorstore",
	"Agent",
	"Tool",
	"tool",
	# domain models
	"Thread",
	"Message",
	"UserMessage",
	"AssistantMessage",
	"ToolMessage",
	"SystemMessage",
	"ToolCall",
	"ToolResult",
]
