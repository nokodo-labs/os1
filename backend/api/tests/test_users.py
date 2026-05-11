"""Tests for user endpoints."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi import HTTPException
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.block import Block
from api.models.friendship import Friendship, FriendshipStatus
from api.schemas.user import UserCreate
from api.v1.service import users as user_service
from api.v1.service.auth import Principal
from nokodo_ai.utils.typeid import new_typeid


def auth_headers(auth: dict[str, object]) -> dict[str, str]:
	headers = auth["headers"]
	assert isinstance(headers, dict)
	result: dict[str, str] = {}
	for key, value in headers.items():
		assert isinstance(key, str)
		assert isinstance(value, str)
		result[key] = value
	return result


def auth_user(auth: dict[str, object]) -> dict[str, object]:
	user = auth["user"]
	assert isinstance(user, dict)
	result: dict[str, object] = {}
	for key, value in user.items():
		assert isinstance(key, str)
		result[key] = value
	return result


@pytest.mark.asyncio
async def test_create_user(client: AsyncClient) -> None:
	"""Test creating a new user."""
	bootstrap_admin = {
		"email": "admin@example.com",
		"username": "admin_test",
		"password": "testpassword123",
		"is_superuser": True,
	}
	admin_resp = await client.post("/v1/users", json=bootstrap_admin)
	assert admin_resp.status_code == 201

	user_data = {
		"email": "test@example.com",
		"username": "test_user",
		"password": "testpassword123",
	}
	response = await client.post("/v1/users", json=user_data)
	assert response.status_code == 201

	data = response.json()
	assert data["email"] == user_data["email"]
	assert "id" in data
	assert "created_at" in data


@pytest.mark.asyncio
async def test_get_users(client: AsyncClient, admin_auth: dict[str, object]) -> None:
	"""Test retrieving list of users."""
	headers = auth_headers(admin_auth)
	response = await client.get("/v1/users", headers=headers)
	assert response.status_code == 200
	assert isinstance(response.json(), list)


@pytest.mark.asyncio
async def test_get_users_sorting(
	client: AsyncClient, admin_auth: dict[str, object]
) -> None:
	"""List users supports server-side sort_by + sort_dir."""
	headers = auth_headers(admin_auth)

	# Use lowercase alnum-only local parts so ordering is stable across DB collations.
	created_emails = [
		"asort1@example.com",
		"asort2@example.com",
		"bsort1@example.com",
		"bsort2@example.com",
	]

	# Create out-of-order so the test catches missing sorting.
	for email in [
		"bsort2@example.com",
		"asort1@example.com",
		"bsort1@example.com",
		"asort2@example.com",
	]:
		resp = await client.post(
			"/v1/users",
			json={"email": email, "username": email.split("@")[0], "password": "pw"},
			headers=headers,
		)
		assert resp.status_code == 201

	response = await client.get(
		"/v1/users",
		headers=headers,
		params={"sort_by": "email", "sort_dir": "asc", "limit": 200},
	)
	assert response.status_code == 200
	emails = [u["email"] for u in response.json()]

	# Compare only the emails created in this test.
	created = set(created_emails)
	filtered = [email for email in emails if email in created]
	assert filtered == sorted(created_emails)


@pytest.mark.asyncio
async def test_get_user_by_id(
	client: AsyncClient,
	user_auth: dict[str, object],
) -> None:
	"""Test retrieving a specific user by ID."""
	user = auth_user(user_auth)
	user_id = user["id"]
	assert isinstance(user_id, str)
	user_email = user["email"]
	assert isinstance(user_email, str)

	# Then retrieve it
	headers = auth_headers(user_auth)
	response = await client.get(f"/v1/users/{user_id}", headers=headers)
	assert response.status_code == 200

	data = response.json()
	assert data["id"] == user_id
	assert data["email"] == user_email


@pytest.mark.asyncio
async def test_get_nonexistent_user(
	client: AsyncClient, admin_auth: dict[str, object]
) -> None:
	"""Test retrieving a user that doesn't exist."""
	headers = auth_headers(admin_auth)
	response = await client.get(f"/v1/users/{new_typeid('user')}", headers=headers)
	assert response.status_code == 404


