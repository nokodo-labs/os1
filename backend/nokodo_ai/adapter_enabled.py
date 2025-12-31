"""shared adapter-enabled model behavior."""

from __future__ import annotations

from pydantic import ConfigDict, Field

from nokodo_ai.base import Base


def split_model_identifier(
	model: str,
	*,
	default_provider: str = "openai",
) -> tuple[str, str | None, str]:
	"""split a model identifier into (provider, api, model_name)."""
	if ":" in model:
		provider_part, model_name = model.split(":", 1)
	else:
		provider_part = default_provider
		model_name = model

	if "." in provider_part:
		provider, api = provider_part.split(".", 1)
	else:
		provider = provider_part
		api = None

	return provider, api, model_name


class AdapterEnabledMixin[AdapterType](Base):
	"""base model for interfaces that resolve an adapter.

	the 'model' input string is transient and parsed into provider/api/model_name.
	"""

	provider: str | None = Field(default=None, description="resolved provider name")
	api: str | None = Field(default=None, description="resolved api variant")
	model_name: str = Field(..., description="resolved model name")

	adapter: AdapterType = Field(
		description="resolved adapter instance",
	)

	model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)
