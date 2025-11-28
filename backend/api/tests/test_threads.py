"""Thread-specific tests."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.project import Project


@pytest.mark.asyncio
async def test_thread_project_association(
	client: AsyncClient,
	db_session: AsyncSession,
) -> None:
	"""Threads can belong to multiple projects and be reassigned."""
	user_payload = {
		"email": "owner@example.com",
		"username": "owner",
		"password": "supersecret",
		"display_name": "Thread Owner",
	}
	user_resp = await client.post("/v1/users", json=user_payload)
	assert user_resp.status_code == 201
	user = user_resp.json()

	project_a = Project(name="Project A", description="A", owner_id=user["id"])
	project_b = Project(name="Project B", description="B", owner_id=user["id"])
	db_session.add_all([project_a, project_b])
	await db_session.commit()
	await db_session.refresh(project_a)
	await db_session.refresh(project_b)

	thread_payload = {
		"owner_id": user["id"],
		"title": "Multi-project thread",
		"project_ids": [project_a.id, project_b.id],
	}
	thread_resp = await client.post("/v1/threads", json=thread_payload)
	assert thread_resp.status_code == 201
	thread = thread_resp.json()
	assert set(thread["project_ids"]) == {project_a.id, project_b.id}
	assert len(thread["projects"]) == 2

	update_resp = await client.patch(
		f"/v1/threads/{thread['id']}",
		json={"project_ids": [project_b.id]},
	)
	assert update_resp.status_code == 200
	updated = update_resp.json()
	assert updated["project_ids"] == [project_b.id]
	assert len(updated["projects"]) == 1
