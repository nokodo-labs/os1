"""shared adapter-enabled model behavior."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, ClassVar, Self

from pydantic import ConfigDict, Field, model_validator

from .adapters.base.adapter import BaseAdapter
from .base import Base


class AdapterEnabledBase[AdapterType: BaseAdapter](Base):
	"""base model for interfaces that resolve an adapter.

	subclasses must define their own identifier field (e.g., model_name, collection)
	and set the _adapter_resolver class variable.

	usage:
		ChatModel.model_validate({
			"model_name": "gpt-4o",
			"adapter": {"type": "openai", "api_key": "..."}
		})

	the adapter type can be a shorthand provider name (e.g., "openai") which
	will be resolved to the full adapter type (e.g., "openai.chat_completions").
	"""

	_adapter_resolver: ClassVar[Callable[[str, str | None], str | None]]
	adapter: AdapterType = Field(
		description="resolved adapter instance",
	)
	model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

	@classmethod
	def _create(
		cls,
		identifier: tuple[str, str],
		adapter: AdapterType | dict[str, Any],
		**fields: Any,
	) -> Self:
		"""shared implementation for concrete `.create(...)` constructors"""
		data: dict[str, Any] = {
			identifier[0]: identifier[1],
			"adapter": adapter,
			**fields,
		}
		return cls.model_validate(data)

	@model_validator(mode="before")
	@classmethod
	def _resolve_adapter_shorthand(cls, data: Any) -> Any:
		"""resolve adapter type shorthand to full qualified type.

		allows users to write:
			{"adapter": {"type": "openai", "api_key": "..."}}
		instead of:
			{"adapter": {"type": "openai.chat_completions", "api_key": "..."}}
		"""
		if not isinstance(data, dict):
			return data

		adapter = data.get("adapter")
		if not isinstance(adapter, dict):
			return data

		type_value = adapter.get("type")
		if not isinstance(type_value, str) or type_value == "":
			return data

		# already fully qualified (contains a dot)
		if "." in type_value:
			return data

		# shorthand: resolve "openai" -> "openai.chat_completions"
		provider = type_value
		adapter_type = cls._adapter_resolver(provider, None)
		if adapter_type is None:
			raise ValueError(f"unknown provider: {provider}")

		adapter["type"] = adapter_type

		return data

	async def __aenter__(self) -> AdapterEnabledBase[AdapterType]:
		return self

	async def __aexit__(self, exc_type, exc_value, traceback) -> None:
		await self.close()

	async def close(self) -> None:
		"""close resources held by the adapter."""
		await self.adapter.close()
