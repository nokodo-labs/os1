"""content part schemas for messages.

These models define the structure of message content parts stored in the ORM
and are designed to be compatible with SDK content parts via Pydantic validation.

The key design principle:
- File references are stored in `metadata["file_id"]` for ORM persistence
- `url`/`base64` are used for SDK execution (actual data for LLM calls)
- The API layer resolves file_id → url when sending to SDK
- The API layer persists url/base64 → File record when receiving from SDK
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter


class BaseContentPart(BaseModel):
	"""base class for all content parts."""

	model_config = ConfigDict(extra="ignore")

	metadata: dict | None = None


class TextContent(BaseContentPart):
	"""plain text content."""

	type: Literal["text"] = "text"
	text: str = ""


class JsonContent(BaseContentPart):
	"""structured JSON content (for structured outputs)."""

	type: Literal["json"] = "json"
	data: dict | None = None


class FileContent(BaseContentPart):
	"""file attachment content.

	for ORM storage: metadata["file_id"] is set, url/base64 may be null
	for SDK execution: url or base64 must be populated (resolved from file_id)
	for external files: url is set, no file_id in metadata
	"""

	type: Literal["file"] = "file"
	url: str | None = None
	base64: str | None = None
	filename: str | None = None
	media_type: str | None = None


class ImageContent(BaseContentPart):
	"""image content part.

	this mirrors FileContent fields but uses a distinct content type.
	"""

	type: Literal["image"] = "image"
	url: str | None = None
	base64: str | None = None
	filename: str | None = None
	media_type: str | None = None


class RefusalContent(BaseContentPart):
	"""refusal content (when model refuses to respond)."""

	type: Literal["refusal"] = "refusal"
	reason: str = ""


ContentPart = Annotated[
	TextContent | JsonContent | ImageContent | FileContent | RefusalContent,
	Field(discriminator="type"),
]

# Subset allowed for user messages
UserContentPart = Annotated[
	TextContent | ImageContent | FileContent,
	Field(discriminator="type"),
]

# Subset allowed for system messages
SystemContentPart = Annotated[
	TextContent,
	Field(discriminator="type"),
]

# Type adapter for validating content parts from dicts
ContentPartAdapter = TypeAdapter(ContentPart)
