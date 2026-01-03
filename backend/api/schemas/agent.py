"""Agent schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from api.models.agent import AgentVisibility
from api.schemas.common import MetadataModel
from api.schemas.model import Model
from nokodo_ai.utils.typeid import TypeID


class AgentBase(MetadataModel):
	"""Shared agent fields."""

	name: str
	description: str | None = None
	system_prompt: str | None = None
	visibility: AgentVisibility = AgentVisibility.PUBLIC
	plugin_ids: list[TypeID] = Field(default_factory=list)
	config: dict[str, Any] = Field(default_factory=dict)
	model_id: TypeID | None = None


class AgentCreate(AgentBase):
	"""Payload for agent creation."""

	pass


class AgentUpdate(MetadataModel):
	"""Payload for agent update."""

	name: str | None = None
	description: str | None = None
	system_prompt: str | None = None
	visibility: AgentVisibility | None = None
	plugin_ids: list[TypeID] | None = None
	config: dict[str, Any] | None = None
	model_id: TypeID | None = None


class Agent(AgentBase):
	"""Response schema."""

	id: TypeID
	created_at: datetime
	updated_at: datetime
	model: Model | None = None
