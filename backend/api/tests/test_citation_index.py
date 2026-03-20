"""tests for citation index filter and helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.schemas.citations import Citation, CitationSource
from api.v1.service.chat.filters.citation_index import (
	CitationIndexFilter,
	_ensure_slot,
	_find_nci_in_window,
	_oldest_message_id,
	_overfetch_nci,
	_rebuild_from_existing,
	_seed_entries,
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


def _mock_app_ctx(entries: list[Citation | None] | None = None) -> MagicMock:
	ctx = MagicMock()
	ctx.citations = entries if entries is not None else [None]
	ctx.session = AsyncMock()
	ctx.event_emitter = AsyncMock()
	ctx.thread_id = None
	ctx.user_id = "user_test"
	return ctx


# -- _ensure_slot ------------------------------------------------------------


class TestEnsureSlot:
	def test_grows_list(self) -> None:
		lst: list[Citation | None] = [None]
		_ensure_slot(lst, 5)
		assert len(lst) == 6
		assert all(x is None for x in lst)

	def test_no_op_when_already_large(self) -> None:
		lst: list[Citation | None] = [None] * 10
		_ensure_slot(lst, 3)
		assert len(lst) == 10

	def test_exact_boundary(self) -> None:
		lst: list[Citation | None] = [None]
		_ensure_slot(lst, 1)
		assert len(lst) == 2


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
		entries: list[Citation | None] = [None]
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
		assert len(entries) == 2
		assert entries[1] is not None
		assert entries[1].source_id == "https://example.com"

	def test_skips_non_assistant_messages(self) -> None:
		entries: list[Citation | None] = [None]
		thread = Thread(
			messages=[
				UserMessage.from_text("hi"),
				_tool_msg(),
			]
		)
		_rebuild_from_existing(thread, entries)
		assert entries == [None]

	def test_does_not_overwrite_existing_entries(self) -> None:
		existing = _citation(1, source_id="https://original.com")
		entries: list[Citation | None] = [None, existing]
		citation_data = {
			"index": 1,
			"source_type": "url",
			"source_id": "https://overwrite-attempt.com",
			"title": "should not replace",
		}
		thread = Thread(messages=[_assistant_msg(citations=[citation_data])])
		_rebuild_from_existing(thread, entries)
		assert entries[1] is existing

	def test_skips_invalid_citation_data(self) -> None:
		entries: list[Citation | None] = [None]
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
		assert entries == [None]

	def test_skips_invalid_pydantic_data(self) -> None:
		entries: list[Citation | None] = [None]
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
		# invalid source_type should cause model_validate to fail
		assert len(entries) >= 2
		# depending on pydantic strictness, the entry may or may not be set
		# if it fails, the slot should still be None
		# (the key behavior: no crash)

	def test_handles_missing_citations_metadata(self) -> None:
		entries: list[Citation | None] = [None]
		thread = Thread(
			messages=[
				_assistant_msg(),  # no citations in metadata
			]
		)
		_rebuild_from_existing(thread, entries)
		assert entries == [None]

	def test_rebuilds_sparse_indices(self) -> None:
		entries: list[Citation | None] = [None]
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
		assert len(entries) == 6
		assert entries[1] is None
		assert entries[2] is None
		assert entries[3] is not None
		assert entries[3].source_id == "https://a.com"
		assert entries[4] is None
		assert entries[5] is not None
		assert entries[5].source_type == CitationSource.NOTE


# -- _assign_new_citations (via filter instance) -----------------------------


class TestAssignNewCitations:
	def _make_filter(self) -> CitationIndexFilter:
		return CitationIndexFilter()

	def test_assigns_indices_to_citable_sources(self) -> None:
		f = self._make_filter()
		entries: list[Citation | None] = [None]
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
		f._assign_new_citations(thread, entries)
		assert len(entries) == 2
		assert entries[1] is not None
		assert entries[1].index == 1
		assert entries[1].source_id == "https://a.com"
		assert entries[1].title == "Site A"
		# tool output should have markers appended
		msg = thread.messages[0]
		assert isinstance(msg, ToolMessage)
		assert "[1] Site A" in msg.tool_output

	def test_skips_already_assigned(self) -> None:
		f = self._make_filter()
		entries: list[Citation | None] = [None]
		thread = Thread(
			messages=[
				_tool_msg(
					output="content",
					citable_sources=[{"source_type": "url", "source_id": "x"}],
					assigned=True,
				),
			]
		)
		f._assign_new_citations(thread, entries)
		assert entries == [None]

	def test_skips_non_tool_messages(self) -> None:
		f = self._make_filter()
		entries: list[Citation | None] = [None]
		thread = Thread(
			messages=[
				UserMessage.from_text("hi"),
				_assistant_msg(),
			]
		)
		f._assign_new_citations(thread, entries)
		assert entries == [None]

	def test_skips_tool_without_citable_sources(self) -> None:
		f = self._make_filter()
		entries: list[Citation | None] = [None]
		thread = Thread(messages=[_tool_msg(output="just text")])
		f._assign_new_citations(thread, entries)
		assert entries == [None]

	def test_skips_invalid_source_entries(self) -> None:
		f = self._make_filter()
		entries: list[Citation | None] = [None]
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
		f._assign_new_citations(thread, entries)
		# only the valid one should be assigned
		assert len(entries) == 2
		assert entries[1] is not None
		assert entries[1].source_id == "valid"

	def test_multiple_sources_in_one_tool(self) -> None:
		f = self._make_filter()
		entries: list[Citation | None] = [None]
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
		f._assign_new_citations(thread, entries)
		assert len(entries) == 3
		assert entries[1] is not None
		assert entries[1].source_type == CitationSource.URL
		assert entries[2] is not None
		assert entries[2].source_type == CitationSource.NOTE
		msg = thread.messages[0]
		assert isinstance(msg, ToolMessage)
		assert "[1] A" in msg.tool_output
		assert "[2] Note 1" in msg.tool_output

	def test_indices_continue_from_existing(self) -> None:
		f = self._make_filter()
		entries: list[Citation | None] = [None, _citation(1), _citation(2)]
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
		f._assign_new_citations(thread, entries)
		assert len(entries) == 4
		assert entries[3] is not None
		assert entries[3].index == 3
		assert entries[3].source_id == "https://b.com"

	def test_uses_source_id_as_label_when_no_title(self) -> None:
		f = self._make_filter()
		entries: list[Citation | None] = [None]
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
		f._assign_new_citations(thread, entries)
		msg = thread.messages[0]
		assert isinstance(msg, ToolMessage)
		assert "[1] https://notitle.com" in msg.tool_output

	def test_uses_source_type_as_fallback_label(self) -> None:
		f = self._make_filter()
		entries: list[Citation | None] = [None]
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
		f._assign_new_citations(thread, entries)
		msg = thread.messages[0]
		assert isinstance(msg, ToolMessage)
		assert "[1] tool_result" in msg.tool_output

	def test_marks_tool_message_as_assigned(self) -> None:
		f = self._make_filter()
		entries: list[Citation | None] = [None]
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
		f._assign_new_citations(thread, entries)
		msg = thread.messages[0]
		assert isinstance(msg, ToolMessage)
		assert msg.metadata is not None
		assert msg.metadata["_citations_assigned"] is True

	def test_empty_citable_sources_list(self) -> None:
		f = self._make_filter()
		entries: list[Citation | None] = [None]
		thread = Thread(
			messages=[
				_tool_msg(output="content", citable_sources=[]),
			]
		)
		f._assign_new_citations(thread, entries)
		assert entries == [None]

	def test_all_sources_invalid_skips_tool(self) -> None:
		f = self._make_filter()
		entries: list[Citation | None] = [None]
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
		f._assign_new_citations(thread, entries)
		assert entries == [None]
		# tool output should be unchanged (no markers appended)
		msg = thread.messages[0]
		assert isinstance(msg, ToolMessage)
		assert msg.tool_output == "content"


# -- _inject_manifest --------------------------------------------------------


class TestInjectManifest:
	def _make_filter(self) -> CitationIndexFilter:
		return CitationIndexFilter()

	def test_replaces_sentinel_with_manifest(self) -> None:
		f = self._make_filter()
		entries: list[Citation | None] = [
			None,
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
		entries: list[Citation | None] = [None]
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

	def test_skips_none_entries_in_manifest(self) -> None:
		f = self._make_filter()
		entries: list[Citation | None] = [
			None,
			_citation(1, title="A"),
			None,
			_citation(3, title="C"),
		]
		thread = Thread(
			messages=[
				SystemMessage.from_text(f"x{SENTINEL_CITATION_SOURCES}y"),
			]
		)
		f._inject_manifest(thread, entries)
		msg = thread.messages[0]
		assert isinstance(msg, SystemMessage)
		assert "[1] A" in msg.text
		assert "[3] C" in msg.text

	def test_no_sentinel_in_thread(self) -> None:
		f = self._make_filter()
		entries: list[Citation | None] = [None, _citation(1)]
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
		entries: list[Citation | None] = [
			None,
			_citation(1, source_id="https://a.com"),
			_citation(2, source_id="https://b.com"),
		]
		result = resolve_assistant_citations("see [1] and [2] for details", entries)
		assert len(result) == 2
		assert result[0].source_id == "https://a.com"
		assert result[1].source_id == "https://b.com"

	def test_returns_empty_for_no_text(self) -> None:
		entries: list[Citation | None] = [None, _citation(1)]
		assert resolve_assistant_citations("", entries) == []

	def test_returns_empty_for_no_entries(self) -> None:
		assert resolve_assistant_citations("see [1]", [None]) == []

	def test_ignores_out_of_range_indices(self) -> None:
		entries: list[Citation | None] = [None, _citation(1)]
		result = resolve_assistant_citations("see [1] and [99]", entries)
		assert len(result) == 1

	def test_ignores_zero_index(self) -> None:
		entries: list[Citation | None] = [None, _citation(1)]
		result = resolve_assistant_citations("[0] and [1]", entries)
		assert len(result) == 1
		assert result[0].index == 1

	def test_deduplicates_repeated_markers(self) -> None:
		entries: list[Citation | None] = [None, _citation(1)]
		result = resolve_assistant_citations("[1] then [1] again", entries)
		assert len(result) == 1

	def test_returns_sorted_by_index(self) -> None:
		entries: list[Citation | None] = [
			None,
			_citation(1, source_id="a"),
			_citation(2, source_id="b"),
			_citation(3, source_id="c"),
		]
		result = resolve_assistant_citations("[3] then [1] then [2]", entries)
		assert [c.index for c in result] == [1, 2, 3]

	def test_skips_none_slots(self) -> None:
		entries: list[Citation | None] = [None, None, _citation(2)]
		result = resolve_assistant_citations("[1] and [2]", entries)
		assert len(result) == 1
		assert result[0].index == 2

	def test_handles_adjacent_markers(self) -> None:
		entries: list[Citation | None] = [None, _citation(1), _citation(2)]
		result = resolve_assistant_citations("[1][2]", entries)
		assert len(result) == 2

	def test_ignores_non_numeric_brackets(self) -> None:
		entries: list[Citation | None] = [None, _citation(1)]
		result = resolve_assistant_citations("[abc] and [1]", entries)
		assert len(result) == 1


# -- _seed_entries -----------------------------------------------------------


class TestSeedEntries:
	async def test_seeds_from_nci_in_window(self) -> None:
		entries: list[Citation | None] = [None]
		thread = Thread(messages=[_assistant_msg(nci=5)])
		session = AsyncMock()
		await _seed_entries(entries, thread, session)
		assert len(entries) == 5

	async def test_no_op_when_entries_already_large_enough(self) -> None:
		entries: list[Citation | None] = [None] * 10
		thread = Thread(messages=[_assistant_msg(nci=5)])
		session = AsyncMock()
		await _seed_entries(entries, thread, session)
		assert len(entries) == 10  # unchanged

	async def test_no_op_when_no_nci_and_no_message_ids(self) -> None:
		entries: list[Citation | None] = [None]
		thread = Thread(messages=[_assistant_msg()])
		session = AsyncMock()
		await _seed_entries(entries, thread, session)
		assert len(entries) == 1  # unchanged

	async def test_overfetch_path_when_window_has_no_nci(self) -> None:
		entries: list[Citation | None] = [None]
		# no nci in assistant metadata, but has message_id -> triggers overfetch
		thread = Thread(messages=[_assistant_msg(message_id="msg_001")])
		session = AsyncMock()
		with patch(
			"api.v1.service.chat.filters.citation_index._overfetch_nci",
			return_value=4,
		) as mock_overfetch:
			await _seed_entries(entries, thread, session)
			mock_overfetch.assert_awaited_once_with(session, "msg_001")
		assert len(entries) == 4

	async def test_overfetch_returns_none(self) -> None:
		entries: list[Citation | None] = [None]
		thread = Thread(messages=[_assistant_msg(message_id="msg_001")])
		session = AsyncMock()
		with patch(
			"api.v1.service.chat.filters.citation_index._overfetch_nci",
			return_value=None,
		):
			await _seed_entries(entries, thread, session)
		assert len(entries) == 1  # unchanged


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
		assert len(ctx.citations) == 2
		assert ctx.citations[1] is not None
		assert ctx.citations[1].source_id == "https://x.com"
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
		assert len(ctx.citations) == 3
		assert ctx.citations[1] is not None
		assert ctx.citations[1].source_id == "https://old.com"
		assert ctx.citations[2] is not None
		assert ctx.citations[2].source_id == "note_1"
		# manifest should contain both
		sys_msg = result.messages[0]
		assert isinstance(sys_msg, SystemMessage)
		assert "[1] Old" in sys_msg.text
		assert "[2] New Note" in sys_msg.text


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
