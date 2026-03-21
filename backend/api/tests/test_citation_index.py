"""tests for citation index filter and helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.schemas.citations import Citation, CitationSource
from api.v1.service.chat.filters.citation_index import (
	CitationIndexFilter,
	_find_nci_in_window,
	_next_index,
	_oldest_message_id,
	_overfetch_nci,
	_rebuild_from_existing,
	_resolve_nci,
	resolve_assistant_citations,
)
from api.v1.service.prompt_runtime import SENTINEL_CITATION_SOURCES
from nokodo_ai.messages import (
	AssistantMessage,
	SystemMessage,
	ToolMessage,
	UserMessage,
)
from nokodo_ai.threads import Thread
from nokodo_ai.types import JSONObject, JSONValue


# -- helpers -----------------------------------------------------------------


def _citation(
	index: int,
	source_type: str = "url",
	source_id: str = "https://x.com",
	title: str | None = None,
) -> Citation:
	return Citation(
		index=index,
		source_type=CitationSource(source_type),
		source_id=source_id,
		title=title,
	)


def _tool_msg(
	output: str = "some output",
	*,
	citable_sources: list[JSONValue] | None = None,
	assigned: bool = False,
) -> ToolMessage:
	meta: JSONObject = {}
	if citable_sources is not None:
		meta["citable_sources"] = citable_sources
	if assigned:
		meta["_citations_assigned"] = True
	return ToolMessage(tool_call_id="tc_1", tool_output=output, metadata=meta or None)


def _assistant_msg(
	text: str = "hello",
	*,
	nci: int | None = None,
	citations: list[JSONValue] | None = None,
	message_id: str | None = None,
) -> AssistantMessage:
	meta: JSONObject = {}
	if nci is not None:
		meta["next_citation_index"] = nci
	if citations is not None:
		meta["citations"] = citations
	if message_id is not None:
		meta["message_id"] = message_id
	return AssistantMessage.from_text(text).model_copy(
		update={"metadata": meta or None},
	)


def _mock_app_ctx(entries: list[Citation] | None = None) -> MagicMock:
	ctx = MagicMock()
	ctx.citations = entries if entries is not None else []
	ctx.session = AsyncMock()
	ctx.event_emitter = AsyncMock()
	ctx.thread_id = None
	ctx.user_id = "user_test"
	return ctx


# -- _next_index -------------------------------------------------------------


class TestNextIndex:
	def test_first_citation_from_empty(self) -> None:
		assert _next_index([], 0) == 1

	def test_continues_from_existing(self) -> None:
		entries = [_citation(1), _citation(2)]
		assert _next_index(entries, 0) == 3

	def test_respects_nci_floor(self) -> None:
		# nci=5 means last run ended at index 4, next should be 5
		assert _next_index([], 5) == 5

	def test_entries_take_priority_over_nci(self) -> None:
		entries = [_citation(1), _citation(2), _citation(3)]
		# entries highest=3 > nci-1=1, so next=4
		assert _next_index(entries, 2) == 4

	def test_nci_takes_priority_when_higher(self) -> None:
		entries = [_citation(1)]
		# nci=5 -> nci-1=4 > highest=1, so next=5
		assert _next_index(entries, 5) == 5


# -- _find_nci_in_window -----------------------------------------------------


class TestFindNciInWindow:
	def test_returns_none_for_empty_thread(self) -> None:
		thread = Thread(messages=[])
		assert _find_nci_in_window(thread) is None

	def test_returns_none_when_no_assistant_messages(self) -> None:
		thread = Thread(messages=[UserMessage.from_text("hi")])
		assert _find_nci_in_window(thread) is None

	def test_returns_none_when_nci_is_1(self) -> None:
		thread = Thread(messages=[_assistant_msg(nci=1)])
		assert _find_nci_in_window(thread) is None

	def test_returns_highest_nci(self) -> None:
		thread = Thread(
			messages=[
				_assistant_msg(nci=3),
				_assistant_msg(nci=7),
				_assistant_msg(nci=5),
			]
		)
		assert _find_nci_in_window(thread) == 7

	def test_skips_non_int_nci(self) -> None:
		msg = _assistant_msg()
		msg.metadata = {"next_citation_index": "not_an_int"}
		thread = Thread(messages=[msg])
		assert _find_nci_in_window(thread) is None

	def test_ignores_tool_messages(self) -> None:
		thread = Thread(
			messages=[
				_tool_msg(),
				_assistant_msg(nci=5),
			]
		)
		assert _find_nci_in_window(thread) == 5


# -- _oldest_message_id ------------------------------------------------------


class TestOldestMessageId:
	def test_returns_none_for_empty_thread(self) -> None:
		thread = Thread(messages=[])
		assert _oldest_message_id(thread) is None

	def test_returns_first_message_with_id(self) -> None:
		thread = Thread(
			messages=[
				_assistant_msg(message_id="msg_001"),
				_assistant_msg(message_id="msg_002"),
			]
		)
		assert _oldest_message_id(thread) == "msg_001"

	def test_skips_messages_without_id(self) -> None:
		thread = Thread(
			messages=[
				UserMessage.from_text("hi"),
				_assistant_msg(message_id="msg_003"),
			]
		)
		assert _oldest_message_id(thread) == "msg_003"

	def test_returns_none_when_no_message_ids(self) -> None:
		thread = Thread(
			messages=[
				UserMessage.from_text("hi"),
				_assistant_msg(),
			]
		)
		assert _oldest_message_id(thread) is None


# -- _rebuild_from_existing --------------------------------------------------


class TestRebuildFromExisting:
	def test_rebuilds_citations_from_assistant_metadata(self) -> None:
		entries: list[Citation] = []
		citation_data = {
			"index": 1,
			"source_type": "url",
			"source_id": "https://example.com",
			"title": "example",
		}
		thread = Thread(
			messages=[
				_assistant_msg(citations=[citation_data]),
			]
		)
		_rebuild_from_existing(thread, entries)
		assert len(entries) == 1
		assert entries[0].index == 1
		assert entries[0].source_id == "https://example.com"

	def test_skips_non_assistant_messages(self) -> None:
		entries: list[Citation] = []
		thread = Thread(
			messages=[
				UserMessage.from_text("hi"),
				_tool_msg(),
			]
		)
		_rebuild_from_existing(thread, entries)
		assert entries == []

	def test_does_not_overwrite_existing_entries(self) -> None:
		existing = _citation(1, source_id="https://original.com")
		entries: list[Citation] = [existing]
		citation_data = {
			"index": 1,
			"source_type": "url",
			"source_id": "https://overwrite-attempt.com",
			"title": "should not replace",
		}
		thread = Thread(messages=[_assistant_msg(citations=[citation_data])])
		_rebuild_from_existing(thread, entries)
		assert len(entries) == 1
		assert entries[0] is existing

	def test_skips_invalid_citation_data(self) -> None:
		entries: list[Citation] = []
		thread = Thread(
			messages=[
				_assistant_msg(
					citations=[
						{
							"index": 0,
							"source_type": "url",
							"source_id": "x",
						},  # index < 1
						{"bad": "data"},  # no index
						"not a dict",  # not a dict
						{
							"index": "abc",
							"source_type": "url",
							"source_id": "x",
						},  # non-int index
					]
				),
			]
		)
		_rebuild_from_existing(thread, entries)
		assert entries == []

	def test_skips_invalid_pydantic_data(self) -> None:
		entries: list[Citation] = []
		thread = Thread(
			messages=[
				_assistant_msg(
					citations=[
						{"index": 1, "source_type": "invalid_source", "source_id": "x"},
					]
				),
			]
		)
		_rebuild_from_existing(thread, entries)
		# invalid source_type causes model_validate to fail, entry skipped
		# (the key behavior: no crash)

	def test_handles_missing_citations_metadata(self) -> None:
		entries: list[Citation] = []
		thread = Thread(
			messages=[
				_assistant_msg(),  # no citations in metadata
			]
		)
		_rebuild_from_existing(thread, entries)
		assert entries == []

	def test_rebuilds_sparse_indices(self) -> None:
		entries: list[Citation] = []
		thread = Thread(
			messages=[
				_assistant_msg(
					citations=[
						{
							"index": 3,
							"source_type": "url",
							"source_id": "https://a.com",
						},
						{"index": 5, "source_type": "note", "source_id": "note_123"},
					]
				),
			]
		)
		_rebuild_from_existing(thread, entries)
		assert len(entries) == 2
		assert entries[0].index == 3
		assert entries[0].source_id == "https://a.com"
		assert entries[1].index == 5
		assert entries[1].source_type == CitationSource.NOTE


# -- _assign_new_citations (via filter instance) -----------------------------


class TestAssignNewCitations:
	def _make_filter(self) -> CitationIndexFilter:
		return CitationIndexFilter()

	def test_assigns_indices_to_citable_sources(self) -> None:
		f = self._make_filter()
		entries: list[Citation] = []
		thread = Thread(
			messages=[
				_tool_msg(
					output="page content here",
					citable_sources=[
						{
							"source_type": "url",
							"source_id": "https://a.com",
							"title": "Site A",
						},
					],
				),
			]
		)
		f._assign_new_citations(thread, entries, 0)
		assert len(entries) == 1
		assert entries[0].index == 1
		assert entries[0].source_id == "https://a.com"
		assert entries[0].title == "Site A"
		# tool output should have markers appended
		msg = thread.messages[0]
		assert isinstance(msg, ToolMessage)
		assert "[1] Site A" in msg.tool_output

	def test_skips_already_assigned(self) -> None:
		f = self._make_filter()
		entries: list[Citation] = []
		thread = Thread(
			messages=[
				_tool_msg(
					output="content",
					citable_sources=[{"source_type": "url", "source_id": "x"}],
					assigned=True,
				),
			]
		)
		f._assign_new_citations(thread, entries, 0)
		assert entries == []

	def test_skips_non_tool_messages(self) -> None:
		f = self._make_filter()
		entries: list[Citation] = []
		thread = Thread(
			messages=[
				UserMessage.from_text("hi"),
				_assistant_msg(),
			]
		)
		f._assign_new_citations(thread, entries, 0)
		assert entries == []

	def test_skips_tool_without_citable_sources(self) -> None:
		f = self._make_filter()
		entries: list[Citation] = []
		thread = Thread(messages=[_tool_msg(output="just text")])
		f._assign_new_citations(thread, entries, 0)
		assert entries == []

	def test_skips_invalid_source_entries(self) -> None:
		f = self._make_filter()
		entries: list[Citation] = []
		thread = Thread(
			messages=[
				_tool_msg(
					output="content",
					citable_sources=[
						"not a dict",
						{"no_source_type": True},
						{"source_type": "url", "source_id": "valid"},
					],
				),
			]
		)
		f._assign_new_citations(thread, entries, 0)
		# only the valid one should be assigned
		assert len(entries) == 1
		assert entries[0].source_id == "valid"

	def test_multiple_sources_in_one_tool(self) -> None:
		f = self._make_filter()
		entries: list[Citation] = []
		thread = Thread(
			messages=[
				_tool_msg(
					output="content",
					citable_sources=[
						{
							"source_type": "url",
							"source_id": "https://a.com",
							"title": "A",
						},
						{
							"source_type": "note",
							"source_id": "note_1",
							"title": "Note 1",
						},
					],
				),
			]
		)
		f._assign_new_citations(thread, entries, 0)
		assert len(entries) == 2
		assert entries[0].source_type == CitationSource.URL
		assert entries[1].source_type == CitationSource.NOTE
		msg = thread.messages[0]
		assert isinstance(msg, ToolMessage)
		assert "[1] A" in msg.tool_output
		assert "[2] Note 1" in msg.tool_output

	def test_indices_continue_from_existing(self) -> None:
		f = self._make_filter()
		entries: list[Citation] = [_citation(1), _citation(2)]
		thread = Thread(
			messages=[
				_tool_msg(
					output="content",
					citable_sources=[
						{
							"source_type": "url",
							"source_id": "https://b.com",
							"title": "B",
						},
					],
				),
			]
		)
		f._assign_new_citations(thread, entries, 0)
		assert len(entries) == 3
		assert entries[2].index == 3
		assert entries[2].source_id == "https://b.com"

	def test_uses_source_id_as_label_when_no_title(self) -> None:
		f = self._make_filter()
		entries: list[Citation] = []
		thread = Thread(
			messages=[
				_tool_msg(
					output="content",
					citable_sources=[
						{"source_type": "url", "source_id": "https://notitle.com"},
					],
				),
			]
		)
		f._assign_new_citations(thread, entries, 0)
		msg = thread.messages[0]
		assert isinstance(msg, ToolMessage)
		assert "[1] https://notitle.com" in msg.tool_output

	def test_uses_source_type_as_fallback_label(self) -> None:
		f = self._make_filter()
		entries: list[Citation] = []
		thread = Thread(
			messages=[
				_tool_msg(
					output="content",
					citable_sources=[
						{"source_type": "tool_result"},
					],
				),
			]
		)
		f._assign_new_citations(thread, entries, 0)
		msg = thread.messages[0]
		assert isinstance(msg, ToolMessage)
		assert "[1] tool_result" in msg.tool_output

	def test_marks_tool_message_as_assigned(self) -> None:
		f = self._make_filter()
		entries: list[Citation] = []
		thread = Thread(
			messages=[
				_tool_msg(
					output="content",
					citable_sources=[
						{"source_type": "url", "source_id": "x"},
					],
				),
			]
		)
		f._assign_new_citations(thread, entries, 0)
		msg = thread.messages[0]
		assert isinstance(msg, ToolMessage)
		assert msg.metadata is not None
		assert msg.metadata["_citations_assigned"] is True

	def test_empty_citable_sources_list(self) -> None:
		f = self._make_filter()
		entries: list[Citation] = []
		thread = Thread(
			messages=[
				_tool_msg(output="content", citable_sources=[]),
			]
		)
		f._assign_new_citations(thread, entries, 0)
		assert entries == []

	def test_all_sources_invalid_skips_tool(self) -> None:
		f = self._make_filter()
		entries: list[Citation] = []
		tool = ToolMessage(
			tool_call_id="tc_1",
			tool_output="content",
			metadata={
				"citable_sources": [
					"not a dict",
					42,
					{"no_source_type": True},
				],
			},
		)
		thread = Thread(messages=[tool])
		f._assign_new_citations(thread, entries, 0)
		assert entries == []
		# tool output should be unchanged (no markers appended)
		msg = thread.messages[0]
		assert isinstance(msg, ToolMessage)
		assert msg.tool_output == "content"

	def test_nci_floor_prevents_index_collision(self) -> None:
		"""when nci is higher than entries count, new indices start at nci."""
		f = self._make_filter()
		entries: list[Citation] = []
		thread = Thread(
			messages=[
				_tool_msg(
					output="content",
					citable_sources=[
						{"source_type": "url", "source_id": "x", "title": "X"},
					],
				),
			]
		)
		f._assign_new_citations(thread, entries, 5)
		assert len(entries) == 1
		assert entries[0].index == 5


# -- _inject_manifest --------------------------------------------------------


class TestInjectManifest:
	def _make_filter(self) -> CitationIndexFilter:
		return CitationIndexFilter()

	def test_replaces_sentinel_with_manifest(self) -> None:
		f = self._make_filter()
		entries: list[Citation] = [
			_citation(1, title="Site A"),
			_citation(2, source_type="note", source_id="note_1", title="My Note"),
		]
		thread = Thread(
			messages=[
				SystemMessage.from_text(f"prompt\n{SENTINEL_CITATION_SOURCES}\nend"),
			]
		)
		f._inject_manifest(thread, entries)
		msg = thread.messages[0]
		assert isinstance(msg, SystemMessage)
		assert "[1] Site A" in msg.text
		assert "[2] My Note" in msg.text
		assert SENTINEL_CITATION_SOURCES not in msg.text

	def test_clears_sentinel_when_no_citations(self) -> None:
		f = self._make_filter()
		entries: list[Citation] = []
		thread = Thread(
			messages=[
				SystemMessage.from_text(f"prompt\n{SENTINEL_CITATION_SOURCES}\nend"),
			]
		)
		f._inject_manifest(thread, entries)
		msg = thread.messages[0]
		assert isinstance(msg, SystemMessage)
		assert SENTINEL_CITATION_SOURCES not in msg.text
		assert "prompt" in msg.text

	def test_no_sentinel_in_thread(self) -> None:
		f = self._make_filter()
		entries: list[Citation] = [_citation(1)]
		thread = Thread(
			messages=[
				SystemMessage.from_text("no sentinel here"),
			]
		)
		f._inject_manifest(thread, entries)
		# should not crash, text unchanged
		msg = thread.messages[0]
		assert isinstance(msg, SystemMessage)
		assert msg.text == "no sentinel here"


# -- resolve_assistant_citations ---------------------------------------------


class TestResolveAssistantCitations:
	def test_resolves_markers_to_citations(self) -> None:
		entries: list[Citation] = [
			_citation(1, source_id="https://a.com"),
			_citation(2, source_id="https://b.com"),
		]
		result = resolve_assistant_citations("see [1] and [2] for details", entries)
		assert len(result) == 2
		assert result[0].source_id == "https://a.com"
		assert result[1].source_id == "https://b.com"

	def test_returns_empty_for_no_text(self) -> None:
		entries: list[Citation] = [_citation(1)]
		assert resolve_assistant_citations("", entries) == []

	def test_returns_empty_for_no_entries(self) -> None:
		assert resolve_assistant_citations("see [1]", []) == []

	def test_ignores_out_of_range_indices(self) -> None:
		entries: list[Citation] = [_citation(1)]
		result = resolve_assistant_citations("see [1] and [99]", entries)
		assert len(result) == 1

	def test_ignores_zero_index(self) -> None:
		entries: list[Citation] = [_citation(1)]
		result = resolve_assistant_citations("[0] and [1]", entries)
		assert len(result) == 1
		assert result[0].index == 1

	def test_deduplicates_repeated_markers(self) -> None:
		entries: list[Citation] = [_citation(1)]
		result = resolve_assistant_citations("[1] then [1] again", entries)
		assert len(result) == 1

	def test_returns_sorted_by_index(self) -> None:
		entries: list[Citation] = [
			_citation(1, source_id="a"),
			_citation(2, source_id="b"),
			_citation(3, source_id="c"),
		]
		result = resolve_assistant_citations("[3] then [1] then [2]", entries)
		assert [c.index for c in result] == [1, 2, 3]

	def test_handles_adjacent_markers(self) -> None:
		entries: list[Citation] = [_citation(1), _citation(2)]
		result = resolve_assistant_citations("[1][2]", entries)
		assert len(result) == 2

	def test_ignores_non_numeric_brackets(self) -> None:
		entries: list[Citation] = [_citation(1)]
		result = resolve_assistant_citations("[abc] and [1]", entries)
		assert len(result) == 1

	def test_resolves_footnote_style_markers(self) -> None:
		"""models sometimes emit [^n] instead of [n]."""
		entries: list[Citation] = [
			_citation(1, source_id="https://a.com"),
			_citation(2, source_id="https://b.com"),
		]
		result = resolve_assistant_citations("see [^1] and [^2]", entries)
		assert len(result) == 2
		assert result[0].source_id == "https://a.com"
		assert result[1].source_id == "https://b.com"

	def test_resolves_mixed_bracket_and_footnote(self) -> None:
		entries: list[Citation] = [_citation(1), _citation(2)]
		result = resolve_assistant_citations("[1] and [^2]", entries)
		assert len(result) == 2

	def test_footnote_definition_lines_are_matched(self) -> None:
		"""footnote defs like [^1]: ... still contain [^1] and should match."""
		entries: list[Citation] = [_citation(1)]
		text = "see [^1] for details.\n\n[^1]: source title"
		result = resolve_assistant_citations(text, entries)
		assert len(result) == 1


# -- _resolve_nci ------------------------------------------------------------


class TestResolveNci:
	async def test_returns_nci_from_window(self) -> None:
		thread = Thread(messages=[_assistant_msg(nci=5)])
		session = AsyncMock()
		result = await _resolve_nci(thread, session)
		assert result == 5

	async def test_returns_zero_when_no_nci(self) -> None:
		thread = Thread(messages=[_assistant_msg()])
		session = AsyncMock()
		result = await _resolve_nci(thread, session)
		assert result == 0

	async def test_overfetch_path_when_window_has_no_nci(self) -> None:
		thread = Thread(messages=[_assistant_msg(message_id="msg_001")])
		session = AsyncMock()
		with patch(
			"api.v1.service.chat.filters.citation_index._overfetch_nci",
			return_value=4,
		) as mock_overfetch:
			result = await _resolve_nci(thread, session)
			mock_overfetch.assert_awaited_once_with(session, "msg_001")
		assert result == 4

	async def test_overfetch_returns_none(self) -> None:
		thread = Thread(messages=[_assistant_msg(message_id="msg_001")])
		session = AsyncMock()
		with patch(
			"api.v1.service.chat.filters.citation_index._overfetch_nci",
			return_value=None,
		):
			result = await _resolve_nci(thread, session)
		assert result == 0


# -- _overfetch_nci ----------------------------------------------------------


class TestOverfetchNci:
	async def test_returns_nci_from_result(self) -> None:
		session = AsyncMock()
		mock_row = MagicMock()
		mock_row.nci = "5"
		mock_result = MagicMock()
		mock_result.one_or_none.return_value = mock_row
		session.execute.return_value = mock_result
		result = await _overfetch_nci(session, "msg_001")
		assert result == 5

	async def test_returns_none_when_no_rows(self) -> None:
		session = AsyncMock()
		mock_result = MagicMock()
		mock_result.one_or_none.return_value = None
		session.execute.return_value = mock_result
		result = await _overfetch_nci(session, "msg_001")
		assert result is None

	async def test_returns_none_for_non_numeric_nci(self) -> None:
		session = AsyncMock()
		mock_row = MagicMock()
		mock_row.nci = "not_a_number"
		mock_result = MagicMock()
		mock_result.one_or_none.return_value = mock_row
		session.execute.return_value = mock_result
		result = await _overfetch_nci(session, "msg_001")
		assert result is None

	async def test_returns_none_for_none_nci_value(self) -> None:
		session = AsyncMock()
		mock_row = MagicMock()
		mock_row.nci = None
		mock_result = MagicMock()
		mock_result.one_or_none.return_value = mock_row
		session.execute.return_value = mock_result
		result = await _overfetch_nci(session, "msg_001")
		assert result is None


# -- CitationIndexFilter.process (integration) -------------------------------


class TestCitationIndexFilterProcess:
	async def test_returns_thread_when_no_app_context(self) -> None:
		f = CitationIndexFilter()
		thread = Thread(messages=[])
		result = await f.process(thread, None)
		assert result is thread

	async def test_full_flow_assigns_and_resolves(self) -> None:
		f = CitationIndexFilter()
		ctx = _mock_app_ctx()
		thread = Thread(
			messages=[
				SystemMessage.from_text(f"prompt\n{SENTINEL_CITATION_SOURCES}"),
				_tool_msg(
					output="fetched page",
					citable_sources=[
						{
							"source_type": "url",
							"source_id": "https://x.com",
							"title": "X",
						},
					],
				),
			]
		)
		result = await f.process(thread, ctx)
		# citation should be assigned
		assert len(ctx.citations) == 1
		assert ctx.citations[0].index == 1
		assert ctx.citations[0].source_id == "https://x.com"
		# sentinel should be replaced
		sys_msg = result.messages[0]
		assert isinstance(sys_msg, SystemMessage)
		assert "[1] X" in sys_msg.text
		# tool output should have marker
		tool_msg = result.messages[1]
		assert isinstance(tool_msg, ToolMessage)
		assert "[1] X" in tool_msg.tool_output

	async def test_rebuilds_then_assigns_new(self) -> None:
		f = CitationIndexFilter()
		ctx = _mock_app_ctx()
		existing_citation = {
			"index": 1,
			"source_type": "url",
			"source_id": "https://old.com",
			"title": "Old",
		}
		thread = Thread(
			messages=[
				SystemMessage.from_text(f"prompt\n{SENTINEL_CITATION_SOURCES}"),
				_assistant_msg(nci=2, citations=[existing_citation]),
				_tool_msg(
					output="new fetched page",
					citable_sources=[
						{
							"source_type": "note",
							"source_id": "note_1",
							"title": "New Note",
						},
					],
				),
			]
		)
		result = await f.process(thread, ctx)
		# entries should contain both rebuilt and new
		assert len(ctx.citations) == 2
		assert ctx.citations[0].index == 1
		assert ctx.citations[0].source_id == "https://old.com"
		assert ctx.citations[1].index == 2
		assert ctx.citations[1].source_id == "note_1"
		# manifest should contain both
		sys_msg = result.messages[0]
		assert isinstance(sys_msg, SystemMessage)
		assert "[1] Old" in sys_msg.text
		assert "[2] New Note" in sys_msg.text

	async def test_empty_list_assigns_correctly(self) -> None:
		"""ctx.citations starts as [] in production - verify it works."""
		f = CitationIndexFilter()
		ctx = _mock_app_ctx(entries=[])
		thread = Thread(
			messages=[
				SystemMessage.from_text(f"prompt\n{SENTINEL_CITATION_SOURCES}"),
				_tool_msg(
					output="fetched page",
					citable_sources=[
						{
							"source_type": "url",
							"source_id": "https://x.com",
							"title": "X",
						},
					],
				),
			]
		)
		await f.process(thread, ctx)
		assert len(ctx.citations) == 1
		assert ctx.citations[0].index == 1
		assert ctx.citations[0].source_id == "https://x.com"
		# ensure resolve_assistant_citations can find it
		resolved = resolve_assistant_citations("see [1] here", ctx.citations)
		assert len(resolved) == 1
		assert resolved[0].source_id == "https://x.com"

	async def test_single_source_resolvable(self) -> None:
		"""a single citable source is properly resolvable."""
		f = CitationIndexFilter()
		ctx = _mock_app_ctx(entries=[])
		thread = Thread(
			messages=[
				_tool_msg(
					output="content",
					citable_sources=[
						{
							"source_type": "url",
							"source_id": "https://only.com",
							"title": "Only Source",
						},
					],
				),
			]
		)
		await f.process(thread, ctx)
		result = resolve_assistant_citations("check [1] out", ctx.citations)
		assert len(result) == 1
		assert result[0].index == 1
		assert result[0].source_id == "https://only.com"


# -- Citation schema ---------------------------------------------------------


class TestCitationSchema:
	def test_valid_citation(self) -> None:
		c = Citation(
			index=1,
			source_type=CitationSource.URL,
			source_id="https://x.com",
			title="X",
		)
		assert c.index == 1
		assert c.source_type == CitationSource.URL
		assert c.source_id == "https://x.com"
		assert c.title == "X"

	def test_index_must_be_positive(self) -> None:
		with pytest.raises(Exception):
			Citation(index=0, source_type=CitationSource.URL, source_id="x")

	def test_title_optional(self) -> None:
		c = Citation(index=1, source_type=CitationSource.URL, source_id="x")
		assert c.title is None

	def test_all_source_types(self) -> None:
		for src in CitationSource:
			c = Citation(index=1, source_type=src, source_id="test")
			assert c.source_type == src

	def test_model_validate_from_dict(self) -> None:
		data = {
			"index": 2,
			"source_type": "note",
			"source_id": "n_123",
			"title": "My Note",
		}
		c = Citation.model_validate(data)
		assert c.source_type == CitationSource.NOTE
		assert c.source_id == "n_123"

	def test_model_validate_rejects_invalid_source_type(self) -> None:
		data = {"index": 1, "source_type": "bogus", "source_id": "x"}
		with pytest.raises(Exception):
			Citation.model_validate(data)

	def test_negative_index_rejected(self) -> None:
		with pytest.raises(Exception):
			Citation(index=-1, source_type=CitationSource.URL, source_id="x")
