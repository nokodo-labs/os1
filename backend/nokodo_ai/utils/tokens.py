"""pure token estimation and context budget utilities.

contains ONLY pure functions with no runtime imports from the SDK.
message-aware estimation lives in nokodo_ai.token_estimation.
"""

from __future__ import annotations

from math import ceil


# -- constants --

# approximate tokens-per-char ratio. english text averages ~4 chars per
# token across most LLM tokenizers (BPE). multiplied by a safety margin
# to avoid underestimates on structured/code content.
CHARS_PER_TOKEN: float = 4.0

# safety margin applied to heuristic estimates. compensates for the
# chars/4 heuristic undercounting on non-english, structured, or
# code-heavy content.
SAFETY_MARGIN: float = 1.2

# fallback context window when model metadata is unavailable.
DEFAULT_CONTEXT_WINDOW: int = 128_000

# tokens reserved for the model's response.
DEFAULT_RESPONSE_HEADROOM: int = 4096


# -- estimation --


def estimate_tokens(text: str) -> int:
	"""estimate token count for a text string.

	uses a chars/4 heuristic with a safety margin. this is fast and
	allocation-free, accurate within ~20% for english text.

	even copilot chat uses openai's o200k tokenizer for non-openai
	models (claude, gemini) -- so any tokenizer is an approximation
	across providers. this heuristic is the pragmatic choice.
	"""
	if not text:
		return 0
	return ceil(len(text) / CHARS_PER_TOKEN * SAFETY_MARGIN)


def compute_available_budget(
	context_window: int | None,
	system_prompt_tokens: int = 0,
	summary_tokens: int = 0,
	response_headroom: int = DEFAULT_RESPONSE_HEADROOM,
) -> int:
	"""compute available token budget for conversation history.

	subtracts system prompt, existing summaries, and response headroom
	from the model's context window.

	returns the remaining tokens available for unsummarized messages.
	"""
	window = context_window or DEFAULT_CONTEXT_WINDOW
	available = window - system_prompt_tokens - summary_tokens - response_headroom
	# floor at 0 -- if overhead exceeds the window, nothing fits
	return max(available, 0)
