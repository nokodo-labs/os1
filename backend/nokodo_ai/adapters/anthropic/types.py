"""centralized Anthropic SDK types for nokodo_ai adapters.

the goal is to keep all Anthropic SDK imports in one place so adapter modules
stay small and type check cleanly.
"""

from __future__ import annotations

from anthropic.types import (
	Base64ImageSourceParam as AnthropicBase64ImageSourceParam,
)
from anthropic.types import (
	ContentBlockParam as AnthropicContentBlockParam,
)
from anthropic.types import (
	ImageBlockParam as AnthropicImageBlockParam,
)
from anthropic.types import (
	ThinkingConfigDisabledParam as AnthropicThinkingConfigDisabledParam,
)
from anthropic.types import (
	ThinkingConfigEnabledParam as AnthropicThinkingConfigEnabledParam,
)
from anthropic.types import (
	ThinkingConfigParam as AnthropicThinkingConfigParam,
)
from anthropic.types import (
	URLImageSourceParam as AnthropicURLImageSourceParam,
)
from anthropic.types.input_json_delta import (
	InputJSONDelta as AnthropicInputJSONDelta,
)
from anthropic.types.message_param import (
	MessageParam as AnthropicMessageParam,
)
from anthropic.types.raw_content_block_delta_event import (
	RawContentBlockDeltaEvent as AnthropicRawContentBlockDeltaEvent,
)
from anthropic.types.raw_content_block_start_event import (
	RawContentBlockStartEvent as AnthropicRawContentBlockStartEvent,
)
from anthropic.types.raw_content_block_stop_event import (
	RawContentBlockStopEvent as AnthropicRawContentBlockStopEvent,
)
from anthropic.types.raw_message_start_event import (
	RawMessageStartEvent as AnthropicRawMessageStartEvent,
)
from anthropic.types.text_block import (
	TextBlock as AnthropicTextBlock,
)
from anthropic.types.text_block_param import (
	TextBlockParam as AnthropicTextBlockParam,
)
from anthropic.types.text_delta import (
	TextDelta as AnthropicTextDelta,
)
from anthropic.types.tool_choice_any_param import (
	ToolChoiceAnyParam as AnthropicToolChoiceAnyParam,
)
from anthropic.types.tool_choice_auto_param import (
	ToolChoiceAutoParam as AnthropicToolChoiceAutoParam,
)
from anthropic.types.tool_choice_none_param import (
	ToolChoiceNoneParam as AnthropicToolChoiceNoneParam,
)
from anthropic.types.tool_choice_tool_param import (
	ToolChoiceToolParam as AnthropicToolChoiceToolParam,
)
from anthropic.types.tool_param import (
	ToolParam as AnthropicToolParam,
)
from anthropic.types.tool_result_block_param import (
	ToolResultBlockParam as AnthropicToolResultBlockParam,
)
from anthropic.types.tool_use_block import (
	ToolUseBlock as AnthropicToolUseBlock,
)
from anthropic.types.tool_use_block_param import (
	ToolUseBlockParam as AnthropicToolUseBlockParam,
)


__all__ = [
	"AnthropicBase64ImageSourceParam",
	"AnthropicContentBlockParam",
	"AnthropicImageBlockParam",
	"AnthropicURLImageSourceParam",
	"AnthropicInputJSONDelta",
	"AnthropicMessageParam",
	"AnthropicRawContentBlockDeltaEvent",
	"AnthropicRawContentBlockStartEvent",
	"AnthropicRawContentBlockStopEvent",
	"AnthropicRawMessageStartEvent",
	"AnthropicTextBlock",
	"AnthropicTextBlockParam",
	"AnthropicTextDelta",
	"AnthropicToolChoice",
	"AnthropicToolChoiceAnyParam",
	"AnthropicToolChoiceAutoParam",
	"AnthropicToolChoiceNoneParam",
	"AnthropicToolChoiceToolParam",
	"AnthropicToolParam",
	"AnthropicToolResultBlockParam",
	"AnthropicToolUseBlock",
	"AnthropicToolUseBlockParam",
	"AnthropicThinkingConfigParam",
	"AnthropicThinkingConfigEnabledParam",
	"AnthropicThinkingConfigDisabledParam",
]

type AnthropicToolChoice = (
	AnthropicToolChoiceAutoParam
	| AnthropicToolChoiceAnyParam
	| AnthropicToolChoiceNoneParam
	| AnthropicToolChoiceToolParam
)
