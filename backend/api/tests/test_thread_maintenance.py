from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.message import MessageType
from api.models.thread_summary import SummaryType
from api.schemas.message import MessageCreate, MessageUpdate
from api.schemas.thread import ThreadCreate
from api.schemas.user import UserCreate
from api.v1.service import thread_summaries as summary_service
from api.v1.service import threads as thread_service
from api.v1.service import users as user_service
from api.v1.service.auth import Principal
from api.v1.service.threads import maintenance as thread_maintenance_service


async def _create_user_principal(
	db_session: AsyncSession,
	email: str,
	username: str,
) -> Principal:
	user = await user_service.create_user(
		UserCreate(
			email=email,
			username=username,
			password="password123",
			is_superuser=True,
		),
		db_session,
	)
	return Principal(user=user, group_ids=(), permissions=frozenset())


@pytest.mark.asyncio
async def test_thread_maintenance_noops_when_summary_is_current(
	db_session: AsyncSession,
) -> None:
	principal = await _create_user_principal(
		db_session,
		"maintenance_current@example.com",
		"maintenance_current",
	)
	thread = await thread_service.create_thread(
		ThreadCreate(
			owner_id=principal.user.id,
			title="ready",
			tags=["planning"],
		),
		db_session,
		principal=principal,
	)
	message = await thread_service.create_message(
		thread.id,
		MessageCreate(content="hello", type=MessageType.USER),
		db_session,
		principal=principal,
	)
	await db_session.refresh(thread)
	await summary_service.create_summary(
		thread_id=thread.id,
		summary_type=SummaryType.WINDOW,
		content="current summary",
		message_count=1,
		start_message_id=message.id,
		end_message_id=message.id,
		session=db_session,
	)

	assert await thread_service.thread_needs_maintenance(thread, db_session) is False
	result = await thread_service.maintain_thread_metadata(
		thread.id,
		db_session,
		principal=principal,
	)
	assert result == {
		"thread_id": str(thread.id),
		"skipped": True,
		"reason": "up to date",
	}


@pytest.mark.asyncio
async def test_thread_maintenance_generates_metadata_and_summary_once(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	principal = await _create_user_principal(
		db_session,
		"maintenance_generate@example.com",
		"maintenance_generate",
	)
	thread = await thread_service.create_thread(
		ThreadCreate(owner_id=principal.user.id),
		db_session,
		principal=principal,
	)
	await thread_service.create_message(
		thread.id,
		MessageCreate(
			content="we decided to ship task maintenance", type=MessageType.USER
		),
		db_session,
		principal=principal,
	)
	await db_session.refresh(thread)
	calls: list[object] = []

	async def _resolve_model(
		session: AsyncSession,
		task: str,
	) -> object:
		assert task == "thread_maintenance"
		return object()

	async def _run_structured(
		chat_model: object,
		*,
		thread: object,
		json_schema: dict[str, Any],
	) -> dict[str, object]:
		calls.append(thread)
		return {
			"title": "Project Status",
			"tags": ["planning", "tasks"],
			"summary": "The active branch decided to ship task maintenance.",
		}

	monkeypatch.setattr(
		thread_maintenance_service, "resolve_task_chat_model", _resolve_model
	)
	monkeypatch.setattr(
		thread_maintenance_service, "run_chat_model_json_schema", _run_structured
	)

	result = await thread_service.maintain_thread_metadata(
		thread.id,
		db_session,
		principal=principal,
	)
	await db_session.refresh(thread)
	summaries = await summary_service.list_active_summaries(thread.id, db_session)

	assert len(calls) == 1
	assert result["metadata_updated"] is True
	assert result["summary_updated"] is True
	assert thread.title == "project status"
	assert thread.tags == ["planning", "tasks"]
	assert len(summaries) == 1
	assert summaries[0].content == "The active branch decided to ship task maintenance."
	assert str(summaries[0].end_message_id) == str(thread.current_message_id)


@pytest.mark.asyncio
async def test_thread_maintenance_regenerates_summary_after_message_edit(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	principal = await _create_user_principal(
		db_session,
		"maintenance_stale@example.com",
		"maintenance_stale",
	)
	thread = await thread_service.create_thread(
		ThreadCreate(owner_id=principal.user.id, title="ready", tags=["chat"]),
		db_session,
		principal=principal,
	)
	message = await thread_service.create_message(
		thread.id,
		MessageCreate(content="old text", type=MessageType.USER),
		db_session,
		principal=principal,
	)
	await db_session.refresh(thread)
	old_summary = await summary_service.create_summary(
		thread_id=thread.id,
		summary_type=SummaryType.WINDOW,
		content="old summary",
		message_count=1,
		start_message_id=message.id,
		end_message_id=message.id,
		session=db_session,
	)
	await thread_service.update_user_message(
		thread.id,
		message.id,
		MessageUpdate(content="new edited text"),
		db_session,
		principal=principal,
	)
	await db_session.refresh(thread)
	captured_transcripts: list[str] = []

	async def _resolve_model(
		session: AsyncSession,
		task: str,
	) -> object:
		return object()

	async def _run_structured(
		chat_model: object,
		*,
		thread: Any,
		json_schema: dict[str, Any],
	) -> dict[str, object]:
		captured_transcripts.append(thread.messages[-1].text)
		return {
			"title": "ready",
			"tags": ["chat"],
			"summary": "new summary",
		}

	monkeypatch.setattr(
		thread_maintenance_service, "resolve_task_chat_model", _resolve_model
	)
	monkeypatch.setattr(
		thread_maintenance_service, "run_chat_model_json_schema", _run_structured
	)

	assert await thread_service.thread_needs_maintenance(thread, db_session) is True
	result = await thread_service.maintain_thread_metadata(
		thread.id,
		db_session,
		principal=principal,
		observed_last_activity_at=datetime.now(tz=UTC),
	)
	summaries = await summary_service.list_active_summaries(thread.id, db_session)

	assert result["summary_updated"] is True
	assert "new edited text" in captured_transcripts[0]
	assert len(summaries) == 1
	assert summaries[0].content == "new summary"
	assert summaries[0].id != old_summary.id
