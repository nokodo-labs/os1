"""raw MCP adapter errors."""


class MCPError(RuntimeError):
	"""base MCP adapter error."""


class MCPDependencyError(MCPError):
	"""raised when the optional MCP dependency is unavailable."""


class MCPUnsupportedTransportError(MCPError):
	"""raised when an MCP transport is not implemented yet."""
