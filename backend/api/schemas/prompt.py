"""prompt schemas."""

from __future__ import annotations

import re

from pydantic import Field, field_validator

from api.schemas.common import MetadataModel, TimestampedModel


_COMMAND_PATTERN = r"^[a-zA-Z0-9][a-zA-Z0-9-_]*$"


def _normalize_command(command: str) -> str:
	command = command.strip()
	if not command:
		return command
	# strip any leading slash (legacy format)
	command = command.lstrip("/")
	# auto-convert spaces to dashes
	command = command.replace(" ", "-")
	return command


class PromptBase(MetadataModel):
	"""shared prompt fields."""

	command: str = Field(..., description="prompt identifier, e.g. 'my-prompt'")
	content: str

	@field_validator("command")
	@classmethod
	def _validate_command(cls, value: str) -> str:
		normalized = _normalize_command(value)
		# keep validation local to this module; the service layer enforces uniqueness.
		if not re.match(_COMMAND_PATTERN, normalized):
			raise ValueError(
				"command must look like 'my-prompt' "
				"(letters, numbers, '-', '_' only; no leading slash)"
			)
		return normalized


class PromptCreate(PromptBase):
	"""payload for prompt creation."""

	pass


class PromptUpdate(MetadataModel):
	"""payload for prompt update."""

	command: str | None = None
	content: str | None = None

	@field_validator("command")
	@classmethod
	def _validate_command(cls, value: str | None) -> str | None:
		if value is None:
			return None
		# reuse the base validator logic
		return PromptBase._validate_command(value)


class Prompt(PromptBase, TimestampedModel):
	"""response schema."""

	id: str
