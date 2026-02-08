"""Plugin schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from api.models.plugin import PluginType
from api.schemas.common import MetadataModel, ORMModel, TimestampedModel
from nokodo_ai.utils.typeid import TypeID


PluginTypeStr = Literal["tool", "filter", "hook"]


class PluginBase(MetadataModel):
	"""Shared plugin fields."""

	name: str = Field(description="unique plugin name/identifier")
	description: str | None = Field(default=None, description="what the plugin does")
	type: PluginType = Field(description="type of plugin: tool, filter, or hook")
	author: str | None = Field(default=None, description="plugin author")
	version: str | None = Field(default=None, description="plugin version")
	source_code: str = Field(
		description="python module source containing the plugin class"
	)


class PluginCreate(PluginBase):
	"""Payload for plugin creation."""

	pass


class PluginUpdate(MetadataModel):
	"""Payload for plugin update."""

	name: str | None = None
	description: str | None = None
	type: PluginType | None = None
	author: str | None = None
	version: str | None = None
	source_code: str | None = None


class Plugin(PluginBase, TimestampedModel):
	"""Response schema."""

	id: TypeID


class PluginInfo(ORMModel):
	"""metadata about an available plugin (native or user-defined)."""

	id: str = Field(description="unique plugin identifier")
	name: str = Field(description="display name of the plugin")
	description: str = Field(description="what the plugin does")
	type: PluginTypeStr = Field(
		description="type of plugin: 'tool', 'filter', or 'hook'"
	)
	is_native: bool = Field(
		default=False,
		description="whether this plugin is built-in (native) or user-defined",
	)
