"""high-level content loading surface."""

from __future__ import annotations

from typing import ClassVar

from pydantic import model_validator

from .adapter_enabled import AdapterEnabledBase, AdapterResolver
from .adapters.base.loaders import (
	BaseLoaderAdapter,
	File,
	LoaderConfig,
	LoaderContext,
	Text,
	TextFormatPreference,
)
from .adapters.loaders import (
	LoaderAdapter,
	resolve_loader_adapter,
)
from .chat_models import ChatModel


class Loader(AdapterEnabledBase[BaseLoaderAdapter]):
	"""content loader that delegates to a concrete adapter."""

	adapter: LoaderAdapter
	text_format: TextFormatPreference = "auto"
	chat_model: ChatModel | None = None

	_adapter_resolver: ClassVar[AdapterResolver] = resolve_loader_adapter

	@classmethod
	def create(
		cls,
		adapter: str | LoaderAdapter | dict[str, object],
		**fields: object,
	) -> Loader:
		"""create a loader with adapter configuration."""
		return cls.model_validate({"adapter": adapter, **fields})

	@model_validator(mode="before")
	@classmethod
	def _resolve_loader_adapter_config(cls, data: dict[str, object]) -> object:
		if not isinstance(data, dict):
			return data
		adapter = data.get("adapter")
		if not isinstance(adapter, str):
			return data
		adapter_type = cls._adapter_type_from_string(adapter)
		return {**data, "adapter": {"type": adapter_type}}

	@classmethod
	def _adapter_type_from_string(cls, adapter: str) -> str:
		if "." in adapter:
			return adapter
		resolved = cls._adapter_resolver(adapter, None)
		if resolved is None:
			raise ValueError(f"unknown loader adapter: {adapter}")
		return resolved

	async def load(
		self,
		file: File,
		context: LoaderContext | None = None,
		config: LoaderConfig | None = None,
	) -> Text:
		context = context or LoaderContext(chat_model=self.chat_model)
		config = config or LoaderConfig(text_format=self.text_format)
		return await self.adapter.load(file, context, config)

	async def close(self) -> None:
		await self.adapter.close()
