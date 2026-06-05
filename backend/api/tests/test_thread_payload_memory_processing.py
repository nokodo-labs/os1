"""regressions for thread payloads and memory maintenance."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.event import Event
from api.schemas.thread import ThreadCreate, ThreadUpdate
from api.schemas.user import UserCreate
from api.v1.service import memories as memory_service
from api.v1.service import users as user_service
from api.v1.service.auth import Principal
from api.v1.service.chat.context import AppContext, RetrievalContext
from api.v1.service.chat.hooks import memory_post_processing as memory_hook_module
from api.v1.service.chat.hooks.memory_post_processing import MemoryPostProcessingHook
from api.v1.service.threads.core import create_thread, update_thread
from nokodo_ai.agents import AgentIterationSnapshot, AgentIterationState
from nokodo_ai.chat_models import ChatModel
from nokodo_ai.context import AgentContext
from nokodo_ai.messages import (
	AssistantMessage,
	FileContent,
	TextContent,
	ToolCall,
	ToolMessage,
	UserMessage,
)
from nokodo_ai.threads import Thread as SDKThread
from nokodo_ai.utils.typeid import TypeID


async def _noop_event_emitter(event: Event) -> None:
	_ = event


def _agent_context() -> AgentContext:
	return AgentContext(
		model=ChatModel.model_construct(api=None, model_name="test", adapter=None)
	)


def _hook_state(
	thread: SDKThread, final: bool = False
) -> AgentIterationSnapshot[AppContext]:
	return AgentIterationState[AppContext](thread=thread, tools=[]).snapshot(
		final=final
	)


@pytest.mark.asyncio
async def test_thread_update_omitted_tags_are_unchanged(
	db_session: AsyncSession,
) -> None:
	"""omitted tags must mean leave unchanged, never NULL."""
	user = await user_service.create_user(
		UserCreate(
			email="thread_update_none@example.com",
			username="thread_update_none",
			password="password123",
			is_superuser=True,
		),
		db_session,
	)
	principal = Principal(user=user, group_ids=(), permissions=frozenset())

	thread = await create_thread(
		ThreadCreate(owner_id=user.id, title="original", tags=["a", "b"]),
		db_session,
		principal,
	)
	await db_session.commit()

	updated = await update_thread(
		thread.id,
		ThreadUpdate(title="renamed"),
		db_session,
		principal,
	)
	await db_session.commit()

	assert updated.title == "renamed"
	assert updated.tags == ["a", "b"]


@pytest.mark.asyncio
async def test_thread_update_null_title_clears_title(
	db_session: AsyncSession,
) -> None:
	"""nullable thread fields can still be explicitly cleared."""
	user = await user_service.create_user(
		UserCreate(
			email="thread_update_clear_title@example.com",
			username="thread_update_clear_title",
			password="password123",
			is_superuser=True,
		),
		db_session,
	)
	principal = Principal(user=user, group_ids=(), permissions=frozenset())

	thread = await create_thread(
		ThreadCreate(owner_id=user.id, title="original", tags=["a"]),
		db_session,
		principal,
	)
	await db_session.commit()

	updated = await update_thread(
		thread.id,
		ThreadUpdate(title=None),
		db_session,
		principal,
	)
	await db_session.commit()

	assert updated.title is None
	assert updated.tags == ["a"]


def test_thread_update_rejects_null_tags() -> None:
	"""non-null thread update fields reject JSON null."""
	with pytest.raises(ValidationError):
		ThreadUpdate.model_validate({"tags": None})


@pytest.mark.asyncio
async def test_memory_post_processing_hook_defers_to_chat_runner(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""the SDK hook never schedules before the API runner has the message id."""
	calls: list[str] = []

	async def fake_start_memory_post_processing_task(
		task_session: AsyncSession,
		principal: Principal,
		query_text: str,
		max_related_memories: int,
		conversation_snapshot: str | None = None,
		thread_id: str | None = None,
		message_id: str | None = None,
		message_ref: str | None = None,
		run_id: str | None = None,
		emit_activity: bool = False,
	) -> None:
		_ = (
			task_session,
			principal,
			max_related_memories,
			conversation_snapshot,
			thread_id,
			message_id,
			message_ref,
			run_id,
			emit_activity,
		)
		calls.append(query_text)

	monkeypatch.setattr(
		memory_hook_module,
		"start_memory_post_processing_task",
		fake_start_memory_post_processing_task,
	)
	user = await user_service.create_user(
		UserCreate(
			email="memory_hook_tool@example.com",
			username="memory_hook_tool",
			password="password123",
			is_superuser=True,
		),
		db_session,
	)
	principal = Principal(user=user, group_ids=(), permissions=frozenset())
	app_context = AppContext(
		session=db_session,
		principal=principal,
		thread_id=TypeID("thread_memory_hook_defer"),
		event_emitter=_noop_event_emitter,
		retrieval=RetrievalContext(query_text="remember this"),
	)
	thread = SDKThread()
	thread.add(UserMessage.from_text("remember this"))
	thread.add(AssistantMessage.from_text("done"))

	await MemoryPostProcessingHook().execute(
		_hook_state(thread), _agent_context(), app_context
	)

	assert calls == []


