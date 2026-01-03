"""base hook class for sdk-compatible hooks."""

from __future__ import annotations

from api.v1.service.chat.context import AppContext
from nokodo_ai.hooks import Hook as SDKHook


class Hook(SDKHook[AppContext]):
	"""sdk Hook specialized to AppContext."""

	pass
