"""Schema-specific unit tests for ORM-aware validators."""

from __future__ import annotations

from datetime import UTC, datetime

from api.models.project import Project as ProjectModel
from api.models.thread import Thread as ThreadModel
from api.schemas.project import Project as ProjectSchema
from api.schemas.thread import Thread as ThreadSchema
from api.schemas.thread import ThreadSummary


def _stamp_project(project: ProjectModel, *, project_id: str) -> ProjectModel:
	project.id = project_id
	project.metadata_ = {}
	project.created_at = datetime.now(tz=UTC)
	project.updated_at = datetime.now(tz=UTC)
	return project


def _stamp_thread(thread: ThreadModel, *, thread_id: str) -> ThreadModel:
	thread.id = thread_id
	thread.metadata_ = {}
	thread.tags = []
	thread.is_archived = False
	thread.last_activity_at = datetime.now(tz=UTC)
	thread.created_at = datetime.now(tz=UTC)
	thread.updated_at = datetime.now(tz=UTC)
	return thread


def test_project_schema_populates_thread_ids() -> None:
	project = _stamp_project(
		ProjectModel(name="Schema", description="Test", owner_id=1),
		project_id="project-schema",
	)
	thread = _stamp_thread(ThreadModel(owner_id=1), thread_id="thread-schema")
	project.threads = [thread]

	serialized = ProjectSchema.model_validate(project)
	assert serialized.thread_ids == ["thread-schema"]


def test_project_schema_handles_empty_threads() -> None:
	project = _stamp_project(
		ProjectModel(name="Schema", description="Test", owner_id=1),
		project_id="project-empty",
	)
	project.threads = []

	serialized = ProjectSchema.model_validate(project)
	assert serialized.thread_ids == []


def test_project_schema_respects_existing_thread_ids() -> None:
	project = _stamp_project(
		ProjectModel(name="Schema", description="Test", owner_id=1),
		project_id="project-existing",
	)
	project.thread_ids = ["preloaded"]
	project.threads = []

	serialized = ProjectSchema.model_validate(project)
	assert serialized.thread_ids == ["preloaded"]


def test_thread_schema_populates_project_ids() -> None:
	thread = _stamp_thread(ThreadModel(owner_id=1), thread_id="thread-schema")
	project = _stamp_project(
		ProjectModel(name="Schema", description="Test", owner_id=1),
		project_id="project-schema",
	)
	thread.projects = [project]

	detailed = ThreadSchema.model_validate(thread)
	summary = ThreadSummary.model_validate(thread)

	assert detailed.project_ids == ["project-schema"]
	assert summary.project_ids == ["project-schema"]
