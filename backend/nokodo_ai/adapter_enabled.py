"""shared adapter-enabled model behavior."""

from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import ConfigDict, Field, PrivateAttr, model_validator

from nokodo_ai.base import Base


def split_model_identifier(
	model: str,
	*,
	default_provider: str,
) -> tuple[str, str | None, str]:
	"""split a model identifier into (provider, variant, model_name)."""
	if ":" in model:
		provider_part, model_name = model.split(":", 1)
	else:
		provider_part = default_provider
		model_name = model

	if "." in provider_part:
		provider, variant = provider_part.split(".", 1)
	else:
		provider = provider_part
		variant = None

	return provider, variant, model_name


class AdapterEnabledMixin[AdapterType](Base, ABC):
	"""base model for interfaces that can take an adapter or resolve one from
	`model`.
	"""

	model: str = Field(
		...,
		description="model identifier with optional provider and variant prefix",
	)

	model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

	adapter: AdapterType | None = Field(
		default=None,
		exclude=True,
		description="explicit adapter instance (overrides auto-resolution)",
	)
	_adapter_resolved: AdapterType = PrivateAttr()

	@model_validator(mode="after")
	def _resolve_adapter_eagerly(self) -> AdapterEnabledMixin[AdapterType]:
		if self.adapter is not None:
			self._adapter_resolved = self.adapter
		else:
			self._adapter_resolved = self._resolve_adapter_from_model(self.model)
		return self

	@abstractmethod
	def _resolve_adapter_from_model(self, model: str) -> AdapterType:
		raise NotImplementedError
