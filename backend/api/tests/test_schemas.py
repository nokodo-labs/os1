"""Schema-specific unit tests for ORM-aware validators."""

from __future__ import annotations

from datetime import UTC, datetime

from api.models.project import Project as ProjectModel
from api.models.thread import Thread as ThreadModel
from api.schemas.project import Project as ProjectSchema
from api.schemas.thread import Thread as ThreadSchema
from api.schemas.thread import ThreadSummary
from nokodo_ai.utils.typeid import new_typeid


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
	owner_id = new_typeid("user")
	project_id = new_typeid("proj")
	thread_id = new_typeid("thread")
	project = _stamp_project(
		ProjectModel(name="Schema", description="Test", owner_id=owner_id),
		project_id=project_id,
	)
	thread = _stamp_thread(ThreadModel(owner_id=owner_id), thread_id=thread_id)
	project.threads = [thread]

	serialized = ProjectSchema.model_validate(project)
	assert serialized.thread_ids == [thread_id]


def test_project_schema_handles_empty_threads() -> None:
	owner_id = new_typeid("user")
	project = _stamp_project(
		ProjectModel(name="Schema", description="Test", owner_id=owner_id),
		project_id=new_typeid("proj"),
	)
	project.threads = []

	serialized = ProjectSchema.model_validate(project)
	assert serialized.thread_ids == []


def test_project_schema_respects_existing_thread_ids() -> None:
	owner_id = new_typeid("user")
	preloaded_thread_id = new_typeid("thread")
	project = _stamp_project(
		ProjectModel(name="Schema", description="Test", owner_id=owner_id),
		project_id=new_typeid("proj"),
	)
	project.thread_ids = [preloaded_thread_id]
	project.threads = []

	serialized = ProjectSchema.model_validate(project)
	assert serialized.thread_ids == [preloaded_thread_id]


def test_thread_schema_populates_project_ids() -> None:
	owner_id = new_typeid("user")
	thread_id = new_typeid("thread")
	project_id = new_typeid("proj")
	thread = _stamp_thread(ThreadModel(owner_id=owner_id), thread_id=thread_id)
	project = _stamp_project(
		ProjectModel(name="Schema", description="Test", owner_id=owner_id),
		project_id=project_id,
	)
	thread.projects = [project]

	detailed = ThreadSchema.model_validate(thread)
	summary = ThreadSummary.model_validate(thread)

	assert detailed.project_ids == [project_id]
	assert summary.project_ids == [project_id]