@pytest.mark.asyncio
async def test_bulk_user_lookup_omits_inaccessible_users(
	client: AsyncClient,
	admin_auth: dict[str, object],
	user_auth: dict[str, object],
) -> None:
	"""bulk lookup returns active unblocked users with privacy redaction."""
	admin_headers = auth_headers(admin_auth)
	user_headers = auth_headers(user_auth)
	current_user = auth_user(user_auth)
	other_resp = await client.post(
		"/v1/users",
		headers=admin_headers,
		json={
			"email": "bulk-private@example.com",
			"username": "bulk_private",
			"password": "password",
			"is_superuser": False,
		},
	)
	assert other_resp.status_code == 201
	other_id = other_resp.json()["id"]

	response = await client.post(
		"/v1/users/bulk",
		headers=user_headers,
		json={"user_ids": [current_user["id"], other_id]},
	)

	assert response.status_code == 200
	data = response.json()
	assert [user["id"] for user in data] == [current_user["id"], other_id]
	assert "email" not in data[0]
	assert "email" not in data[1]


@pytest.mark.asyncio
async def test_admin_bulk_user_lookup_returns_requested_users(
	client: AsyncClient,
	admin_auth: dict[str, object],
) -> None:
	"""admins can resolve requested user summaries in bulk."""
	headers = auth_headers(admin_auth)
	admin_user = auth_user(admin_auth)
	other_resp = await client.post(
		"/v1/users",
		headers=headers,
		json={
			"email": "bulk-admin-visible@example.com",
			"username": "bulk_admin_visible",
			"password": "password",
			"is_superuser": False,
		},
	)
	assert other_resp.status_code == 201

	response = await client.post(
		"/v1/users/bulk",
		headers=headers,
		json={"user_ids": [other_resp.json()["id"], admin_user["id"]]},
	)

	assert response.status_code == 200
	assert [user["id"] for user in response.json()] == [
		other_resp.json()["id"],
		admin_user["id"],
	]


@pytest.mark.asyncio
async def test_admin_user_list_q_matches_exact_id_only(
	client: AsyncClient,
	admin_auth: dict[str, object],
) -> None:
	"""admin q filters match IDs exactly, not by substring."""
	headers = auth_headers(admin_auth)
	unique = uuid4().hex[:10]
	other_resp = await client.post(
		"/v1/users",
		headers=headers,
		json={
			"email": f"exact-id-{unique}@example.com",
			"username": f"exactid{unique}",
			"password": "password",
			"is_superuser": False,
		},
	)
	assert other_resp.status_code == 201
	target = other_resp.json()

	exact_resp = await client.get(
		"/v1/users",
		headers=headers,
		params={"q": target["id"]},
	)
	assert exact_resp.status_code == 200
	assert target["id"] in [user["id"] for user in exact_resp.json()]

	partial_resp = await client.get(
		"/v1/users",
		headers=headers,
		params={"q": target["id"][-10:]},
	)
	assert partial_resp.status_code == 200
	assert target["id"] not in [user["id"] for user in partial_resp.json()]


@pytest.mark.asyncio
async def test_user_search_respects_email_discoverability(
	client: AsyncClient,
	admin_auth: dict[str, object],
	user_auth: dict[str, object],
) -> None:
	"""email search only matches users that explicitly allow email discovery."""
	admin_headers = auth_headers(admin_auth)
	user_headers = auth_headers(user_auth)
	unique = uuid4().hex[:10]
	target_resp = await client.post(
		"/v1/users",
		headers=admin_headers,
		json={
			"email": f"hidden-email-{unique}@example.com",
			"username": f"hiddenemail{unique}",
			"password": "password",
			"is_superuser": False,
		},
	)
	assert target_resp.status_code == 201
	target = target_resp.json()

	patch_resp = await client.patch(
		f"/v1/users/{target['id']}",
		headers=admin_headers,
		json={
			"find_by_email": False,
			"privacy": {
				"allow_friend_requests": "private",
			},
		},
	)
	assert patch_resp.status_code == 200

	hidden_resp = await client.get(
		"/v1/users/search",
		headers=user_headers,
		params={"q": target["email"]},
	)
	assert hidden_resp.status_code == 200
	assert target["id"] not in [user["id"] for user in hidden_resp.json()]

	patch_resp = await client.patch(
		f"/v1/users/{target['id']}",
		headers=admin_headers,
		json={"find_by_email": True},
	)
	assert patch_resp.status_code == 200

	visible_resp = await client.get(
		"/v1/users/search",
		headers=user_headers,
		params={"q": target["email"]},
	)
	assert visible_resp.status_code == 200
	results = [user for user in visible_resp.json() if user["id"] == target["id"]]
	assert len(results) == 1
	assert results[0]["email"] is None


