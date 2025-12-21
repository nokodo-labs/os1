"""base adapter infrastructure shared by all adapters."""

from __future__ import annotations

from abc import ABC


class BaseAdapter(ABC):
	"""base infrastructure all adapters share.

	provides common functionality like configuration, logging, and lifecycle management.
	concrete provider bases (e.g., BaseOpenAIAdapter) inherit from this.
	"""

	pass
