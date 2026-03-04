"""tool result truncation filter.

caps individual tool results that are disproportionately large relative
to the context budget. this prevents a single tool call (e.g. a web
scrape, code search, or large file read) from consuming the entire
context window.

this filter is always active and runs before other filters. it does
not lose information permanently -- the full tool result is in the DB.
it only trims what gets sent to the model for the current inference.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from pydantic import Field

from api.settings.settings import settings as app_settings
from api.v1.service.chat.filters.base import Filter
from nokodo_ai.messages import ToolMessage as SDKToolMessage
from nokodo_ai.threads import Thread as SDKThread
from nokodo_ai.utils.tokens import (
	CHARS_PER_TOKEN,
	SAFETY_MARGIN,
	compute_available_budget,
	estimate_tokens,
)


if TYPE_CHECKING:
	from api.v1.service.chat.context import AppContext

logger = logging.getLogger(__name__)

# notice appended to truncated tool results
_TRUNCATION_NOTICE = (
	"\n\n[... truncated: {original_chars} chars total, "
	"{removed_chars} chars removed to fit context budget ...]"
)


def _compute_char_limit(context_window: int | None) -> int:
	"""compute the character limit for a single tool result.

	applies both the budget-relative share and the absolute hard cap,
	returning the stricter of the two.
	"""
	ws = app_settings.ai.windowing

	# hard ceiling in chars (always applied)
	hard_cap = ws.tool_result_hard_cap

	if context_window is None:
		# no model context window known -- rely on hard cap only
		return hard_cap

	# budget-relative limit: convert token share to approximate chars
	budget_tokens = compute_available_budget(
		context_window,
		response_headroom=ws.response_headroom,
	)
	share_tokens = int(budget_tokens * ws.tool_result_max_share)
	# convert tokens -> chars (inverse of the estimation heuristic)
	share_chars = int(share_tokens * CHARS_PER_TOKEN / SAFETY_MARGIN)

	return min(share_chars, hard_cap)


def _truncate_text(text: str, char_limit: int) -> str:
	"""truncate text to char_limit, appending a notice."""
	if len(text) <= char_limit:
		return text

	original_len = len(text)
	# reserve space for the notice itself
	notice = _TRUNCATION_NOTICE.format(
		original_chars=original_len,
		removed_chars=original_len - char_limit,
	)
	keep = max(char_limit - len(notice), 0)
	return text[:keep] + notice


class ToolResultTruncationFilter(Filter):
	"""truncates oversized tool results to fit the context budget.

	always runs, independent of windowing enabled/disabled.
	the tool_result_hard_cap provides a safety floor even when
	no model context_window is available.
	"""

	name: str = Field(default="tool_result_truncation")
	description: str = Field(
		default="truncates oversized tool results to fit context budget"
	)

	async def process(
		self,
		thread: SDKThread,
		app_context: AppContext | None,
	) -> SDKThread:
		context_window = app_context.context_window if app_context else None
		char_limit = _compute_char_limit(context_window)
		messages = list(thread.messages)
		changed = False

		for idx, msg in enumerate(messages):
			if not isinstance(msg, SDKToolMessage):
				continue

			output = msg.tool_output
			if not output or len(output) <= char_limit:
				continue

			original_tokens = estimate_tokens(output)
			truncated = _truncate_text(output, char_limit)
			messages[idx] = msg.model_copy(update={"tool_output": truncated})
			changed = True

			logger.info(
				"truncated tool result: %d -> %d chars (~%d -> ~%d tokens)",
				len(output),
				len(truncated),
				original_tokens,
				estimate_tokens(truncated),
			)

		if not changed:
			return thread

		return thread.model_copy(update={"messages": messages})
