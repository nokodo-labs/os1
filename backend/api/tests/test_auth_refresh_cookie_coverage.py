"""Coverage-focused tests for refresh-cookie paths."""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from httpx import AsyncClient

from api.v1.schemas.token import Token


@pytest.mark.asyncio
async def test_refresh_missing_cookie_401(
	client: AsyncClient,
) -> None:
	resp = await client.post("/v1/auth/refresh")
	assert resp.status_code == 401


@pytest.mark.asyncio
async def test_refresh_clears_cookie_on_flag(
	client: AsyncClient,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	cleared = {"called": False}

	def _mark_cleared(_response) -> None:
		cleared["called"] = True

	monkeypatch.setattr(
		"api.v1.routers.auth._clear_refresh_cookie",
		_mark_cleared,
	)

	async def _raise(_refresh_token: str, _session: object) -> Token:
		raise HTTPException(
			status_code=401,
			detail="x",
			headers={"X-Clear-Refresh-Cookie": "true"},
		)

	monkeypatch.setattr(
		"api.v1.service.auth.refresh_token_for_user",
		_raise,
	)

	resp = await client.post(
		"/v1/auth/refresh",
		cookies={"refresh_token": "r"},
	)
	assert resp.status_code == 401
	assert cleared["called"] is True


@pytest.mark.asyncio
async def test_refresh_sets_cookie_on_success(
	client: AsyncClient,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	async def _ok(_refresh_token: str, _session: object) -> Token:
		return Token(access_token="a", token_type="bearer", refresh_token="r2")

	monkeypatch.setattr(
		"api.v1.service.auth.refresh_token_for_user",
		_ok,
	)

	resp = await client.post(
		"/v1/auth/refresh",
		cookies={"refresh_token": "r"},
	)
	assert resp.status_code == 200
	assert resp.json()["access_token"] == "a"
	assert "set-cookie" in resp.headers
	assert "refresh_token" in resp.headers["set-cookie"]


@pytest.mark.asyncio
async def test_refresh_does_not_clear_cookie_without_header(
	client: AsyncClient,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	cleared = {"called": False}

	def _mark_cleared(_response) -> None:
		cleared["called"] = True

	monkeypatch.setattr(
		"api.v1.routers.auth._clear_refresh_cookie",
		_mark_cleared,
	)

	async def _raise(_refresh_token: str, _session: object) -> Token:
		raise HTTPException(status_code=401, detail="x")

	monkeypatch.setattr(
		"api.v1.service.auth.refresh_token_for_user",
		_raise,
	)

	resp = await client.post(
		"/v1/auth/refresh",
		cookies={"refresh_token": "r"},
	)
	assert resp.status_code == 401
	assert cleared["called"] is False


@pytest.mark.asyncio
async def test_refresh_does_not_set_cookie_when_refresh_token_missing(
	client: AsyncClient,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	async def _ok(_refresh_token: str, _session: object) -> Token:
		return Token(access_token="a", token_type="bearer", refresh_token=None)

	monkeypatch.setattr(
		"api.v1.service.auth.refresh_token_for_user",
		_ok,
	)

	resp = await client.post(
		"/v1/auth/refresh",
		cookies={"refresh_token": "r"},
	)
	assert resp.status_code == 200
	assert "set-cookie" not in resp.headers


@pytest.mark.asyncio
async def test_login_does_not_set_cookie_when_refresh_token_missing(
	client: AsyncClient,
	monkeypatch: pytest.MonkeyPatch,
	user_auth: dict[str, object],
) -> None:
	user_email = user_auth["email"]
	user_password = user_auth["password"]
	assert isinstance(user_email, str)
	assert isinstance(user_password, str)

	async def _ok(_user) -> Token:
		return Token(access_token="a", token_type="bearer", refresh_token=None)

	monkeypatch.setattr(
		"api.v1.service.auth.create_token_pair",
		_ok,
	)

	resp = await client.post(
		"/v1/auth/login/access-token",
		data={"username": user_email, "password": user_password},
	)
	assert resp.status_code == 200
	assert "set-cookie" not in resp.headers


@pytest.mark.asyncio
async def test_logout_clears_cookie(
	client: AsyncClient,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	cleared = {"called": False}

	def _mark_cleared(_response) -> None:
		cleared["called"] = True

	monkeypatch.setattr(
		"api.v1.routers.auth._clear_refresh_cookie",
		_mark_cleared,
	)

	resp = await client.post("/v1/auth/logout")
	assert resp.status_code == 204
	assert cleared["called"] is True


@pytest.mark.asyncio
async def test_logout_sets_clear_cookie_header(client: AsyncClient) -> None:
	resp = await client.post("/v1/auth/logout")
	assert resp.status_code == 204
	assert "set-cookie" in resp.headers
	assert "refresh_token" in resp.headers["set-cookie"]