@pytest.mark.asyncio
async def test_memory_post_processing_hook_skips_when_messages_are_queued(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""memory maintenance waits when out-of-band user messages will continue the run."""
	calls: list[str] = []

	async def fake_start_memory_post_processing_task(
		task_session: AsyncSession,
		principal: Principal,
		query_text: str,
		max_related_memories: int,
		conversation_snapshot: str | None = None,
		thread_id: str | None = None,
		message_id: str | None = None,
		message_ref: str | None = None,
		run_id: str | None = None,
		emit_activity: bool = False,
	) -> None:
		_ = (
			task_session,
			principal,
			max_related_memories,
			conversation_snapshot,
			thread_id,
			message_id,
			message_ref,
			run_id,
			emit_activity,
		)
		calls.append(query_text)

	monkeypatch.setattr(
		memory_hook_module,
		"start_memory_post_processing_task",
		fake_start_memory_post_processing_task,
	)
	user = await user_service.create_user(
		UserCreate(
			email="memory_hook_queued@example.com",
			username="memory_hook_queued",
			password="password123",
			is_superuser=True,
		),
		db_session,
	)
	principal = Principal(user=user, group_ids=(), permissions=frozenset())
	app_context = AppContext(
		session=db_session,
		principal=principal,
		run_id=TypeID("run_memory_hook_queued"),
		thread_id=TypeID("thread_memory_hook_queued"),
		event_emitter=_noop_event_emitter,
		retrieval=RetrievalContext(query_text="remember this"),
	)
	seen_run_ids: list[TypeID] = []

	async def has_in_flight_steering(run_id: TypeID) -> bool:
		seen_run_ids.append(run_id)
		return True

	monkeypatch.setattr(
		memory_hook_module.run_status_store,
		"has_in_flight_steering",
		has_in_flight_steering,
	)
	thread = SDKThread()
	thread.add(UserMessage.from_text("remember this"))
	thread.add(AssistantMessage.from_text("done"))

	await memory_hook_module.schedule_memory_post_processing(
		thread,
		app_context,
		"msg_final",
	)

	assert calls == []
	assert seen_run_ids == [TypeID("run_memory_hook_queued")]


@pytest.mark.asyncio
async def test_memory_post_processing_hook_schedules_after_final_assistant(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""memory maintenance schedules once the final assistant answer is present."""
	calls: list[dict[str, object]] = []

	async def fake_start_memory_post_processing_task(
		task_session: AsyncSession,
		principal: Principal,
		query_text: str,
		max_related_memories: int,
		conversation_snapshot: str | None = None,
		thread_id: str | None = None,
		message_id: str | None = None,
		message_ref: str | None = None,
		run_id: str | None = None,
		emit_activity: bool = False,
	) -> None:
		_ = (task_session, principal)
		calls.append(
			{
				"query_text": query_text,
				"max_related_memories": max_related_memories,
				"conversation_snapshot": conversation_snapshot,
				"thread_id": thread_id,
				"message_id": message_id,
				"message_ref": message_ref,
				"run_id": run_id,
				"emit_activity": emit_activity,
			}
		)

	monkeypatch.setattr(
		memory_hook_module,
		"start_memory_post_processing_task",
		fake_start_memory_post_processing_task,
	)
	user = await user_service.create_user(
		UserCreate(
			email="memory_hook_final@example.com",
			username="memory_hook_final",
			password="password123",
			is_superuser=True,
		),
		db_session,
	)
	principal = Principal(user=user, group_ids=(), permissions=frozenset())
	app_context = AppContext(
		session=db_session,
		principal=principal,
		run_id=TypeID("run_memory_hook_final"),
		thread_id=TypeID("thread_memory_hook_final"),
		final_assistant_message_ref="msg_ref_memory_hook_final",
		event_emitter=_noop_event_emitter,
		retrieval=RetrievalContext(query_text="remember this"),
	)
	thread = SDKThread()
	thread.add(
		UserMessage(
			content=[
				FileContent(
					filename="profile.pdf",
					media_type="application/pdf",
					base64="raw bytes must not leak",
					metadata={
						"file_id": "file_123",
						"description": "likes chocolate",
						"url": "https://private.example/file",
					},
				),
				TextContent(text="remember this"),
			]
		)
	)
	thread.add(
		AssistantMessage(
			content=[TextContent(text="checking")],
			tool_calls=[
				ToolCall(
					id="tc1",
					name="lookup",
					arguments={"dump": "tool call dump"},
				)
			],
		)
	)
	thread.add(
		ToolMessage(
			tool_call_id="tc1",
			tool_output="tool message dump",
			attachments=[
				FileContent(
					filename="tool-output.csv",
					media_type="text/csv",
					metadata={"description": "tool attachment"},
				)
			],
		)
	)
	thread.add(AssistantMessage.from_text("done"))

	await MemoryPostProcessingHook().execute(
		_hook_state(thread, final=True),
		_agent_context(),
		app_context,
	)

	assert len(calls) == 1
	call = calls[0]
	assert call["query_text"] == "remember this"
	assert call["max_related_memories"] == 10
	assert call["thread_id"] == "thread_memory_hook_final"
	assert call["message_id"] is None
	assert call["message_ref"] == "msg_ref_memory_hook_final"
	assert call["run_id"] == "run_memory_hook_final"
	assert call["emit_activity"] is True
	snapshot = call["conversation_snapshot"]
	assert isinstance(snapshot, str)
	assert "remember this" in snapshot
	assert "checking" in snapshot
	assert "done" in snapshot
	assert "name=profile.pdf" in snapshot
	assert "media_type=application/pdf" in snapshot
	assert "file_id=file_123" in snapshot
	assert "description=likes chocolate" in snapshot
	assert "lookup" not in snapshot
	assert "tool call dump" not in snapshot
	assert "tool message dump" not in snapshot
	assert "tool-output.csv" not in snapshot
	assert "raw bytes must not leak" not in snapshot
	assert "private.example" not in snapshot


@pytest.mark.asyncio
async def test_memory_post_processing_provider_timeout_is_skipped(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""provider timeouts skip optional memory maintenance instead of hanging."""

	class APITimeoutError(Exception):
		pass

	async def fail_embed(text: str, session: AsyncSession) -> list[float]:
		_ = (text, session)
		raise APITimeoutError("Request timed out.")

	user = await user_service.create_user(
		UserCreate(
			email="memory_timeout@example.com",
			username="memory_timeout",
			password="password123",
			is_superuser=True,
		),
		db_session,
	)
	principal = Principal(user=user, group_ids=(), permissions=frozenset())
	progress_events: list[tuple[int, str]] = []

	async def record_progress(progress: int, stage: str) -> None:
		progress_events.append((progress, stage))

	monkeypatch.setattr(memory_service, "embed_text", fail_embed)

	result = await memory_service.post_process_relevant_memories(
		"hello",
		db_session,
		principal=principal,
		progress_callback=record_progress,
	)

	assert result == {
		"skipped": True,
		"reason": "provider_timeout",
		"stage": "embedding memory query",
		"error": "APITimeoutError",
		"message": "Request timed out.",
	}
	assert progress_events == [(15, "embedding memory query")]
