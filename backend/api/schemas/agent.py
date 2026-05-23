"""agent schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from api.schemas.common import (
	MISSING,
	MetadataModel,
	MetadataUpdateModel,
	MissingType,
	TimestampedModel,
)
from api.schemas.sorting import CommonSortBy
from nokodo_ai.utils.typeid import TypeID


type AgentSortBy = CommonSortBy | Literal["name"]

DEFAULT_AGENT_PLUGIN_IDS: tuple[str, ...] = (
	"chat_context",
	"attachment_decay",
	"file_resolve",
	"citation_index",
	"context_compaction",
)


def default_agent_plugin_ids() -> list[str]:
	return list(DEFAULT_AGENT_PLUGIN_IDS)


class AgentListFilters(BaseModel):
	"""filters for listing agents."""

	q: str | None = Field(default=None, min_length=1, max_length=500)


# typed config sub-models
# storage stays as JSONB so the admin console can persist arbitrary
# (unknown keys round-trip via ``extra``).


class SteeringFeature(BaseModel):
	"""runtime-steering toggle for an agent."""

	model_config = ConfigDict(extra="allow")
	enabled: bool = True


class AgentFeatures(BaseModel):
	"""per-agent feature toggles."""

	model_config = ConfigDict(extra="allow")
	steering: SteeringFeature = Field(default_factory=SteeringFeature)


class AgentConfig(BaseModel):
	"""top-level typed view of ``agent.config``."""

	model_config = ConfigDict(extra="allow")
	features: AgentFeatures = Field(default_factory=AgentFeatures)


# agent schemas


class AgentBase(MetadataModel):
	"""shared agent fields."""

	name: str
	description: str | None = None
	system_prompt: str | None = None
	plugin_ids: list[str] = Field(default_factory=default_agent_plugin_ids)
	config: AgentConfig = Field(default_factory=AgentConfig)
	model_id: TypeID | None = None
	profile_image_file_id: TypeID | None = None
	profile_image_url: str | None = None


class AgentCreate(AgentBase):
	"""payload for agent creation."""

	pass


class AgentUpdate(MetadataUpdateModel):
	"""payload for agent update."""

	name: str | MissingType = MISSING
	description: str | None | MissingType = MISSING
	system_prompt: str | None | MissingType = MISSING
	plugin_ids: list[str] | MissingType = MISSING
	config: AgentConfig | MissingType = MISSING
	model_id: TypeID | None | MissingType = MISSING
	profile_image_file_id: TypeID | None | MissingType = MISSING
	profile_image_url: str | None | MissingType = MISSING


class Agent(AgentBase, TimestampedModel):
	"""agent response schema - returns IDs only, no hydrated relationships."""

	id: TypeID
