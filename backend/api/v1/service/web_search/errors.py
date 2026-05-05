"""web search service errors."""

from __future__ import annotations


class WebSearchError(Exception):
	"""raised when web search or web loading fails."""


__all__ = ["WebSearchError"]
