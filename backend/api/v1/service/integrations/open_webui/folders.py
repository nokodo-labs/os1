"""Open WebUI folder parsing and project import writers."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.project import Project
from api.settings import OpenWebUIDeployment
from api.v1.service.integrations.open_webui.common import (
	ImportSummary,
	_epoch_to_dt,
	_merge_metadata,
	_owui_field_filter,
	_owui_metadata,
	_owui_origin_filter,
)
from nokodo_ai.utils.typeid import TypeID


_PINNED_CHATS_PROJECT_NAME = "pinned chats"


def _folder_id(folder: dict[str, Any]) -> str | None:
	value = folder.get("id")
	return value if isinstance(value, str) and value else None


def _folder_parent_id(folder: dict[str, Any]) -> str | None:
	value = folder.get("parent_id")
	return value if isinstance(value, str) and value else None


def _folder_name(folder: dict[str, Any]) -> str:
	name = folder.get("name")
	if isinstance(name, str) and name.strip():
		return name.strip()
	return "imported folder"


def _folder_path(
	folder: dict[str, Any],
	folders_by_id: dict[str, dict[str, Any]],
) -> str:
	parts: list[str] = []
	seen: set[str] = set()
	current: dict[str, Any] | None = folder
	while current is not None:
		current_id = _folder_id(current)
		if current_id is None or current_id in seen:
			break
		seen.add(current_id)
		parts.append(_folder_name(current))
		parent_id = _folder_parent_id(current)
		current = folders_by_id.get(parent_id) if parent_id is not None else None
	return " / ".join(reversed(parts))


async def _find_folder_project(
	session: AsyncSession,
	owner_id: TypeID,
	deployment: OpenWebUIDeployment,
	folder_id: str,
) -> Project | None:
	result = await session.scalars(
		select(Project)
		.where(
			Project.owner_id == owner_id,
			Project.metadata_["imported_from"].as_string() == "open_webui",
			_owui_origin_filter(Project.metadata_, deployment),
			_owui_field_filter(Project.metadata_, "folder_id", folder_id),
		)
		.limit(1)
	)
	return result.one_or_none()


async def _find_pinned_chats_project(
	session: AsyncSession,
	owner_id: TypeID,
	deployment: OpenWebUIDeployment,
) -> Project | None:
	result = await session.scalars(
		select(Project)
		.where(
			Project.owner_id == owner_id,
			Project.metadata_["imported_from"].as_string() == "open_webui",
			_owui_origin_filter(Project.metadata_, deployment),
			_owui_field_filter(Project.metadata_, "special_project", "pinned_chats"),
		)
		.limit(1)
	)
	return result.one_or_none()


async def _import_folder_projects(
	folders: Iterable[dict[str, Any]],
	session: AsyncSession,
	owner_id: TypeID,
	deployment: OpenWebUIDeployment,
	summary: ImportSummary,
) -> dict[str, Project]:
	folders_by_id = {
		folder_id: folder
		for folder in folders
		if (folder_id := _folder_id(folder)) is not None
	}
	projects_by_folder_id: dict[str, Project] = {}
	for folder_id, folder in folders_by_id.items():
		name = _folder_name(folder)
		if not name:
			summary.projects_skipped += 1
			continue
		metadata = _owui_metadata(
			deployment,
			"folder",
			folder_id,
			folder_id=folder_id,
			parent_folder_id=_folder_parent_id(folder),
			folder_path=_folder_path(folder, folders_by_id),
		)
		existing = await _find_folder_project(
			session=session,
			owner_id=owner_id,
			deployment=deployment,
			folder_id=folder_id,
		)
		if existing is not None:
			existing.metadata_ = _merge_metadata(existing.metadata_, metadata)
			projects_by_folder_id[folder_id] = existing
			summary.projects_skipped += 1
			continue
		project = Project(
			name=name[:100],
			description=None,
			owner_id=owner_id,
			metadata_=metadata,
		)
		session.add(project)
		await session.flush()
		created_at = _epoch_to_dt(folder.get("created_at"))
		updated_at = _epoch_to_dt(folder.get("updated_at"))
		if created_at:
			project.created_at = created_at
		if updated_at:
			project.updated_at = updated_at
		projects_by_folder_id[folder_id] = project
		summary.projects_imported += 1
	return projects_by_folder_id


async def _import_pinned_chats_project(
	session: AsyncSession,
	owner_id: TypeID,
	deployment: OpenWebUIDeployment,
	summary: ImportSummary,
) -> Project:
	existing = await _find_pinned_chats_project(
		session=session,
		owner_id=owner_id,
		deployment=deployment,
	)
	metadata = _owui_metadata(
		deployment,
		"project",
		"pinned_chats",
		special_project="pinned_chats",
	)
	if existing is not None:
		existing.metadata_ = _merge_metadata(existing.metadata_, metadata)
		summary.projects_skipped += 1
		return existing
	project = Project(
		name=_PINNED_CHATS_PROJECT_NAME,
		description=None,
		owner_id=owner_id,
		metadata_=metadata,
	)
	session.add(project)
	await session.flush()
	summary.projects_imported += 1
	return project
