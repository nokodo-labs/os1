"""Open WebUI note parsing and import writers."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.note import Note
from api.settings import OpenWebUIDeployment
from api.v1.service.integrations.open_webui.common import (
	ImportSummary,
	_first_dt,
	_first_str,
	_iter_tag_values,
	_merge_metadata,
	_normalize_chat_tag,
	_owui_field_filter,
	_owui_metadata,
	_owui_origin_filter,
)
from nokodo_ai.utils.typeid import TypeID


logger = logging.getLogger(__name__)


def _note_content(raw: dict[str, Any]) -> str:
	content = raw.get("content")
	if isinstance(content, str):
		return content
	data = raw.get("data")
	if isinstance(data, dict):
		content_data = data.get("content")
		if isinstance(content_data, dict):
			md = content_data.get("md")
			if isinstance(md, str):
				return md
			text = content_data.get("text")
			if isinstance(text, str):
				return text
		md = data.get("md")
		if isinstance(md, str):
			return md
	return ""


def _note_title(raw: dict[str, Any]) -> str:
	title = raw.get("title")
	if isinstance(title, str) and title.strip():
		return title.strip()[:255]
	return "imported note"


def _note_labels(raw: dict[str, Any]) -> list[str]:
	candidates: list[str] = []
	for key in ("labels", "tags"):
		candidates.extend(_iter_tag_values(raw.get(key)))
	for meta_key in ("meta", "metadata"):
		meta = raw.get(meta_key)
		if not isinstance(meta, dict):
			continue
		for key in ("labels", "tags"):
			candidates.extend(_iter_tag_values(meta.get(key)))

	labels: list[str] = []
	seen: set[str] = set()
	for candidate in candidates:
		label = _normalize_chat_tag(candidate)
		if label is None or label in seen:
			continue
		labels.append(label)
		seen.add(label)
	return labels


async def _find_note_for_owui_id(
	session: AsyncSession,
	owner_id: TypeID,
	deployment: OpenWebUIDeployment,
	owui_note_id: str,
) -> Note | None:
	result = await session.scalars(
		select(Note)
		.where(
			Note.user_id == owner_id,
			Note.deleted_at.is_(None),
			Note.metadata_["imported_from"].as_string() == "open_webui",
			_owui_origin_filter(Note.metadata_, deployment),
			_owui_field_filter(Note.metadata_, "note_id", owui_note_id),
		)
		.limit(1)
	)
	return result.one_or_none()


async def _import_notes(
	notes: Iterable[dict[str, Any]],
	session: AsyncSession,
	owner_id: TypeID,
	deployment: OpenWebUIDeployment,
	summary: ImportSummary,
) -> None:
	for raw in notes:
		note_id = _first_str(raw, "id", "note_id")
		if note_id is None:
			summary.notes_skipped += 1
			summary.add_error("note skipped: missing Open WebUI id")
			continue
		metadata = _owui_metadata(
			deployment,
			"note",
			note_id,
			note_id=note_id,
			is_pinned=raw.get("is_pinned") is True,
		)
		created_at = _first_dt(raw, "created_at", "createdAt")
		updated_at = _first_dt(raw, "updated_at", "updatedAt")
		title = _note_title(raw)
		content = _note_content(raw)
		labels = _note_labels(raw)
		existing = await _find_note_for_owui_id(
			session=session,
			owner_id=owner_id,
			deployment=deployment,
			owui_note_id=note_id,
		)
		if existing is not None:
			existing.title = title
			existing.content = content
			existing.labels = labels
			existing.metadata_ = _merge_metadata(existing.metadata_, metadata)
			if created_at:
				existing.created_at = created_at
			if updated_at:
				existing.updated_at = updated_at
			# include in vectorization so a re-import fills any gap from a
			# previous run where the note was stored but not vectorized.
			summary.note_ids.append(existing.id)
			summary.notes_skipped += 1
			continue
		note = Note(
			user_id=owner_id,
			title=title,
			content=content,
			labels=labels,
			metadata_=metadata,
		)
		session.add(note)
		await session.flush()
		if created_at:
			note.created_at = created_at
		if updated_at:
			note.updated_at = updated_at
		summary.note_ids.append(note.id)
		summary.notes_imported += 1
