"""Open WebUI HTTP client.

Reusable async client for integration operations against a configured Open WebUI
deployment. This module intentionally has no FastAPI or service-layer imports.
"""

from __future__ import annotations

import logging
from types import TracebackType
from typing import Any
from urllib.parse import quote

import httpx


logger = logging.getLogger(__name__)

_CHAT_LIST_PATH = "/api/v1/chats/"
_CHAT_ARCHIVED_LIST_PATH = "/api/v1/chats/archived"
_CHATS_BULK_PATH = "/api/v1/chats/all"
_CHATS_ARCHIVED_BULK_PATH = "/api/v1/chats/all/archived"
_CHAT_PATH = "/api/v1/chats"
_FILES_PATH = "/api/v1/files"
_FOLDERS_PATH = "/api/v1/folders/"
_MEMORIES_PATH = "/api/v1/memories/"
_NOTES_PATH = "/api/v1/notes/"
_MODELS_PATH = "/api/models"
_CHAT_LIST_PAGE_SIZE = 60
_NOTE_LIST_PAGE_SIZE = 60

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

	async def list_all_chats(
		self,
		include_archived_chats: bool = False,
	) -> list[dict[str, Any]]:
		"""return all visible Open WebUI chats for the credential."""
		return await self.list_bulk_chats(include_archived_chats)

	async def list_bulk_chats(
		self,
		include_archived_chats: bool = False,
	) -> list[dict[str, Any]]:
		"""return full chats using Open WebUI's bulk export endpoints."""
		chats: list[dict[str, Any]] = []
		chats.extend(self._list_dicts(await self._get_json(_CHATS_BULK_PATH)))
		if include_archived_chats:
			archived = self._list_dicts(await self._get_json(_CHATS_ARCHIVED_BULK_PATH))
			chats.extend({**chat, "archived": True} for chat in archived)
		return chats

	async def list_chat_refs(
		self,
		include_archived_chats: bool = False,
	) -> list[dict[str, Any]]:
		"""return lightweight chat references using Open WebUI's list APIs."""
		refs = self._list_dicts(
			await self._get_json(
				_CHAT_LIST_PATH,
				params={"include_pinned": "true", "include_folders": "true"},
			)
		)
		if include_archived_chats:
			archived = await self._list_chat_refs(_CHAT_ARCHIVED_LIST_PATH)
			refs.extend({**ref, "archived": True} for ref in archived)
		return self._dedupe_by_id(refs)

	async def get_chat(self, chat_id: str) -> dict[str, Any] | None:
		"""return a full Open WebUI chat by id."""
		encoded_id = quote(chat_id, safe="")
		value = await self._get_json(f"{_CHAT_PATH}/{encoded_id}")
		return value if isinstance(value, dict) else None

	async def list_memories(self) -> list[dict[str, Any]]:
		"""return all visible Open WebUI memories for the credential."""
		return self._list_dicts(await self._get_json(_MEMORIES_PATH))

	async def list_models(self) -> list[dict[str, Any]]:
		"""return all visible Open WebUI models for the credential."""
		value = await self._get_json(_MODELS_PATH)
		if isinstance(value, dict):
			return self._list_dicts(value.get("data"))
		return self._list_dicts(value)

	async def list_notes(self) -> list[dict[str, Any]]:
		"""return all visible Open WebUI notes for the credential."""
		refs: list[dict[str, Any]] = []
		page = 1
		while True:
			batch = self._list_dicts(
				await self._get_json(_NOTES_PATH, params={"page": str(page)})
			)
			if not batch:
				break
			refs.extend(batch)
			if len(batch) < _NOTE_LIST_PAGE_SIZE:
				break
			page += 1

		notes: list[dict[str, Any]] = []
		for ref in self._dedupe_by_id(refs):
			note_id = ref.get("id")
			if not isinstance(note_id, str) or not note_id:
				continue
			note = await self.get_note(note_id)
			notes.append({**ref, **note} if note is not None else ref)
		return notes

	async def get_note(self, note_id: str) -> dict[str, Any] | None:
		"""return a full Open WebUI note by id."""
		encoded_id = quote(note_id, safe="")
		value = await self._get_json(f"{_NOTES_PATH}{encoded_id}")
		return value if isinstance(value, dict) else None

	async def list_folders(self) -> list[dict[str, Any]]:
		"""return all visible Open WebUI folders for the credential."""
		return self._list_dicts(await self._get_json(_FOLDERS_PATH))

	async def get_file_metadata(self, file_id: str) -> dict[str, Any] | None:
		"""return Open WebUI file metadata for a file id."""
		encoded_id = quote(file_id, safe="")
		value = await self._get_json(f"{_FILES_PATH}/{encoded_id}")
		return value if isinstance(value, dict) else None

	async def download_file(self, file_id: str) -> tuple[bytes, str | None]:
		"""download Open WebUI file bytes by file id."""
		encoded_id = quote(file_id, safe="")
		return await self._get_bytes(f"{_FILES_PATH}/{encoded_id}/content")

	async def _get_json(
		self,
		path: str,
		params: dict[str, str] | None = None,
	) -> Any:
		response = await self._get(path, params=params)

		try:
			return response.json()
		except ValueError as exc:
			raise OpenWebUIInvalidJSONError(
				"Open WebUI returned non-JSON response"
			) from exc

	async def _get_bytes(self, path: str) -> tuple[bytes, str | None]:
		response = await self._get(path)
		content_type = response.headers.get("content-type")
		if content_type:
			content_type = content_type.split(";", 1)[0].strip() or None
		return response.content, content_type

	async def _get(
		self,
		path: str,
		params: dict[str, str] | None = None,
	) -> httpx.Response:
		if self._client is None:
			raise RuntimeError("Open WebUI client is not open")

		try:
			response = await self._client.get(f"{self._origin}{path}", params=params)
		except httpx.HTTPError as exc:
			detail = str(exc).strip() or exc.__class__.__name__
			raise OpenWebUIRequestError(
				f"Open WebUI request failed for {path}: {detail}"
			) from exc

		if response.status_code in (401, 403):
			raise OpenWebUIAuthError("Open WebUI rejected the provided credential")
		if response.status_code >= 400:
			raise OpenWebUIResponseError(response.status_code, path)
		return response

	@staticmethod
	def _list_dicts(value: Any) -> list[dict[str, Any]]:
		if not isinstance(value, list):
			return []
		return [item for item in value if isinstance(item, dict)]

	async def _list_chat_refs(
		self,
		path: str,
		params: dict[str, str] | None = None,
	) -> list[dict[str, Any]]:
		refs: list[dict[str, Any]] = []
		page = 1
		while True:
			page_params = {**(params or {}), "page": str(page)}
			batch = self._list_dicts(await self._get_json(path, params=page_params))
			if not batch:
				break
			refs.extend(batch)
			if len(batch) < _CHAT_LIST_PAGE_SIZE:
				break
			page += 1
		return refs

	@staticmethod
	def _dedupe_by_id(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
		seen: set[str] = set()
		out: list[dict[str, Any]] = []
		for value in values:
			value_id = value.get("id")
			if not isinstance(value_id, str) or not value_id:
				continue
			if value_id in seen:
				continue
			seen.add(value_id)
			out.append(value)
		return out

	@staticmethod
	def _is_archived_chat(value: dict[str, Any]) -> bool:
		if value.get("archived") is True:
			return True
		chat = value.get("chat")
		return isinstance(chat, dict) and chat.get("archived") is True
