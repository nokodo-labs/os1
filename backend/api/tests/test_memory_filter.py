"""tests for memory context filter formatting."""

import json
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast

import pytest

from api.models.memory import Memory
from api.schemas.preferences import AIPreferences
from api.v1.service.chat.context import AppContext
from api.v1.service.chat.filters.chat_context import ChatContextFilter
from api.v1.service.chat.filters.memory import MemoryContextFilter
from api.v1.service.prompt_runtime import SENTINEL_CHAT_CONTEXT, SENTINEL_USER_MEMORIES
from nokodo_ai.agents import AgentIterationState
from nokodo_ai.chat_models import ChatModel
from nokodo_ai.context import AgentContext
from nokodo_ai.messages import SystemMessage
from nokodo_ai.threads import Thread


@pytest.fixture
def filter_instance() -> MemoryContextFilter:
	return MemoryContextFilter()


def _make_memory(
	content: str = "test content",
	tags: list[str] | None = None,
	created_at: datetime | None = None,
	updated_at: datetime | None = None,
) -> Memory:
	return cast(
		Memory,
		SimpleNamespace(
			content=content,
			tags=tags,
			created_at=created_at,
			updated_at=updated_at,
		),
	)


def _agent_context(thread: Thread) -> AgentContext:
	_ = thread
	return AgentContext(
		model=ChatModel.model_construct(model_name="test"),
	)


def _app_context(ai: AIPreferences) -> AppContext:
	return cast(
		AppContext,
		SimpleNamespace(
			principal=SimpleNamespace(
				user=SimpleNamespace(prefs=SimpleNamespace(ai=ai))
			),
			retrieval=SimpleNamespace(query_text=None, query_embedding=None),
			session=None,
			thread_id=None,
		),
	)


def _ai_preferences(**values: object) -> AIPreferences:
	return AIPreferences.model_validate(values)


def _state(thread: Thread) -> AgentIterationState[AppContext]:
	return cast(
		AgentIterationState[AppContext], AgentIterationState(thread=thread, tools=[])
	)


def test_format_memories_with_tags(filter_instance: MemoryContextFilter) -> None:
	"""_format_memories includes tags when present."""
	now = datetime(2026, 1, 1, tzinfo=UTC)
	mem = _make_memory(
		content="likes pizza", tags=["food", "preferences"], created_at=now
	)
	result = json.loads(filter_instance._format_memories([mem]))
	assert result[0]["content"] == "likes pizza"
	assert result[0]["tags"] == ["food", "preferences"]


def test_format_memories_without_tags(filter_instance: MemoryContextFilter) -> None:
	"""_format_memories omits tags key when None."""
	mem = _make_memory(content="no tags here", tags=None)
	result = json.loads(filter_instance._format_memories([mem]))
	assert "tags" not in result[0]
	assert result[0]["content"] == "no tags here"


def test_format_memories_empty_tags(filter_instance: MemoryContextFilter) -> None:
	"""_format_memories omits tags key when empty list."""
	mem = _make_memory(content="empty tags", tags=[])
	result = json.loads(filter_instance._format_memories([mem]))
	assert "tags" not in result[0]


def test_format_memories_multiple(filter_instance: MemoryContextFilter) -> None:
	"""_format_memories handles multiple memories."""
	mems = [
		_make_memory(content="first", tags=["a"]),
		_make_memory(content="second", tags=None),
	]
	result = json.loads(filter_instance._format_memories(mems))
	assert len(result) == 2
	assert result[0]["tags"] == ["a"]
	assert "tags" not in result[1]


@pytest.mark.asyncio
async def test_memory_filter_clears_sentinel_when_memories_disabled() -> None:
	thread = Thread(
		messages=[SystemMessage.from_text(f"before {SENTINEL_USER_MEMORIES} after")]
	)
	state = _state(thread)

	result = await MemoryContextFilter().process(
		state,
		_agent_context(thread),
		_app_context(_ai_preferences(memoriesEnabled=False)),
	)

	assert result.thread.system_message is not None
	assert SENTINEL_USER_MEMORIES not in result.thread.system_message.text
	assert result.thread.system_message.text == "before  after"


@pytest.mark.asyncio
async def test_chat_context_filter_clears_sentinel_when_chat_recall_disabled() -> None:
	thread = Thread(
		messages=[SystemMessage.from_text(f"before {SENTINEL_CHAT_CONTEXT} after")]
	)
	state = _state(thread)

	result = await ChatContextFilter().process(
		state,
		_agent_context(thread),
		_app_context(_ai_preferences(chatRecall=False)),
	)

	assert result.thread.system_message is not None
	assert SENTINEL_CHAT_CONTEXT not in result.thread.system_message.text
	assert result.thread.system_message.text == "before  after"


@pytest.mark.asyncio
async def test_chat_context_filter_clears_sentinel_when_memories_disabled() -> None:
	thread = Thread(
		messages=[SystemMessage.from_text(f"before {SENTINEL_CHAT_CONTEXT} after")]
	)
	state = _state(thread)

	result = await ChatContextFilter().process(
		state,
		_agent_context(thread),
		_app_context(_ai_preferences(memoriesEnabled=False, chatRecall=True)),
	)

	assert result.thread.system_message is not None
	assert SENTINEL_CHAT_CONTEXT not in result.thread.system_message.text
	assert result.thread.system_message.text == "before  after"


def test_default_ai_preferences_do_not_disable_memory_context() -> None:
	preferences = _ai_preferences()

	assert preferences.memories_enabled is not False
	assert preferences.chat_recall is not False


@pytest.mark.asyncio
async def test_chat_context_filter_default_preferences_do_not_skip(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	thread = Thread(
		messages=[SystemMessage.from_text(f"before {SENTINEL_CHAT_CONTEXT} after")]
	)
	state = _state(thread)
	filter_ = ChatContextFilter()
	called = False

	async def fake_fetch_recent(
		app_context: AppContext,
		cfg: object,
		exclude_id: object,
	) -> list[object]:
		nonlocal called
		called = True
		return []

	async def fake_fetch_relevant(
		thread: Thread,
		app_context: AppContext,
		cfg: object,
		exclude_id: object,
	) -> list[object]:
		nonlocal called
		called = True
		return []

	monkeypatch.setattr(filter_, "_fetch_recent", fake_fetch_recent)
	monkeypatch.setattr(filter_, "_fetch_relevant", fake_fetch_relevant)

	await filter_.process(
		state,
		_agent_context(thread),
		_app_context(_ai_preferences()),
	)

	assert called
