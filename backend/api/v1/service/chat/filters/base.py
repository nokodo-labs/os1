"""base filter class for sdk-compatible filters."""

from __future__ import annotations

from api.v1.service.chat.context import AppContext
from nokodo_ai.filters import Filter as SDKFilter
from nokodo_ai.messages import SystemMessage as SDKSystemMessage
from nokodo_ai.threads import Thread as SDKThread


class Filter(SDKFilter[AppContext]):
	"""sdk Filter specialized to AppContext."""

	@staticmethod
	def _replace_sentinel(
		thread: SDKThread,
		sentinel: str,
		replacement: str,
	) -> bool:
		"""replace a sentinel string in the system message, in-place.

		returns True if the sentinel was found and replaced, False otherwise.
		"""
		for i, m in enumerate(thread.messages):
			if not isinstance(m, SDKSystemMessage):
				continue
			text = m.text
			if not text or sentinel not in text:
				continue
			thread.messages[i] = SDKSystemMessage.from_text(
				text.replace(sentinel, replacement)
			)
			return True
		return False
