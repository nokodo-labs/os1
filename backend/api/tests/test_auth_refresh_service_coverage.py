"""Coverage-focused tests for refresh_token_for_user service branches."""

from __future__ import annotations

import pytest
from authlib.jose import JoseError
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from api.settings import settings
from api.v1.service import auth as auth_service
from nokodo_ai.utils.security import create_jwt_token
from nokodo_ai.utils.typeid import new_typeid


@pytest.mark.asyncio
async def test_refresh_token_for_user_decode_error_raises_401(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:

	def _boom(*_args: object, **_kwargs: object) -> None:
		raise JoseError("bad")

	monkeypatch.setattr(auth_service, "decode_jwt_token", _boom)

	with pytest.raises(HTTPException) as exc:
		await auth_service.refresh_token_for_user("x", db_session)
	assert exc.value.status_code == 401
	assert exc.value.headers == {"WWW-Authenticate": "Bearer"}


@pytest.mark.asyncio
async def test_refresh_token_for_user_rejects_non_refresh_token(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:

	def _decode(*_args: object, **_kwargs: object) -> dict[str, object]:
		return {"sub": new_typeid("user"), "typ": "access"}

	monkeypatch.setattr(auth_service, "decode_jwt_token", _decode)

	with pytest.raises(HTTPException) as exc:
		await auth_service.refresh_token_for_user("x", db_session)
	assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_refresh_token_for_user_rejects_missing_sub(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:

	def _decode(*_args: object, **_kwargs: object) -> dict[str, object]:
		return {"typ": "refresh"}

	monkeypatch.setattr(auth_service, "decode_jwt_token", _decode)

	with pytest.raises(HTTPException) as exc:
		await auth_service.refresh_token_for_user("x", db_session)
	assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_refresh_token_for_user_rejects_bad_sub_prefix(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:

	def _decode(*_args: object, **_kwargs: object) -> dict[str, object]:
		return {"sub": "not-a-typeid", "typ": "refresh"}

	monkeypatch.setattr(auth_service, "decode_jwt_token", _decode)

	with pytest.raises(HTTPException) as exc:
		await auth_service.refresh_token_for_user("x", db_session)
	assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_refresh_token_for_user_signals_clear_cookie_for_missing_user(
	db_session: AsyncSession,
) -> None:

	missing_user_id = new_typeid("user")
	refresh_token = create_jwt_token(
		subject=missing_user_id,
		secret_key=settings.security.secret_key,
		algorithm=settings.security.jwt_algorithm,
		additional_claims={"typ": "refresh"},
	)

	with pytest.raises(HTTPException) as exc:
		await auth_service.refresh_token_for_user(refresh_token, db_session)
	assert exc.value.status_code == 401
	assert exc.value.headers is not None
	assert exc.value.headers.get("X-Clear-Refresh-Cookie") == "true"
