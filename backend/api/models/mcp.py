"""MCP server and discovered capability models."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.models.base import TYPEID_LENGTH, Base, StringEnum
from api.models.mixins import (
	MetadataJSONMixin,
	TimestampMixin,
	TypeIDPrimaryKeyMixin,
)
from nokodo_ai.types.json import JSONObject


if TYPE_CHECKING:
	from api.models.user import User


class MCPServerScope(StrEnum):
	"""owner scope for an MCP server."""

	GLOBAL = "global"
	USER = "user"


class MCPTransport(StrEnum):
	"""supported MCP transport types."""

	STREAMABLE_HTTP = "streamable_http"
	SSE = "sse"
	STDIO = "stdio"


class MCPAuthType(StrEnum):
	"""supported MCP authentication modes."""

	NONE = "none"
	BEARER = "bearer"
	OAUTH_2_1 = "oauth_2.1"


class MCPServerStatus(StrEnum):
	"""cached MCP server health state."""

	DISCONNECTED = "disconnected"
	READY = "ready"
	ERROR = "error"


def default_mcp_capabilities() -> JSONObject:
	"""default enabled MCP surface for a server."""
	return {
		"tools": True,
		"resources": False,
		"prompts": False,
		"sampling": False,
	}


class MCPServer(TypeIDPrimaryKeyMixin, TimestampMixin, MetadataJSONMixin, Base):
	"""persisted MCP server connection."""

	__tablename__ = "mcp_servers"
	__typeid_prefix__ = "mcpsrv"

	name: Mapped[str] = mapped_column(String(120))
	description: Mapped[str | None] = mapped_column(Text())
	scope: Mapped[MCPServerScope] = mapped_column(
		StringEnum(MCPServerScope),
		default=MCPServerScope.GLOBAL,
		index=True,
	)
	owner_user_id: Mapped[str | None] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("users.id", ondelete="CASCADE"),
		index=True,
	)
	transport: Mapped[MCPTransport] = mapped_column(
		StringEnum(MCPTransport),
		default=MCPTransport.STREAMABLE_HTTP,
	)
	url: Mapped[str | None] = mapped_column(String(2048))
	command: Mapped[str | None] = mapped_column(String(1024))
	args: Mapped[list[str]] = mapped_column(JSONB, default=list)
	env: Mapped[JSONObject] = mapped_column(JSONB, default=dict)
	auth_type: Mapped[MCPAuthType] = mapped_column(
		StringEnum(MCPAuthType),
		default=MCPAuthType.NONE,
	)
	headers: Mapped[JSONObject] = mapped_column(JSONB, default=dict)
	encrypted_access_token: Mapped[str | None] = mapped_column(String(4096))
	enabled: Mapped[bool] = mapped_column(default=True, index=True)
	capabilities: Mapped[JSONObject] = mapped_column(
		JSONB,
		default=default_mcp_capabilities,
	)
	config: Mapped[JSONObject] = mapped_column(JSONB, default=dict)
	status: Mapped[MCPServerStatus] = mapped_column(
		StringEnum(MCPServerStatus),
		default=MCPServerStatus.DISCONNECTED,
	)
	last_discovered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
	last_error: Mapped[str | None] = mapped_column(Text())
	discovered_tools: Mapped[list[JSONObject]] = mapped_column(JSONB, default=list)
	discovered_resources: Mapped[list[JSONObject]] = mapped_column(JSONB, default=list)
	discovered_prompts: Mapped[list[JSONObject]] = mapped_column(JSONB, default=list)

	owner_user: Mapped[User | None] = relationship("User")

	__table_args__ = (
		Index(
			"uq_mcp_servers_global_name",
			"name",
			unique=True,
			postgresql_where=text("scope = 'global'"),
		),
		Index(
			"uq_mcp_servers_user_name",
			"owner_user_id",
			"name",
			unique=True,
			postgresql_where=text("scope = 'user'"),
		),
	)

	@property
	def has_credentials(self) -> bool:
		"""whether this server has stored credentials."""
		return bool(self.encrypted_access_token)
