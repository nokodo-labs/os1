"""access level resolver API tests."""

import pytest
from httpx import AsyncClient

from nokodo_ai.utils.typeid import new_typeid


async def _create_user(
	client: AsyncClient,
	admin_headers: dict[str, str],
	prefix: str,
) -> tuple[dict[str, object], dict[str, str]]:
	email = f"{prefix}-{new_typeid('user')}@example.com"
	username = f"{prefix}{new_typeid('user')[-12:]}"
	password = "password"
	user_resp = await client.post(
		"/v1/users",
		headers=admin_headers,
		json={
			"email": email,
			"username": username,
			"password": password,
			"is_superuser": False,
		},
	)
	assert user_resp.status_code == 201
	user = user_resp.json()

	login_resp = await client.post(
		"/v1/auth/login/access-token",
		data={"username": email, "password": password},
	)
	assert login_resp.status_code == 200
	token = login_resp.json()["access_token"]
	return user, {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_resolve_access_levels_gates_self_by_read_access(
	client: AsyncClient,
	admin_auth: dict[str, object],
	user_auth: dict[str, object],
) -> None:
	owner = user_auth["user"]
	owner_headers = user_auth["headers"]
	admin_headers = admin_auth["headers"]
	assert isinstance(owner, dict)
	assert isinstance(owner_headers, dict)
	assert isinstance(admin_headers, dict)

	project_resp = await client.post(
		"/v1/projects",
		headers=owner_headers,
		json={"name": "resolver project"},
	)
	assert project_resp.status_code == 201
	project_id = project_resp.json()["id"]

	editor, editor_headers = await _create_user(client, admin_headers, "editor")
	outsider, outsider_headers = await _create_user(client, admin_headers, "outsider")

	acl_resp = await client.put(
		f"/v1/projects/{project_id}/access/rules",
		headers=owner_headers,
		json=[{"subject_user_id": editor["id"], "level": "editor"}],
	)
	assert acl_resp.status_code == 200

	editor_resp = await client.post(
		f"/v1/projects/{project_id}/access/resolve",
		headers=editor_headers,
		json={
			"subject_user_ids": [editor["id"]],
		},
	)
	assert editor_resp.status_code == 200
	assert editor_resp.json() == [
		{
			"resource_type": "project",
			"resource_id": project_id,
			"subject": "user",
			"user_id": editor["id"],
			"level": "editor",
		}
	]

	# no access at all: the resource is concealed rather than refused
	outsider_resp = await client.post(
		f"/v1/projects/{project_id}/access/resolve",
		headers=outsider_headers,
		json={
			"subject_user_ids": [outsider["id"]],
		},
	)
	assert outsider_resp.status_code == 404


@pytest.mark.asyncio
async def test_resolve_access_levels_requires_a_named_grant_for_other_subjects(
	client: AsyncClient,
	admin_auth: dict[str, object],
	user_auth: dict[str, object],
) -> None:
	"""naming users needs a NAMED grant - any level, but never link-only."""
	owner = user_auth["user"]
	owner_headers = user_auth["headers"]
	admin_headers = admin_auth["headers"]
	assert isinstance(owner, dict)
	assert isinstance(owner_headers, dict)
	assert isinstance(admin_headers, dict)

	project_resp = await client.post(
		"/v1/projects",
		headers=owner_headers,
		json={"name": "bulk resolver project"},
	)
	assert project_resp.status_code == 201
	project_id = project_resp.json()["id"]

	editor, editor_headers = await _create_user(client, admin_headers, "editor")
	outsider, outsider_headers = await _create_user(client, admin_headers, "outsider")

	acl_resp = await client.put(
		f"/v1/projects/{project_id}/access/rules",
		headers=owner_headers,
		json=[{"subject_user_id": editor["id"], "level": "editor"}],
	)
	assert acl_resp.status_code == 200

	# a named grant of any level resolves other subjects
	named_resp = await client.post(
		f"/v1/projects/{project_id}/access/resolve",
		headers=editor_headers,
		json={
			"subject_user_ids": [owner["id"]],
		},
	)
	assert named_resp.status_code == 200
	assert named_resp.json() == [
		{
			"resource_type": "project",
			"resource_id": project_id,
			"subject": "user",
			"user_id": owner["id"],
			"level": "admin",
		}
	]

	# no grant at all: concealed, not refused (there is no link either)
	forbidden_resp = await client.post(
		f"/v1/projects/{project_id}/access/resolve",
		headers=outsider_headers,
		json={
			"subject_user_ids": [owner["id"]],
		},
	)
	assert forbidden_resp.status_code == 404

	owner_resp = await client.post(
		f"/v1/projects/{project_id}/access/resolve",
		headers=owner_headers,
		json={
			"subject_user_ids": [owner["id"], editor["id"], outsider["id"]],
		},
	)
	assert owner_resp.status_code == 200
	assert owner_resp.json() == [
		{
			"resource_type": "project",
			"resource_id": project_id,
			"subject": "user",
			"user_id": owner["id"],
			"level": "admin",
		},
		{
			"resource_type": "project",
			"resource_id": project_id,
			"subject": "user",
			"user_id": editor["id"],
			"level": "editor",
		},
		{
			"resource_type": "project",
			"resource_id": project_id,
			"subject": "user",
			"user_id": outsider["id"],
			"level": None,
		},
	]

	unknown_id = new_typeid("user")
	unknown_resp = await client.post(
		f"/v1/projects/{project_id}/access/resolve",
		headers=owner_headers,
		json={"subject_user_ids": [unknown_id]},
	)
	assert unknown_resp.status_code == 200
	assert unknown_resp.json() == [
		{
			"resource_type": "project",
			"resource_id": project_id,
			"subject": "user",
			"user_id": unknown_id,
			"level": None,
		}
	]


@pytest.mark.asyncio
async def test_link_visitor_cannot_list_thread_rules(
	client: AsyncClient,
	admin_auth: dict[str, object],
	user_auth: dict[str, object],
) -> None:
	"""THREAD's acl_list_visibility is READER, so only the link exclusion gates.

	on PROJECT the ADMIN visibility masks the link arm; a thread is where a
	link visitor would otherwise enumerate every named subject.
	"""
	owner = user_auth["user"]
	owner_headers = user_auth["headers"]
	admin_headers = admin_auth["headers"]
	assert isinstance(owner, dict)
	assert isinstance(owner_headers, dict)
	assert isinstance(admin_headers, dict)

	thread_resp = await client.post(
		"/v1/threads",
		headers=owner_headers,
		json={"owner_id": owner["id"], "title": "link visibility thread"},
	)
	assert thread_resp.status_code == 201
	thread_id = thread_resp.json()["id"]

	named, _ = await _create_user(client, admin_headers, "namedmember")
	visitor, visitor_headers = await _create_user(client, admin_headers, "threadlink")

	acl_resp = await client.put(
		f"/v1/threads/{thread_id}/access/rules",
		headers=owner_headers,
		json=[
			{"subject_user_id": named["id"], "level": "reader"},
			{"level": "reader"},
		],
	)
	assert acl_resp.status_code == 200

	# the link admits the visitor to the thread itself
	read_resp = await client.get(f"/v1/threads/{thread_id}", headers=visitor_headers)
	assert read_resp.status_code == 200

	# but never to the list of named subjects
	rules_resp = await client.get(
		f"/v1/threads/{thread_id}/access/rules",
		headers=visitor_headers,
	)
	assert rules_resp.status_code == 404

	# nor to any single rule
	owner_rules = await client.get(
		f"/v1/threads/{thread_id}/access/rules",
		headers=owner_headers,
	)
	assert owner_rules.status_code == 200
	rule_id = owner_rules.json()[0]["id"]
	single_resp = await client.get(
		f"/v1/threads/{thread_id}/access/rules/{rule_id}",
		headers=visitor_headers,
	)
	assert single_resp.status_code == 404

	# and never to another person's level, even at READER visibility
	other_resp = await client.post(
		f"/v1/threads/{thread_id}/access/resolve",
		headers=visitor_headers,
		json={"subject_user_ids": [named["id"]]},
	)
	assert other_resp.status_code == 403


@pytest.mark.asyncio
async def test_resolve_conceals_from_strangers_and_refuses_link_visitors(
	client: AsyncClient,
	admin_auth: dict[str, object],
	user_auth: dict[str, object],
) -> None:
	"""two tracks: 404 conceals, 403 refuses a capability.

	a caller with no access at all must not learn the resource exists; a link
	visitor already knows, so refusing them a capability is the honest answer.
	"""
	owner = user_auth["user"]
	owner_headers = user_auth["headers"]
	admin_headers = admin_auth["headers"]
	assert isinstance(owner, dict)
	assert isinstance(owner_headers, dict)
	assert isinstance(admin_headers, dict)

	project_resp = await client.post(
		"/v1/projects",
		headers=owner_headers,
		json={"name": "two track project"},
	)
	assert project_resp.status_code == 201
	project_id = project_resp.json()["id"]

	_, stranger_headers = await _create_user(client, admin_headers, "stranger")

	# no access at all: concealment
	stranger_resp = await client.post(
		f"/v1/projects/{project_id}/access/resolve",
		headers=stranger_headers,
		json={"subject_user_ids": [owner["id"]]},
	)
	assert stranger_resp.status_code == 404

	# publishing a link makes the same caller a link visitor
	acl_resp = await client.put(
		f"/v1/projects/{project_id}/access/rules",
		headers=owner_headers,
		json=[{"level": "reader"}],
	)
	assert acl_resp.status_code == 200

	link_resp = await client.post(
		f"/v1/projects/{project_id}/access/resolve",
		headers=stranger_headers,
		json={"subject_user_ids": [owner["id"]]},
	)
	assert link_resp.status_code == 403


@pytest.mark.asyncio
async def test_link_visitor_resolves_self_but_not_others_or_rules(
	client: AsyncClient,
	admin_auth: dict[str, object],
	user_auth: dict[str, object],
) -> None:
	"""a link visitor learns their OWN level and nothing else about sharing.

	`/access/resolve` answers effective access, so resolving yourself is
	admitted on identity alone - that is how a link visitor is told what they
	can do. it does NOT answer configuration: whether a link share exists is
	read from the rule list under `acl_list_visibility`, which on PROJECT is
	ADMIN, so a visitor is refused there.
	"""
	owner = user_auth["user"]
	owner_headers = user_auth["headers"]
	admin_headers = admin_auth["headers"]
	assert isinstance(owner, dict)
	assert isinstance(owner_headers, dict)
	assert isinstance(admin_headers, dict)
	project_resp = await client.post(
		"/v1/projects",
		headers=owner_headers,
		json={"name": "link resolver project"},
	)
	project_id = project_resp.json()["id"]
	visitor, visitor_headers = await _create_user(client, admin_headers, "linkvisitor")
	acl_resp = await client.put(
		f"/v1/projects/{project_id}/access/rules",
		headers=owner_headers,
		json=[{"level": "reader"}],
	)
	assert acl_resp.status_code == 200

	self_resp = await client.post(
		f"/v1/projects/{project_id}/access/resolve",
		headers=visitor_headers,
		json={"subject_user_ids": [visitor["id"]]},
	)
	assert self_resp.status_code == 200
	assert self_resp.json() == [
		{
			"resource_type": "project",
			"resource_id": project_id,
			"subject": "user",
			"user_id": visitor["id"],
			"level": "reader",
		}
	]
	others_resp = await client.post(
		f"/v1/projects/{project_id}/access/resolve",
		headers=visitor_headers,
		json={"subject_user_ids": [visitor["id"], owner["id"]]},
	)
	assert others_resp.status_code == 403
	rules_resp = await client.get(
		f"/v1/projects/{project_id}/access/rules",
		headers=visitor_headers,
	)
	assert rules_resp.status_code == 404


@pytest.mark.asyncio
async def test_individual_access_rule_routes_are_resource_scoped(
	client: AsyncClient,
	admin_auth: dict[str, object],
	user_auth: dict[str, object],
) -> None:
	owner_headers = user_auth["headers"]
	admin_headers = admin_auth["headers"]
	assert isinstance(owner_headers, dict)
	assert isinstance(admin_headers, dict)

	project_resp = await client.post(
		"/v1/projects",
		headers=owner_headers,
		json={"name": "individual rule project"},
	)
	assert project_resp.status_code == 201
	project_id = project_resp.json()["id"]

	other_project_resp = await client.post(
		"/v1/projects",
		headers=owner_headers,
		json={"name": "other individual rule project"},
	)
	assert other_project_resp.status_code == 201
	other_project_id = other_project_resp.json()["id"]

	editor, _ = await _create_user(client, admin_headers, "editor")

	create_resp = await client.post(
		f"/v1/projects/{project_id}/access/rules",
		headers=owner_headers,
		json={"subject_user_id": editor["id"], "level": "reader"},
	)
	assert create_resp.status_code == 201
	created_rule = create_resp.json()
	rule_id = created_rule["id"]
	assert created_rule["subject_user_id"] == editor["id"]

	list_resp = await client.get(
		f"/v1/projects/{project_id}/access/rules",
		headers=owner_headers,
	)
	assert list_resp.status_code == 200
	assert [rule["id"] for rule in list_resp.json()] == [rule_id]

	get_resp = await client.get(
		f"/v1/projects/{project_id}/access/rules/{rule_id}",
		headers=owner_headers,
	)
	assert get_resp.status_code == 200
	assert get_resp.json()["id"] == rule_id

	wrong_resource_resp = await client.get(
		f"/v1/projects/{other_project_id}/access/rules/{rule_id}",
		headers=owner_headers,
	)
	assert wrong_resource_resp.status_code == 404

	patch_resp = await client.patch(
		f"/v1/projects/{project_id}/access/rules/{rule_id}",
		headers=owner_headers,
		json={"level": "editor", "order_index": 2},
	)
	assert patch_resp.status_code == 200
	patched_rule = patch_resp.json()
	assert patched_rule["level"] == "editor"
	assert patched_rule["order_index"] == 2

	delete_resp = await client.delete(
		f"/v1/projects/{project_id}/access/rules/{rule_id}",
		headers=owner_headers,
	)
	assert delete_resp.status_code == 204

	final_list_resp = await client.get(
		f"/v1/projects/{project_id}/access/rules",
		headers=owner_headers,
	)
	assert final_list_resp.status_code == 200
	assert final_list_resp.json() == []
