"""base filter class for sdk-compatible filters."""

from __future__ import annotations

from api.v1.service.chat.context import AppContext
from nokodo_ai.filters import Filter as SDKFilter


class Filter(SDKFilter[AppContext]):
	"""sdk Filter specialized to AppContext."""

	pass
