"""acl api tests."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from nokodo_ai.utils.typeid import new_typeid


@pytest.mark.asyncio
async def test_acl_list_set_update_remove(
	client: AsyncClient,
	user_auth: dict[str, object],
) -> None:
	headers = user_auth["headers"]
	assert isinstance(headers, dict)
	user = user_auth["user"]
	assert isinstance(user, dict)

	thread_resp = await client.post(
		"/v1/threads",
		json={"owner_id": user["id"], "title": "acl thread"},
		headers=headers,
	)
	assert thread_resp.status_code == 201
	thread = thread_resp.json()

	list_resp = await client.get(f"/v1/threads/{thread['id']}/acl", headers=headers)
	assert list_resp.status_code == 200
	assert list_resp.json() == []

	set_resp = await client.put(
		f"/v1/threads/{thread['id']}/acl",
		json=[{"user_id": user["id"], "role": "viewer"}],
		headers=headers,
	)
	assert set_resp.status_code == 200
	entries = set_resp.json()
	assert len(entries) == 1
	assert entries[0]["user_id"] == user["id"]
	assert entries[0]["role"] == "viewer"
	assert entries[0]["thread_id"] == thread["id"]

	update_resp = await client.put(
		f"/v1/threads/{thread['id']}/acl",
		json=[{"user_id": user["id"], "role": "editor"}],
		headers=headers,
	)
	assert update_resp.status_code == 200
	entries = update_resp.json()
	assert len(entries) == 1
	assert entries[0]["role"] == "editor"

	remove_resp = await client.put(
		f"/v1/threads/{thread['id']}/acl",
		json=[],
		headers=headers,
	)
	assert remove_resp.status_code == 200
	assert remove_resp.json() == []


@pytest.mark.asyncio
async def test_acl_validation_requires_one_principal(
	client: AsyncClient,
	user_auth: dict[str, object],
) -> None:
	headers = user_auth["headers"]
	assert isinstance(headers, dict)
	user = user_auth["user"]
	assert isinstance(user, dict)
	thread_resp = await client.post(
		"/v1/threads",
		json={"owner_id": user["id"], "title": "acl validate"},
		headers=headers,
	)
	thread = thread_resp.json()

	resp = await client.put(
		f"/v1/threads/{thread['id']}/acl",
		json=[{"role": "viewer"}],
		headers=headers,
	)
	assert resp.status_code == 422

	resp = await client.put(
		f"/v1/threads/{thread['id']}/acl",
		json=[
			{
				"user_id": user["id"],
				"group_id": new_typeid("group"),
				"role": "viewer",
			}
		],
		headers=headers,
	)
	assert resp.status_code == 422


@pytest.mark.asyncio
async def test_acl_rejects_unknown_principal(
	client: AsyncClient,
	user_auth: dict[str, object],
) -> None:
	headers = user_auth["headers"]
	assert isinstance(headers, dict)
	user = user_auth["user"]
	assert isinstance(user, dict)
	thread_resp = await client.post(
		"/v1/threads",
		json={"owner_id": user["id"], "title": "acl unknown"},
		headers=headers,
	)
	thread = thread_resp.json()

	resp = await client.put(
		f"/v1/threads/{thread['id']}/acl",
		json=[{"user_id": new_typeid("user"), "role": "viewer"}],
		headers=headers,
	)
	assert resp.status_code == 404
	assert resp.json()["detail"] == "User not found"


@pytest.mark.asyncio
async def test_acl_rejects_duplicate_principals(
	client: AsyncClient,
	user_auth: dict[str, object],
) -> None:
	headers = user_auth["headers"]
	assert isinstance(headers, dict)
	user = user_auth["user"]
	assert isinstance(user, dict)
	thread_resp = await client.post(
		"/v1/threads",
		json={"owner_id": user["id"], "title": "acl dupe"},
		headers=headers,
	)
	thread = thread_resp.json()

	resp = await client.put(
		f"/v1/threads/{thread['id']}/acl",
		json=[
			{"user_id": user["id"], "role": "viewer"},
			{"user_id": user["id"], "role": "editor"},
		],
		headers=headers,
	)
	assert resp.status_code == 422
	assert resp.json()["detail"] == "Duplicate principal entries are not allowed"


@pytest.mark.asyncio
async def test_thread_acl_not_found_returns_404(
	client: AsyncClient,
	user_auth: dict[str, object],
) -> None:
	headers = user_auth["headers"]
	assert isinstance(headers, dict)
	resp = await client.get(
		f"/v1/threads/{new_typeid('thread')}/acl",
		headers=headers,
	)
	assert resp.status_code == 404
	assert resp.json()["detail"] == "Thread not found"


@pytest.mark.asyncio
async def test_project_acl_list_set_with_group_and_agent(
	client: AsyncClient,
	db_session: AsyncSession,
	user_auth: dict[str, object],
) -> None:
	from api.models.agent import Agent
	from api.models.group import Group
	from api.models.project import Project

	headers = user_auth["headers"]
	assert isinstance(headers, dict)
	user = user_auth["user"]
	assert isinstance(user, dict)

	project = Project(name="acl project", description=None, owner_id=user["id"])
	db_session.add(project)
	await db_session.commit()
	await db_session.refresh(project)

	group = Group(name="acl group", description=None, owner_id=user["id"])
	db_session.add(group)

	agent = Agent(name="acl agent", description=None, system_prompt=None)
	db_session.add(agent)

	await db_session.commit()
	await db_session.refresh(group)
	await db_session.refresh(agent)

	list_resp = await client.get(f"/v1/projects/{project.id}/acl", headers=headers)
	assert list_resp.status_code == 200
	assert list_resp.json() == []

	set_resp = await client.put(
		f"/v1/projects/{project.id}/acl",
		json=[
			{"group_id": group.id, "role": "viewer"},
			{"agent_id": agent.id, "role": "admin"},
		],
		headers=headers,
	)
	assert set_resp.status_code == 200
	entries = set_resp.json()
	assert len(entries) == 2
	assert {e["role"] for e in entries} == {"viewer", "admin"}
	assert all(e["project_id"] == project.id for e in entries)

	update_resp = await client.put(
		f"/v1/projects/{project.id}/acl",
		json=[
			{"group_id": group.id, "role": "editor"},
			{"agent_id": agent.id, "role": "viewer"},
		],
		headers=headers,
	)
	assert update_resp.status_code == 200
	entries = update_resp.json()
	assert len(entries) == 2
	assert {e["role"] for e in entries} == {"editor", "viewer"}


@pytest.mark.asyncio
async def test_project_acl_rejects_unknown_group(
	client: AsyncClient,
	db_session: AsyncSession,
	user_auth: dict[str, object],
) -> None:
	from api.models.project import Project

	headers = user_auth["headers"]
	assert isinstance(headers, dict)
	user = user_auth["user"]
	assert isinstance(user, dict)

	project = Project(
		name="unknown group project",
		description=None,
		owner_id=user["id"],
	)
	db_session.add(project)
	await db_session.commit()
	await db_session.refresh(project)

	resp = await client.put(
		f"/v1/projects/{project.id}/acl",
		json=[{"group_id": new_typeid("group"), "role": "viewer"}],
		headers=headers,
	)
	assert resp.status_code == 404
	assert resp.json()["detail"] == "Group not found"


@pytest.mark.asyncio
async def test_project_acl_rejects_unknown_agent(
	client: AsyncClient,
	db_session: AsyncSession,
	user_auth: dict[str, object],
) -> None:
	from api.models.project import Project

	headers = user_auth["headers"]
	assert isinstance(headers, dict)
	user = user_auth["user"]
	assert isinstance(user, dict)

	project = Project(
		name="unknown agent project",
		description=None,
		owner_id=user["id"],
	)
	db_session.add(project)
	await db_session.commit()
	await db_session.refresh(project)

	resp = await client.put(
		f"/v1/projects/{project.id}/acl",
		json=[{"agent_id": new_typeid("agent"), "role": "viewer"}],
		headers=headers,
	)
	assert resp.status_code == 404
	assert resp.json()["detail"] == "Agent not found"


@pytest.mark.asyncio
async def test_project_acl_set_update_remove(
	client: AsyncClient,
	db_session: AsyncSession,
	user_auth: dict[str, object],
) -> None:
	from api.models.group import Group
	from api.models.project import Project

	headers = user_auth["headers"]
	assert isinstance(headers, dict)
	user = user_auth["user"]
	assert isinstance(user, dict)

	project = Project(name="acl update project", description=None, owner_id=user["id"])
	group = Group(name="acl update group", description=None, owner_id=user["id"])
	db_session.add_all([project, group])
	await db_session.commit()
	await db_session.refresh(project)
	await db_session.refresh(group)

	set_resp = await client.put(
		f"/v1/projects/{project.id}/acl",
		json=[{"group_id": group.id, "role": "viewer"}],
		headers=headers,
	)
	assert set_resp.status_code == 200
	entries = set_resp.json()
	assert len(entries) == 1
	assert entries[0]["group_id"] == group.id
	assert entries[0]["role"] == "viewer"

	update_resp = await client.put(
		f"/v1/projects/{project.id}/acl",
		json=[{"group_id": group.id, "role": "editor"}],
		headers=headers,
	)
	assert update_resp.status_code == 200
	entries = update_resp.json()
	assert len(entries) == 1
	assert entries[0]["role"] == "editor"

	remove_resp = await client.put(
		f"/v1/projects/{project.id}/acl",
		json=[],
		headers=headers,
	)
	assert remove_resp.status_code == 200
	assert remove_resp.json() == []


@pytest.mark.asyncio
async def test_project_acl_rejects_duplicate_principals(
	client: AsyncClient,
	db_session: AsyncSession,
	user_auth: dict[str, object],
) -> None:
	from api.models.group import Group
	from api.models.project import Project

	headers = user_auth["headers"]
	assert isinstance(headers, dict)
	user = user_auth["user"]
	assert isinstance(user, dict)

	project = Project(name="acl dupe project", description=None, owner_id=user["id"])
	group = Group(name="acl dupe group", description=None, owner_id=user["id"])
	db_session.add_all([project, group])
	await db_session.commit()
	await db_session.refresh(project)
	await db_session.refresh(group)

	resp = await client.put(
		f"/v1/projects/{project.id}/acl",
		json=[
			{"group_id": group.id, "role": "viewer"},
			{"group_id": group.id, "role": "admin"},
		],
		headers=headers,
	)
	assert resp.status_code == 422
	assert resp.json()["detail"] == "Duplicate principal entries are not allowed"


@pytest.mark.asyncio
async def test_acl_service_rejects_missing_principal(db_session: AsyncSession) -> None:
	from fastapi import HTTPException

	from api.models.acl import AccessRole
	from api.schemas.acl import AccessControlEntryCreate
	from api.v1.service.acl import _ensure_principal_exists

	entry = AccessControlEntryCreate.model_construct(
		user_id=None,
		group_id=None,
		agent_id=None,
		role=AccessRole.VIEWER,
		metadata={},
	)

	with pytest.raises(HTTPException) as exc:
		await _ensure_principal_exists(entry, db_session)

	assert exc.value.status_code == 422
	assert exc.value.detail == "principal not set"


@pytest.mark.asyncio
async def test_project_acl_not_found_returns_404(
	client: AsyncClient,
	user_auth: dict[str, object],
) -> None:
	headers = user_auth["headers"]
	assert isinstance(headers, dict)
	resp = await client.get(f"/v1/projects/{new_typeid('proj')}/acl", headers=headers)
	assert resp.status_code == 404
	assert resp.json()["detail"] == "Project not found"