@pytest.mark.asyncio
async def test_admin_social_search_bypasses_profile_privacy(
	client: AsyncClient,
	admin_auth: dict[str, object],
	db_session: AsyncSession,
) -> None:
	"""admins can search and view users despite privacy or block settings."""
	admin_headers = auth_headers(admin_auth)
	admin_user = auth_user(admin_auth)
	unique = uuid4().hex[:10]
	target_resp = await client.post(
		"/v1/users",
		headers=admin_headers,
		json={
			"email": f"admin-social-hidden-{unique}@example.com",
			"username": f"adminsocial{unique}",
			"display_name": f"Admin Hidden {unique}",
			"password": "password",
			"is_superuser": False,
		},
	)
	assert target_resp.status_code == 201
	target = target_resp.json()
	patch_resp = await client.patch(
		f"/v1/users/{target['id']}",
		headers=admin_headers,
		json={
			"find_by_email": False,
			"privacy": {"real_name": "private", "bio": "private"},
		},
	)
	assert patch_resp.status_code == 200

	name_resp = await client.get(
		"/v1/users/search",
		headers=admin_headers,
		params={"q": target["display_name"]},
	)
	assert name_resp.status_code == 200
	name_results = [user for user in name_resp.json() if user["id"] == target["id"]]
	assert len(name_results) == 1
	assert name_results[0]["display_name"] == target["display_name"]
	assert name_results[0]["email"] == target["email"]

	email_resp = await client.get(
		"/v1/users/search",
		headers=admin_headers,
		params={"q": target["email"]},
	)
	assert email_resp.status_code == 200
	assert target["id"] in [user["id"] for user in email_resp.json()]

	username_resp = await client.get(
		"/v1/users/search",
		headers=admin_headers,
		params={"q": target["username"]},
	)
	assert username_resp.status_code == 200
	username_results = [
		user for user in username_resp.json() if user["id"] == target["id"]
	]
	assert len(username_results) == 1
	assert username_results[0]["display_name"] == target["display_name"]
	assert username_results[0]["email"] == target["email"]

	db_session.add(
		Block(blocker_id=str(target["id"]), blocked_id=str(admin_user["id"]))
	)
	await db_session.commit()
	blocked_resp = await client.get(
		"/v1/users/search",
		headers=admin_headers,
		params={"q": target["username"]},
	)
	assert blocked_resp.status_code == 200
	blocked_results = [
		user for user in blocked_resp.json() if user["id"] == target["id"]
	]
	assert len(blocked_results) == 1
	assert blocked_results[0]["display_name"] == target["display_name"]
	assert blocked_results[0]["email"] == target["email"]


@pytest.mark.asyncio
async def test_user_search_username_is_baseline_when_profile_is_private(
	client: AsyncClient,
	admin_auth: dict[str, object],
	user_auth: dict[str, object],
) -> None:
	"""username search is available even when other discovery is private."""
	admin_headers = auth_headers(admin_auth)
	user_headers = auth_headers(user_auth)
	unique = uuid4().hex[:10]
	target_resp = await client.post(
		"/v1/users",
		headers=admin_headers,
		json={
			"email": f"baseline-private-{unique}@example.com",
			"username": f"baselineprivate{unique}",
			"display_name": f"Baseline Private {unique}",
			"password": "password",
			"is_superuser": False,
		},
	)
	assert target_resp.status_code == 201
	target = target_resp.json()

	patch_resp = await client.patch(
		f"/v1/users/{target['id']}",
		headers=admin_headers,
		json={
			"find_by_email": False,
			"privacy": {
				"real_name": "private",
				"bio": "private",
				"email": "private",
				"allow_friend_requests": "private",
			},
		},
	)
	assert patch_resp.status_code == 200

	response = await client.get(
		"/v1/users/search",
		headers=user_headers,
		params={"q": target["username"]},
	)
	assert response.status_code == 200
	results = [user for user in response.json() if user["id"] == target["id"]]
	assert len(results) == 1
	assert results[0]["display_name"] is None
	assert results[0]["email"] is None


