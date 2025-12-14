"""System schemas."""

from pydantic import BaseModel


class RuntimeConfigOut(BaseModel):
	"""Runtime configuration values safe for clients."""

	frontend_origin: str | None = None
	cdn_origin: str | None = None
