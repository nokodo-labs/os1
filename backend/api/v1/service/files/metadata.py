"""shared file search/vector metadata helpers."""

from __future__ import annotations

from api.models.file import File
from api.v1.service.vectorstores import VectorChunkResourceType
from nokodo_ai.types.json import JSONObject


FILE_RESOURCE_TYPE = VectorChunkResourceType.FILE
FILE_CONTENT_RESOURCE_TYPE = VectorChunkResourceType.FILE_CONTENT


def file_searchable_text(file: File) -> str:
	"""combine filename and description text for file-level search."""
	parts = [file.filename or ""]
	if file.description:
		parts.append(file.description)
	return " ".join(part for part in parts if part).strip()


def file_metadata(file: File) -> JSONObject:
	"""build shared vector payload metadata for file chunks."""
	return {
		"resource_type": FILE_RESOURCE_TYPE.value,
		"owner_id": str(file.owner_id),
		"filename": file.filename or "",
		"mime_type": file.mime_type or "",
		"source": file.source.value,
		"status": file.status.value,
		"project_ids": [str(project_id) for project_id in file.project_ids],
		"allowed_user_ids": [],
		"allowed_group_ids": [],
		"allowed_role_ids": [],
	}