@pytest.mark.asyncio
async def test_user_search_respects_bio_privacy(
	client: AsyncClient,
	admin_auth: dict[str, object],
	user_auth: dict[str, object],
) -> None:
	"""bio text is searchable only when the bio field is visible."""
	admin_headers = auth_headers(admin_auth)
	user_headers = auth_headers(user_auth)
	unique = uuid4().hex[:10]
	target_resp = await client.post(
		"/v1/users",
		headers=admin_headers,
		json={
			"email": f"bio-search-{unique}@example.com",
			"username": f"biosearch{unique}",
			"bio": f"needle biography {unique}",
			"password": "password",
			"is_superuser": False,
		},
	)
	assert target_resp.status_code == 201
	target = target_resp.json()
	patch_resp = await client.patch(
		f"/v1/users/{target['id']}",
		headers=admin_headers,
		json={"bio": f"needle biography {unique}"},
	)
	assert patch_resp.status_code == 200

	visible_resp = await client.get(
		"/v1/users/search",
		headers=user_headers,
		params={"q": f"needle biography {unique}"},
	)
	assert visible_resp.status_code == 200
	assert target["id"] in [user["id"] for user in visible_resp.json()]

	patch_resp = await client.patch(
		f"/v1/users/{target['id']}",
		headers=admin_headers,
		json={"privacy": {"bio": "private"}},
	)
	assert patch_resp.status_code == 200

	hidden_resp = await client.get(
		"/v1/users/search",
		headers=user_headers,
		params={"q": f"needle biography {unique}"},
	)
	assert hidden_resp.status_code == 200
	assert target["id"] not in [user["id"] for user in hidden_resp.json()]


@pytest.mark.asyncio
async def test_friend_email_visibility_is_privacy_controlled(
	client: AsyncClient,
	admin_auth: dict[str, object],
	user_auth: dict[str, object],
	db_session: AsyncSession,
) -> None:
	"""accepted friends only see email when the target's email setting allows it."""
	admin_headers = auth_headers(admin_auth)
	user_headers = auth_headers(user_auth)
	current_user = auth_user(user_auth)
	unique = uuid4().hex[:10]
	target_resp = await client.post(
		"/v1/users",
		headers=admin_headers,
		json={
			"email": f"friend-email-{unique}@example.com",
			"username": f"friendemail{unique}",
			"password": "password",
			"is_superuser": False,
		},
	)
	assert target_resp.status_code == 201
	target = target_resp.json()
	db_session.add(
		Friendship(
			requester_id=str(current_user["id"]),
			addressee_id=str(target["id"]),
			status=FriendshipStatus.ACCEPTED,
			accepted_at=datetime.now(UTC),
		)
	)
	await db_session.commit()

	private_resp = await client.get(
		f"/v1/users/{current_user['id']}/friends",
		headers=user_headers,
	)
	assert private_resp.status_code == 200
	private_results = [
		user for user in private_resp.json() if user["id"] == target["id"]
	]
	assert len(private_results) == 1
	assert private_results[0]["email"] is None

	patch_resp = await client.patch(
		f"/v1/users/{target['id']}",
		headers=admin_headers,
		json={"privacy": {"email": "friends"}},
	)
	assert patch_resp.status_code == 200

	visible_resp = await client.get(
		f"/v1/users/{current_user['id']}/friends",
		headers=user_headers,
	)
	assert visible_resp.status_code == 200
	visible_results = [
		user for user in visible_resp.json() if user["id"] == target["id"]
	]
	assert len(visible_results) == 1
	assert visible_results[0]["email"] == target["email"]


@pytest.mark.asyncio
async def test_user_search_respects_display_name_privacy_and_friendship(
	client: AsyncClient,
	admin_auth: dict[str, object],
	user_auth: dict[str, object],
	db_session: AsyncSession,
) -> None:
	"""display names are searchable only when visible to the requester."""
	admin_headers = auth_headers(admin_auth)
	user_headers = auth_headers(user_auth)
	current_user = auth_user(user_auth)
	unique = uuid4().hex[:10]
	target_resp = await client.post(
		"/v1/users",
		headers=admin_headers,
		json={
			"email": f"display-private-{unique}@example.com",
			"username": f"displayprivate{unique}",
			"display_name": f"Private Name {unique}",
			"password": "password",
			"is_superuser": False,
		},
	)
	assert target_resp.status_code == 201
	target = target_resp.json()

	patch_resp = await client.patch(
		f"/v1/users/{target['id']}",
		headers=admin_headers,
		json={"privacy": {"real_name": "private"}},
	)
	assert patch_resp.status_code == 200

	private_name_resp = await client.get(
		"/v1/users/search",
		headers=user_headers,
		params={"q": target["display_name"]},
	)
	assert private_name_resp.status_code == 200
	assert target["id"] not in [user["id"] for user in private_name_resp.json()]

	username_resp = await client.get(
		"/v1/users/search",
		headers=user_headers,
		params={"q": target["username"]},
	)
	assert username_resp.status_code == 200
	username_results = [
		user for user in username_resp.json() if user["id"] == target["id"]
	]
	assert len(username_results) == 1
	assert username_results[0]["display_name"] is None

	patch_resp = await client.patch(
		f"/v1/users/{target['id']}",
		headers=admin_headers,
		json={"privacy": {"real_name": "friends"}},
	)
	assert patch_resp.status_code == 200
	db_session.add(
		Friendship(
			requester_id=str(current_user["id"]),
			addressee_id=str(target["id"]),
			status=FriendshipStatus.ACCEPTED,
			accepted_at=datetime.now(UTC),
		)
	)
	await db_session.commit()

	friend_name_resp = await client.get(
		"/v1/users/search",
		headers=user_headers,
		params={"q": target["display_name"]},
	)
	assert friend_name_resp.status_code == 200
	friend_results = [
		user for user in friend_name_resp.json() if user["id"] == target["id"]
	]
	assert len(friend_results) == 1
	assert friend_results[0]["display_name"] == target["display_name"]


