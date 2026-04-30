"""Open WebUI HTTP client.

Reusable async client for integration operations against a configured Open WebUI
deployment. This module intentionally has no FastAPI or service-layer imports.
"""

from __future__ import annotations

import logging
from types import TracebackType
from typing import Any

import httpx


logger = logging.getLogger(__name__)

_CHATS_PATH = "/api/v1/chats/all"
_CHATS_ARCHIVED_PATH = "/api/v1/chats/all/archived"
_MEMORIES_PATH = "/api/v1/memories/"

_HTTP_TIMEOUT = httpx.Timeout(connect=10.0, read=60.0, write=30.0, pool=10.0)


class OpenWebUIError(Exception):
	"""base error for Open WebUI client failures."""


class OpenWebUIAuthError(OpenWebUIError):
	"""Open WebUI rejected the supplied credential."""


class OpenWebUIRequestError(OpenWebUIError):
	"""Open WebUI request failed before a response was received."""


class OpenWebUIResponseError(OpenWebUIError):
	"""Open WebUI returned an unsuccessful response."""

	def __init__(self, status_code: int, path: str) -> None:
		self.status_code = status_code
		self.path = path
		super().__init__(f"Open WebUI returned {status_code} for {path}")


class OpenWebUIInvalidJSONError(OpenWebUIError):
	"""Open WebUI returned a non-JSON response."""


class OpenWebUIClient:
	"""async client for Open WebUI user-data APIs."""

	def __init__(
		self,
		origin: str,
		credential: str,
		timeout: httpx.Timeout = _HTTP_TIMEOUT,
	) -> None:
		self._origin = origin.rstrip("/")
		self._credential = credential.strip()
		self._timeout = timeout
		self._client: httpx.AsyncClient | None = None

	async def __aenter__(self) -> OpenWebUIClient:
		self._client = httpx.AsyncClient(
			timeout=self._timeout,
			headers={
				"Authorization": f"Bearer {self._credential}",
				"Accept": "application/json",
			},
			follow_redirects=True,
		)
		return self

	async def __aexit__(
		self,
		exc_type: type[BaseException] | None,
		exc: BaseException | None,
		traceback: TracebackType | None,
	) -> None:
		await self.aclose()

	async def aclose(self) -> None:
		"""close the underlying HTTP client."""
		if self._client is not None:
			await self._client.aclose()
			self._client = None

	async def list_all_chats(self) -> list[dict[str, Any]]:
		"""return all visible Open WebUI chats for the credential."""
		chats = self._list_dicts(await self._get_json(_CHATS_PATH))
		try:
			archived = self._list_dicts(await self._get_json(_CHATS_ARCHIVED_PATH))
		except OpenWebUIError:
			logger.debug("Open WebUI archived chats endpoint was unavailable")
			archived = []

		seen = {chat.get("id") for chat in chats}
		for chat in archived:
			if chat.get("id") not in seen:
				chats.append(chat)
		return chats

	async def list_memories(self) -> list[dict[str, Any]]:
		"""return all visible Open WebUI memories for the credential."""
		return self._list_dicts(await self._get_json(_MEMORIES_PATH))

	async def _get_json(self, path: str) -> Any:
		if self._client is None:
			raise RuntimeError("Open WebUI client is not open")

		try:
			response = await self._client.get(f"{self._origin}{path}")
		except httpx.HTTPError as exc:
			raise OpenWebUIRequestError(f"Open WebUI request failed: {exc}") from exc

		if response.status_code in (401, 403):
			raise OpenWebUIAuthError("Open WebUI rejected the provided credential")
		if response.status_code >= 400:
			raise OpenWebUIResponseError(response.status_code, path)

		try:
			return response.json()
		except ValueError as exc:
			raise OpenWebUIInvalidJSONError(
				"Open WebUI returned non-JSON response"
			) from exc

	@staticmethod
	def _list_dicts(value: Any) -> list[dict[str, Any]]:
		if not isinstance(value, list):
			return []
		return [item for item in value if isinstance(item, dict)]
