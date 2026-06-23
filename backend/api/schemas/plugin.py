"""plugin schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from api.models.plugin import PluginType
from api.schemas.common import (
	MISSING,
	MetadataModel,
	MetadataUpdateModel,
	MissingType,
	ORMModel,
	TimestampedModel,
)
from nokodo_ai.utils.typeid import TypeID


PluginTypeStr = Literal["tool", "filter", "hook"]
PluginSourceStr = Literal["native", "external", "custom"]
type PluginTypeFilter = PluginTypeStr | None
type PluginSourceFilter = PluginSourceStr | None


class PluginListFilters(BaseModel):
	"""filters for listing plugins."""

	plugin_type: PluginTypeFilter = None
	source: PluginSourceFilter = None


class PluginBase(MetadataModel):
	"""shared plugin fields."""

	name: str = Field(description="unique plugin name/identifier")
	description: str | None = Field(default=None, description="what the plugin does")
	type: PluginType = Field(description="type of plugin: tool, filter, or hook")
	author: str | None = Field(default=None, description="plugin author")
	version: str | None = Field(default=None, description="plugin version")
	source_code: str = Field(
		description="python module source containing the plugin class"
	)


class PluginCreate(PluginBase):
	"""payload for plugin creation."""

	pass


class PluginUpdate(MetadataUpdateModel):
	"""payload for plugin update."""

	name: str | MissingType = MISSING
	description: str | None | MissingType = MISSING
	type: PluginType | MissingType = MISSING
	author: str | None | MissingType = MISSING
	version: str | None | MissingType = MISSING
	source_code: str | MissingType = MISSING


class Plugin(PluginBase, TimestampedModel):
	"""response schema."""

	id: TypeID


class PluginInfo(ORMModel):
	"""metadata about a plugin catalog item."""

	id: str = Field(description="unique plugin identifier")
	name: str = Field(description="display name of the plugin")
	description: str = Field(description="what the plugin does")
	source: PluginSourceStr = Field(description="where this plugin comes from")
	type: PluginTypeStr = Field(
		description="type of plugin: 'tool', 'filter', or 'hook'"
	)