@pytest.mark.asyncio
async def test_user_search_excludes_blocked_users(
	client: AsyncClient,
	admin_auth: dict[str, object],
	user_auth: dict[str, object],
	db_session: AsyncSession,
) -> None:
	"""blocked users are excluded from user discovery."""
	admin_headers = auth_headers(admin_auth)
	user_headers = auth_headers(user_auth)
	current_user = auth_user(user_auth)
	unique = uuid4().hex[:10]
	target_resp = await client.post(
		"/v1/users",
		headers=admin_headers,
		json={
			"email": f"blocked-{unique}@example.com",
			"username": f"blocked{unique}",
			"password": "password",
			"is_superuser": False,
		},
	)
	assert target_resp.status_code == 201
	target = target_resp.json()
	db_session.add(
		Block(blocker_id=str(target["id"]), blocked_id=str(current_user["id"]))
	)
	await db_session.commit()

	response = await client.get(
		"/v1/users/search",
		headers=user_headers,
		params={"q": target["username"]},
	)
	assert response.status_code == 200
	assert target["id"] not in [user["id"] for user in response.json()]


@pytest.mark.asyncio
async def test_create_duplicate_user(
	client: AsyncClient,
	admin_auth: dict[str, object],
) -> None:
	"""Test creating a user with an existing email."""
	user_data = {
		"email": "duplicate@example.com",
		"username": "duplicate_test",
		"password": "password",
	}
	headers = auth_headers(admin_auth)
	resp1 = await client.post("/v1/users", json=user_data, headers=headers)
	assert resp1.status_code == 201

	# Try to create duplicate
	resp2 = await client.post("/v1/users", json=user_data, headers=headers)
	assert resp2.status_code == 400
	assert resp2.json()["detail"] == "email already registered"


@pytest.mark.asyncio
async def test_service_create_user(db_session: AsyncSession) -> None:
	"""Test creating a user directly via service."""
	await user_service.create_user(
		UserCreate(
			email="bootstrap@example.com",
			username="bootstrap_test",
			password="password123",
			is_superuser=True,
		),
		db_session,
	)
	user_in = UserCreate(
		email="service_test@example.com",
		username="service_test",
		password="password123",
	)
	user = await user_service.create_user(user_in, db_session)
	assert user.email == user_in.email
	assert user.id is not None


@pytest.mark.asyncio
async def test_service_get_user(db_session: AsyncSession) -> None:
	"""Test getting a user directly via service."""
	# Create user first
	admin = await user_service.create_user(
		UserCreate(
			email="admin_get@example.com",
			username="admin_get",
			password="password123",
			is_superuser=True,
		),
		db_session,
	)
	admin_principal = Principal(user=admin, group_ids=(), permissions=frozenset())

	user_in = UserCreate(
		email="service_get@example.com", username="service_get", password="password123"
	)
	created_user = await user_service.create_user(
		user_in,
		db_session,
		principal=admin_principal,
	)

	# Get user
	fetched_user = await user_service.get_user(
		created_user.id,
		db_session,
		principal=admin_principal,
	)
	assert fetched_user.id == created_user.id
	assert fetched_user.email == created_user.email


