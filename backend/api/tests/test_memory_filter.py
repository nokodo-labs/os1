"""tests for memory context filter formatting."""

import json
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast

import pytest

from api.models.memory import Memory
from api.v1.service.chat.filters.memory import MemoryContextFilter


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
