"""Tests for the Open WebUI integration service."""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.user import User
from api.permissions import ActionPermission, DefaultResourceAccess
from api.v1.service.auth import Principal
from api.v1.service.integrations import open_webui


def _principal(*permissions: ActionPermission) -> Principal:
	user = User(
		email="open-webui-integration@example.com",
		username="open_webui_integration",
		hashed_password="pw",
		is_active=True,
	)
	return Principal(
		user=user,
		group_ids=(),
		role_ids=(),
		permissions=frozenset(permission.value for permission in permissions),
		role_resource_defaults=DefaultResourceAccess(),
	)


def test_open_webui_sources_require_import_capability() -> None:
	with pytest.raises(HTTPException) as exc:
		open_webui.list_sources(_principal())

	assert exc.value.status_code == 403


def test_open_webui_sources_allow_memory_import_capability() -> None:
	sources = open_webui.list_sources(_principal(ActionPermission.MEMORIES_CREATE))

	assert isinstance(sources.enabled, bool)


@pytest.mark.asyncio
async def test_open_webui_chat_import_requires_thread_permission(
	db_session: AsyncSession,
) -> None:
	with pytest.raises(HTTPException) as exc:
		await open_webui.import_from_open_webui(
			deployment_origin="https://open-webui.example.com",
			credential="token",
			include_chats=True,
			include_memories=False,
			session=db_session,
			principal=_principal(ActionPermission.MEMORIES_CREATE),
		)

	assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_open_webui_memory_import_requires_memory_permission(
	db_session: AsyncSession,
) -> None:
	with pytest.raises(HTTPException) as exc:
		await open_webui.import_from_open_webui(
			deployment_origin="https://open-webui.example.com",
			credential="token",
			include_chats=False,
			include_memories=True,
			session=db_session,
			principal=_principal(ActionPermission.THREADS_CREATE),
		)

	assert exc.value.status_code == 403
