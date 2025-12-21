"""centralized OpenAI SDK types for nokodo_ai adapters.

the goal is to keep all OpenAI SDK imports in one place so adapter modules
stay small and type check cleanly.
"""

from __future__ import annotations

from openai._streaming import AsyncStream as OpenAIAsyncStream
from openai.types.chat import (
	ChatCompletion as OpenAIChatCompletion,
)
from openai.types.chat import (
	ChatCompletionChunk as OpenAIChatCompletionChunk,
)
from openai.types.chat import (
	ChatCompletionMessageParam as OpenAIChatCompletionMessageParam,
)
from openai.types.chat.chat_completion_assistant_message_param import (
	ChatCompletionAssistantMessageParam as OpenAIChatCompletionAssistantMessageParam,
)
from openai.types.chat.chat_completion_message_function_tool_call import (
	ChatCompletionMessageFunctionToolCall,
)
from openai.types.chat.chat_completion_message_function_tool_call_param import (
	ChatCompletionMessageFunctionToolCallParam,
)
from openai.types.chat.chat_completion_system_message_param import (
	ChatCompletionSystemMessageParam as OpenAIChatCompletionSystemMessageParam,
)
from openai.types.chat.chat_completion_tool_message_param import (
	ChatCompletionToolMessageParam as OpenAIChatCompletionToolMessageParam,
)
from openai.types.chat.chat_completion_user_message_param import (
	ChatCompletionUserMessageParam as OpenAIChatCompletionUserMessageParam,
)
from openai.types.responses import (
	Response as OpenAIResponse,
)
from openai.types.responses import (
	ResponseInputParam as OpenAIResponseInputParam,
)
from openai.types.responses.easy_input_message_param import (
	EasyInputMessageParam as OpenAIEasyInputMessageParam,
)
from openai.types.responses.response_stream_event import (
	ResponseStreamEvent as OpenAIResponseStreamEvent,
)
from openai.types.responses.response_text_delta_event import (
	ResponseTextDeltaEvent as OpenAIResponseTextDeltaEvent,
)


OpenAIChatCompletionFunctionToolCall = ChatCompletionMessageFunctionToolCall
OpenAIChatCompletionFunctionToolCallParam = ChatCompletionMessageFunctionToolCallParam

__all__ = [
	# streaming
	"OpenAIAsyncStream",
	# chat completions
	"OpenAIChatCompletion",
	"OpenAIChatCompletionChunk",
	"OpenAIChatCompletionMessageParam",
	"OpenAIChatCompletionAssistantMessageParam",
	"OpenAIChatCompletionSystemMessageParam",
	"OpenAIChatCompletionToolMessageParam",
	"OpenAIChatCompletionUserMessageParam",
	"OpenAIChatCompletionFunctionToolCall",
	"OpenAIChatCompletionFunctionToolCallParam",
	# responses
	"OpenAIResponse",
	"OpenAIResponseInputParam",
	"OpenAIResponseStreamEvent",
	"OpenAIResponseTextDeltaEvent",
	"OpenAIEasyInputMessageParam",
]
