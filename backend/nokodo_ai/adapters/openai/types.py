"""centralized OpenAI SDK types for nokodo_ai adapters.

the goal is to keep all OpenAI SDK imports in one place so adapter modules
stay small and type check cleanly.
"""

from __future__ import annotations

from openai._streaming import AsyncStream as OpenAIAsyncStream
from openai.types import (
	ChatModel as OpenAIChatModel,
)
from openai.types import (
	CompletionUsage as OpenAICompletionUsage,
)
from openai.types import (
	ResponsesModel as OpenAIResponsesModel,
)
from openai.types.chat import (
	ChatCompletion as OpenAIChatCompletion,
)
from openai.types.chat import (
	ChatCompletionAssistantMessageParam as OpenAIChatCompletionAssistantMessageParam,
)
from openai.types.chat import (
	ChatCompletionChunk as OpenAIChatCompletionChunk,
)
from openai.types.chat import (
	ChatCompletionMessageFunctionToolCall,
	ChatCompletionMessageFunctionToolCallParam,
)
from openai.types.chat import (
	ChatCompletionMessageParam as OpenAIChatCompletionMessageParam,
)
from openai.types.chat import (
	ChatCompletionMessageToolCallUnion as OpenAIChatCompletionMessageToolCallUnion,
)
from openai.types.chat import (
	ChatCompletionSystemMessageParam as OpenAIChatCompletionSystemMessageParam,
)
from openai.types.chat import (
	ChatCompletionToolChoiceOptionParam as OpenAIChatCompletionToolChoiceOptionParam,
)
from openai.types.chat import (
	ChatCompletionToolMessageParam as OpenAIChatCompletionToolMessageParam,
)
from openai.types.chat import (
	ChatCompletionToolParam as OpenAIChatCompletionToolParam,
)
from openai.types.chat import (
	ChatCompletionUserMessageParam as OpenAIChatCompletionUserMessageParam,
)
from openai.types.chat.chat_completion_tool_param import (
	FunctionDefinition as OpenAIChatCompletionFunctionDefinition,
)
from openai.types.responses import (
	EasyInputMessageParam as OpenAIEasyInputMessageParam,
)
from openai.types.responses import (
	FunctionToolParam as OpenAIResponseFunctionToolParam,
)
from openai.types.responses import (
	Response as OpenAIResponse,
)
from openai.types.responses import (
	ResponseFormatTextJSONSchemaConfigParam as OpenAIResponseTextJSONSchemaConfigParam,
)
from openai.types.responses import (
	ResponseFunctionCallOutputItemParam as OpenAIResponseFunctionCallOutputItemParam,
)
from openai.types.responses import (
	ResponseFunctionToolCall as OpenAIResponseFunctionToolCall,
)
from openai.types.responses import (
	ResponseFunctionToolCallItem as OpenAIResponseFunctionToolCallItem,
)
from openai.types.responses import (
	ResponseFunctionToolCallParam as OpenAIResponseFunctionToolCallParam,
)
from openai.types.responses import (
	ResponseInputItemParam as OpenAIResponseInputItemParam,
)
from openai.types.responses import (
	ResponseInputParam as OpenAIResponseInputParam,
)
from openai.types.responses import (
	ResponseStreamEvent as OpenAIResponseStreamEvent,
)
from openai.types.responses import (
	ResponseTextConfigParam as OpenAIResponseTextConfigParam,
)
from openai.types.responses import (
	ResponseTextDeltaEvent as OpenAIResponseTextDeltaEvent,
)
from openai.types.responses.response_create_params import (
	ToolChoice as OpenAIResponseToolChoice,
)
from openai.types.responses.response_input_item_param import (
	FunctionCallOutput as OpenAIResponseFunctionCallOutput,
)
from openai.types.shared_params.response_format_json_schema import (
	JSONSchema as OpenAIJSONSchema,
)
from openai.types.shared_params.response_format_json_schema import (
	ResponseFormatJSONSchema as OpenAIResponseFormatJSONSchema,
)


OpenAIChatCompletionFunctionToolCall = ChatCompletionMessageFunctionToolCall
OpenAIChatCompletionFunctionToolCallParam = ChatCompletionMessageFunctionToolCallParam

__all__ = [
	# shared
	"OpenAIChatModel",
	"OpenAIJSONSchema",
	"OpenAIResponseFormatJSONSchema",
	# streaming
	"OpenAIAsyncStream",
	# chat completions
	"OpenAIChatCompletion",
	"OpenAICompletionUsage",
	"OpenAIChatCompletionMessageToolCallUnion",
	"OpenAIChatCompletion",
	"OpenAIChatCompletionChunk",
	"OpenAIChatCompletionMessageParam",
	"OpenAIChatCompletionAssistantMessageParam",
	"OpenAIChatCompletionSystemMessageParam",
	"OpenAIChatCompletionToolMessageParam",
	"OpenAIChatCompletionUserMessageParam",
	"OpenAIChatCompletionFunctionDefinition",
	"OpenAIChatCompletionFunctionToolCall",
	"OpenAIChatCompletionFunctionToolCallParam",
	"OpenAIChatCompletionToolParam",
	"OpenAIChatCompletionToolChoiceOptionParam",
	# responses
	"OpenAIResponse",
	"OpenAIResponsesModel",
	"OpenAIResponseInputParam",
	"OpenAIResponseInputItemParam",
	"OpenAIResponseToolChoice",
	"OpenAIResponseFunctionCallOutput",
	"OpenAIResponseFunctionToolCall",
	"OpenAIResponseFunctionToolCallItem",
	"OpenAIResponseFunctionToolCallParam",
	"OpenAIResponseFunctionCallOutputItemParam",
	"OpenAIResponseFunctionToolParam",
	"OpenAIResponseStreamEvent",
	"OpenAIResponseTextDeltaEvent",
	"OpenAIEasyInputMessageParam",
	"OpenAIResponseTextConfigParam",
	"OpenAIResponseTextJSONSchemaConfigParam",
]
