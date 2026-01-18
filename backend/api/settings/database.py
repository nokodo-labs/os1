"""database-backed settings source."""

from __future__ import annotations

import asyncio
import concurrent.futures
from typing import Any

from pydantic import BaseModel
from pydantic_settings import PydanticBaseSettingsSource
from sqlalchemy import select

from api.core.database import AsyncSessionLocal
from api.models.setting import SettingsDocument


def _is_write_locked(schema: type[BaseModel], field_name: str) -> bool:
	info = schema.model_fields.get(field_name)
	if not info:
		return False
	extra = info.json_schema_extra
	if not isinstance(extra, dict):
		return False
	return bool(extra.get("write_locked"))


def _load_db_overrides(settings_cls: type) -> dict[str, dict[str, Any]]:
	"""synchronously load settings overrides from database."""

	async def fetch() -> dict[str, dict[str, Any]]:
		try:
			async with AsyncSessionLocal() as db:
				result = await db.execute(select(SettingsDocument))
				docs = result.scalars().all()
		except Exception:
			return {}

		overrides: dict[str, dict[str, Any]] = {}
		for doc in docs:
			section = doc.namespace
			if section not in settings_cls.model_fields:
				continue
			if not doc.data:
				continue

			annotation = settings_cls.model_fields[section].annotation
			if annotation is None or not issubclass(annotation, BaseModel):
				continue

			# only load writable fields from db (write_locked = env-only)
			filtered = {
				k: v for k, v in doc.data.items() if not _is_write_locked(annotation, k)
			}
			if filtered:
				overrides[section] = filtered

		return overrides

	try:
		loop = asyncio.get_running_loop()
	except RuntimeError:
		loop = None

	if loop is not None:
		with concurrent.futures.ThreadPoolExecutor() as pool:
			return pool.submit(asyncio.run, fetch()).result()
	return asyncio.run(fetch())


class DbSettingsSource(PydanticBaseSettingsSource):
	"""pydantic settings source that loads from settings_documents table."""

	def get_field_value(self, field: Any, field_name: str) -> tuple[Any, str, bool]:
		return None, field_name, False

	def __call__(self) -> dict[str, Any]:
		return _load_db_overrides(self.settings_cls)
