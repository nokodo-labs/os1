"""Agent schemas."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from api.schemas.common import MetadataModel, TimestampedModel
from nokodo_ai.utils.typeid import TypeID


class AgentBase(MetadataModel):
	"""Shared agent fields."""

	name: str
	description: str | None = None
	system_prompt: str | None = None
	plugin_ids: list[str] = Field(default_factory=list)
	config: dict[str, Any] = Field(default_factory=dict)
	model_id: TypeID | None = None
	profile_image_file_id: TypeID | None = None
	profile_image_url: str | None = None


class AgentCreate(AgentBase):
	"""Payload for agent creation."""

	pass


class AgentUpdate(MetadataModel):
	"""Payload for agent update."""

	name: str | None = None
	description: str | None = None
	system_prompt: str | None = None
	plugin_ids: list[str] | None = None
	config: dict[str, Any] | None = None
	model_id: TypeID | None = None
	profile_image_file_id: TypeID | None = None
	profile_image_url: str | None = None


class Agent(AgentBase, TimestampedModel):
	"""Agent response schema — returns IDs only, no hydrated relationships."""

	id: TypeID
