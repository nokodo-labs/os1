"""Agent schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from api.models.agent import AgentVisibility
from api.schemas.common import MetadataModel
from api.schemas.model import Model


class AgentBase(MetadataModel):
	"""Shared agent fields."""

	name: str
	description: str | None = None
	system_prompt: str | None = None
	visibility: AgentVisibility = AgentVisibility.PUBLIC
	tool_ids: list[str] = Field(default_factory=list)
	config: dict[str, Any] = Field(default_factory=dict)
	model_id: str | None = None


class AgentCreate(AgentBase):
	"""Payload for agent creation."""

	pass


class AgentUpdate(MetadataModel):
	"""Payload for agent update."""

	name: str | None = None
	description: str | None = None
	system_prompt: str | None = None
	visibility: AgentVisibility | None = None
	tool_ids: list[str] | None = None
	config: dict[str, Any] | None = None
	model_id: str | None = None


class Agent(AgentBase):
	"""Response schema."""

	id: str
	created_at: datetime
	updated_at: datetime
	model: Model | None = None
