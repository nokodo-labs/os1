"""citation schemas.

citations are reference-based: markers like [n] live in the message text,
and full citation data lives in message.citations[]. the ``source_type``
field discriminates what kind of resource is being cited; ``source_id``
carries the actual reference value (URL, TypeID, etc.).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import Field

from api.schemas.common import ORMModel


class CitationSource(StrEnum):
	"""what kind of resource a citation points to."""

	URL = "url"
	FILE = "file"
	NOTE = "note"
	MEMORY = "memory"
	THREAD = "thread"
	TOOL_RESULT = "tool_result"


class Citation(ORMModel):
	"""a single citation reference within a message.

	``index`` is the branch-cumulative number used as the [n] marker.
	``source_type`` discriminates the resource kind.
	``source_id`` is the source-specific value (URL, TypeID string, etc.).
	"""

	index: Annotated[
		int,
		Field(ge=1, description="branch-cumulative citation number"),
	]
	source_type: CitationSource
	source_id: str = Field(
		description="source-specific value: URL string, TypeID, tool_call_id, etc.",
	)
	title: str | None = None
