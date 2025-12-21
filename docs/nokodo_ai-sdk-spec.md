# nokodo_ai SDK Architecture

## Overview

The SDK is a **publishable, standalone library** for AI execution abstractions. It provides unified interfaces for LLMs, embeddings, vector stores, tools, and agents — with pluggable adapters for different providers and APIs.

**Core principle:** magic by default, explicitly customizable if needed.

## Domain Models

The SDK still defines **Thread** and **Message** types — but these are:

-   pure domain models (pydantic)
-   completely decoupled from ORM
-   simpler than API schemas (only what's needed for execution)

```python
# example — minimal, execution-focused
@dataclass
class UserMessage:
    content: str

@dataclass
class AssistantMessage:
    content: str
    tool_calls: list[ToolCall] | None = None

@dataclass
class Thread:
    messages: list[UserMessage | AssistantMessage | ToolMessage]
```

The API layer maps these ↔ ORM as needed. The SDK doesn't care how they're stored.

---

## Adapter Architecture

### Key Insight

> adapter ≠ provider
> adapter = **interface shape to a specific API**

Example: OpenAI has multiple chat APIs with different shapes:

| API              | endpoint               |
| ---------------- | ---------------------- |
| Chat Completions | `/v1/chat/completions` |
| Responses        | `/v1/responses`        |
| Realtime         | websocket              |
| Assistants       | `/v1/assistants`       |

Each is a **separate adapter** implementing the **same capability interface**.

### Inheritance Model

```
CAPABILITY bases (interface shape)
├── BaseChatAdapter (ABC)
│   └── generate()
└── BaseEmbeddingAdapter (ABC)
    └── embed()

PROVIDER bases (shared infra)
├── BaseAdapter (ABC)
│   └── base infra all adapters share
├── BaseOpenAIAdapter(BaseAdapter)
│   └── openai client, api_key, timeouts
└── BaseAnthropicAdapter(BaseAdapter)
    └── anthropic client, api_key

CONCRETE adapters (multiple inheritance)
├── OpenAIChatCompletionsAdapter(BaseOpenAIAdapter, BaseChatAdapter)
├── OpenAIResponsesAdapter(BaseOpenAIAdapter, BaseChatAdapter)
├── OpenAIEmbeddingAdapter(BaseOpenAIAdapter, BaseEmbeddingAdapter)
└── AnthropicMessagesAdapter(BaseAnthropicAdapter, BaseChatAdapter)
```

---

## Directory Structure

```
nokodo_ai/
├── __init__.py
│
├── llm.py                          # LLM class
├── embedding.py                    # EmbeddingModel class
├── vectorstore.py                  # Vectorstore class
├── tool.py                         # Tool decorator/class
├── agent.py                        # Agent class
│
├── thread.py                       # Thread
├── message.py                      # UserMessage, AssistantMessage, ToolMessage, etc.
│
└── adapters/
    ├── __init__.py
    ├── base.py                     # BaseAdapter
    ├── chat.py                     # BaseChatAdapter
    ├── embedding.py                # BaseEmbeddingAdapter
    ├── vectorstore.py              # BaseVectorstoreAdapter
    │
    ├── openai/
    │   ├── __init__.py
    │   ├── base.py                 # BaseOpenAIAdapter
    │   ├── chat_completions.py     # OpenAIChatCompletionsAdapter
    │   ├── responses.py            # OpenAIResponsesAdapter
    │   └── embedding.py            # OpenAIEmbeddingAdapter
    │
    ├── anthropic/
    │   ├── __init__.py
    │   ├── base.py                 # BaseAnthropicAdapter
    │   └── messages.py             # AnthropicMessagesAdapter
    │
    └── ollama/
        ├── __init__.py
        ├── base.py                 # BaseOllamaAdapter
        ├── chat.py                 # OllamaChatAdapter
        └── embedding.py            # OllamaEmbeddingAdapter
```

---

## Usage Examples

### Simple (magic)

```python
from nokodo_ai import LLM, EmbeddingModel

llm = LLM("gpt-4o")  # auto-selects default adapter -> OpenAIChatCompletionsAdapter
openai_llm = LLM("openai:gpt-4o") # auto-selects OpenAIChatCompletionsAdapter
openai_responses_llm = LLM("openai.responses:gpt-4o") # specifies adapter
embedder = EmbeddingModel("openai:text-embedding-3-large")

response = await llm.generate(messages)

# or streaming
async for chunk in llm.generate(messages, stream=True):
    ...
vectors = await embedder.embed(["hello", "world"])
```

### Explicit (custom adapter)

```python
from nokodo_ai import LLM
from nokodo_ai.adapters.openai import OpenAIResponsesAdapter

adapter = OpenAIResponsesAdapter(
    api_key="...",
    base_url="https://custom-proxy.com", # this allows use of any API shape with any provider
    timeout=60,
)

llm = LLM(adapter=adapter)
```

### Different APIs, same interface

```python
from nokodo_ai import LLM
from nokodo_ai.adapters.openai import (
    OpenAIChatCompletionsAdapter,
    OpenAIResponsesAdapter,
)

# both work identically
llm1 = LLM(adapter=OpenAIChatCompletionsAdapter(...))
llm2 = LLM(adapter=OpenAIResponsesAdapter(...))

await llm1.generate(messages)  # uses /v1/chat/completions
await llm2.generate(messages)  # uses /v1/responses

# both also support streaming with the same entrypoint
async for chunk in llm1.generate(messages, stream=True):
    ...
```

---

## Summary

| component                                   | responsibility                        |
| ------------------------------------------- | ------------------------------------- |
| `LLM`, `EmbeddingModel`, `Vectorstore`      | high-level unified interfaces         |
| `Agent`                                     | orchestrates LLM + Tools              |
| `Tool`                                      | callable capability for agents        |
| `Thread`, `Message`                         | execution-focused domain models       |
| `BaseChatAdapter`, `BaseEmbeddingAdapter`   | capability ABCs (interface shape)     |
| `BaseOpenAIAdapter`, `BaseAnthropicAdapter` | provider ABCs (shared client/auth)    |
| concrete adapters                           | multiple inheritance, implements both |
