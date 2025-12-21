"""EmbeddingModel high-level interface - unified access to embedding models."""

from __future__ import annotations

from nokodo_ai.adapters.embedding import BaseEmbeddingAdapter


DEFAULT_PROVIDER = "openai"


class EmbeddingModel:
	"""high-level unified interface for embedding models.

	usage (magic - auto-selects adapter):
		embedder = EmbeddingModel("openai:text-embedding-3-large")
		vectors = await embedder.embed(["hello", "world"])

	usage (explicit adapter):
		from nokodo_ai.adapters.openai import OpenAIEmbeddingAdapter
		adapter = OpenAIEmbeddingAdapter(api_key="...")
		embedder = EmbeddingModel(adapter=adapter)
	"""

	def __init__(
		self,
		model: str | None = None,
		*,
		adapter: BaseEmbeddingAdapter | None = None,
	) -> None:
		"""initialize embedding model interface.

		args:
			model: model identifier with optional provider and variant prefix:
				[provider[.variant]:]model (e.g., "text-embedding-3-large",
				"openai:text-embedding-3-large", "ollama:nomic-embed-text")
			adapter: explicit adapter instance (overrides model string)
		"""
		# model is always required
		if model is None or model.strip() == "":
			raise ValueError("model must be provided")

		self._model = model

		if adapter is not None:
			self._adapter = adapter
		else:
			self._adapter = self._resolve_adapter(model)

	def _resolve_adapter(self, model: str) -> BaseEmbeddingAdapter:
		"""resolve a model string to an adapter instance.

		format: [provider[.variant]:][model_name]
		examples:
			- "text-embedding-3-large" -> default provider's embedding adapter
			- "openai:text-embedding-3-large" -> openai embedding adapter
			- "ollama:nomic-embed-text" -> ollama embedding adapter
		"""
		# parse provider and model from string
		if ":" in model:
			provider_part, model_name = model.split(":", 1)
		else:
			# no provider specified: fallback to default provider
			provider_part = DEFAULT_PROVIDER
			model_name = model

		# parse provider and optional variant
		if "." in provider_part:
			provider, variant = provider_part.split(".", 1)
		else:
			provider = provider_part
			variant = None

		# delegate to provider factory
		match provider:
			case "openai":
				from nokodo_ai.adapters.openai import get_embedding_adapter

				return get_embedding_adapter(variant, model_name)

			case "ollama":
				from nokodo_ai.adapters.ollama import get_embedding_adapter

				return get_embedding_adapter(variant, model_name)

			case _:
				raise ValueError(f"unknown embedding provider: {provider}")

	async def embed(self, texts: list[str]) -> list[list[float]]:
		"""generate embeddings for the given texts.

		args:
			texts: list of strings to embed

		returns:
			list of embedding vectors (one per input text)
		"""
		return await self._adapter.embed(texts)