@pytest.mark.asyncio
async def test_service_list_users(db_session: AsyncSession) -> None:
	"""Test listing users directly via service."""
	admin = await user_service.create_user(
		UserCreate(
			email="admin_list@example.com",
			username="admin_list",
			password="password123",
			is_superuser=True,
		),
		db_session,
	)
	admin_principal = Principal(user=admin, group_ids=(), permissions=frozenset())

	for i in range(2):
		user_in = UserCreate(
			email=f"list_{i}@example.com",
			username=f"list_{i}_test",
			password="password123",
		)
		await user_service.create_user(
			user_in,
			db_session,
			principal=Principal(user=admin, group_ids=(), permissions=frozenset()),
		)

	users = await user_service.list_users(db_session, principal=admin_principal)
	assert len(users) >= 3


@pytest.mark.asyncio
async def test_service_get_user_not_found(db_session: AsyncSession) -> None:
	"""Test getting a non-existent user directly via service."""
	admin = await user_service.create_user(
		UserCreate(
			email="admin_nf@example.com",
			username="admin_nf_test",
			password="password123",
			is_superuser=True,
		),
		db_session,
	)
	admin_principal = Principal(user=admin, group_ids=(), permissions=frozenset())
	with pytest.raises(HTTPException) as exc:
		await user_service.get_user(
			new_typeid("user"),
			db_session,
			principal=admin_principal,
		)
	assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_service_create_duplicate_user(db_session: AsyncSession) -> None:
	"""Test creating a duplicate user directly via service."""
	admin = await user_service.create_user(
		UserCreate(
			email="admin_dup@example.com",
			username="admin_dup",
			password="password123",
			is_superuser=True,
		),
		db_session,
	)
	user_in = UserCreate(
		email="duplicate_service@example.com",
		username="duplicate_svc",
		password="password123",
	)
	await user_service.create_user(
		user_in,
		db_session,
		principal=Principal(user=admin, group_ids=(), permissions=frozenset()),
	)

	with pytest.raises(HTTPException) as exc:
		await user_service.create_user(
			user_in,
			db_session,
			principal=Principal(user=admin, group_ids=(), permissions=frozenset()),
		)
	assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_user_service_guards(db_session: AsyncSession) -> None:
	"""Non-admin principals should hit guardrails for list/get."""
	admin = await user_service.create_user(
		UserCreate(
			email="guard-admin@example.com",
			username="guard_admin",
			password="pw",
			is_superuser=True,
		),
		db_session,
	)
	normal_user = await user_service.create_user(
		UserCreate(email="guard@example.com", username="guard_test", password="pw"),
		db_session,
		principal=Principal(user=admin, group_ids=(), permissions=frozenset()),
	)
	principal = Principal(user=normal_user, group_ids=(), permissions=frozenset())

	with pytest.raises(HTTPException):
		await user_service.list_users(db_session, principal=principal)

	with pytest.raises(HTTPException):
		await user_service.get_user(new_typeid("user"), db_session, principal=principal)


@pytest.mark.asyncio
async def test_unauthenticated_create_never_superuser(db_session: AsyncSession) -> None:
	"""Unauthenticated user creation should never produce a superuser."""
	# first user must request superuser explicitly
	with pytest.raises(HTTPException) as exc:
		await user_service.create_user(
			UserCreate(
				email="bootstrap-denied@example.com",
				username="bootstrap_denied",
				password="pw",
			),
			db_session,
		)
	assert exc.value.status_code == 400
	assert isinstance(exc.value.detail, dict)
	assert exc.value.detail.get("code") == "bootstrap_required"
	assert "console_origin" in exc.value.detail

	bootstrap = await user_service.create_user(
		UserCreate(
			email="bootstrap@example.com",
			username="bootstrap_test",
			password="pw",
			is_superuser=True,
		),
		db_session,
	)
	assert bootstrap.is_superuser is True
	assert bootstrap.is_active is True

	# unauthenticated create: even if is_superuser=True is passed,
	# result is a regular user
	sneaky = await user_service.create_user(
		UserCreate(
			email="sneaky@example.com",
			username="sneaky_test",
			password="pw",
			is_superuser=True,
		),
		db_session,
		principal=None,
	)
	assert sneaky.is_superuser is False
	assert sneaky.is_active is True

	# superuser can create another superuser
	new_admin = await user_service.create_user(
		UserCreate(
			email="new-admin@example.com",
			username="new_admin",
			password="pw",
			is_superuser=True,
		),
		db_session,
		principal=Principal(user=bootstrap, group_ids=(), permissions=frozenset()),
	)
	assert new_admin.is_superuser is True
