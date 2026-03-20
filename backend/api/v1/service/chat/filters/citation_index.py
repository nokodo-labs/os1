"""citation index filter - assigns citation indices to tool results.

runs before each model call. scans context for tool messages with
citable_sources metadata, assigns conversation-cumulative [n] indices,
rewrites tool output to include markers, and injects a reference card
into the system prompt so the model knows which sources are available.

citation state is seeded from ``next_citation_index`` stored in assistant
message metadata, so partial branch loads (future) don't require walking
the full history.
"""

from __future__ import annotations

import logging
import re

from pydantic import Field
from sqlalchemy import String, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.citations import Citation, CitationSource
from api.v1.service.chat.context import AppContext
from api.v1.service.chat.filters.base import Filter
from api.v1.service.prompt_runtime import SENTINEL_CITATION_SOURCES
from nokodo_ai.messages import (
	AssistantMessage as SDKAssistantMessage,
)
from nokodo_ai.messages import (
	ToolMessage as SDKToolMessage,
)
from nokodo_ai.threads import Thread as SDKThread


logger = logging.getLogger(__name__)

# tag stored on tool message metadata after citation indices are assigned
_CITATIONS_ASSIGNED_KEY = "_citations_assigned"

# metadata key on assistant messages holding the running index
_NCI_KEY = "next_citation_index"


def _ensure_slot(entries: list[Citation | None], index: int) -> None:
	"""grow the list so entries[index] is addressable."""
	while len(entries) <= index:
		entries.append(None)


class CitationIndexFilter(Filter):
	"""assign citation indices to tool results and build a reference card."""

	name: str = Field(default="citation_index")
	description: str = Field(
		default="assigns [n] citation markers to tool results",
	)

	async def process(
		self,
		thread: SDKThread,
		app_context: AppContext | None,
	) -> SDKThread:
		if app_context is None:
			return thread

		entries = app_context.citations

		# seed the entries list from the highest next_citation_index
		# found on any assistant message in the loaded window.
		# this handles both full-branch and partial-branch loads.
		await _seed_entries(entries, thread, app_context.session)

		# rebuild individual citation entries from persisted citations
		_rebuild_from_existing(thread, entries)
		# assign indices to new tool results
		self._assign_new_citations(thread, entries)
		# inject reference card into system prompt
		self._inject_manifest(thread, entries)

		return thread

	def _assign_new_citations(
		self,
		thread: SDKThread,
		entries: list[Citation | None],
	) -> None:
		"""find tool messages with citable_sources and assign indices."""
		for i, msg in enumerate(thread.messages):
			if not isinstance(msg, SDKToolMessage):
				continue
			meta = msg.metadata or {}
			if meta.get(_CITATIONS_ASSIGNED_KEY):
				continue
			sources = meta.get("citable_sources")
			if not sources or not isinstance(sources, list):
				continue

			assigned: list[Citation] = []
			for src in sources:
				if not isinstance(src, dict) or "source_type" not in src:
					continue
				idx = max(len(entries), 1)
				raw_title = src.get("title")
				entry = Citation(
					index=idx,
					source_type=CitationSource(str(src["source_type"])),
					source_id=str(src.get("source_id", "")),
					title=str(raw_title) if raw_title is not None else None,
				)
				entries.append(entry)
				assigned.append(entry)

			if not assigned:
				continue

			# rewrite tool output to append citation markers
			source_lines = [
				f"[{e.index}] {e.title or e.source_id or e.source_type}"
				for e in assigned
			]
			new_output = msg.tool_output + "\n\nsources:\n" + "\n".join(source_lines)
			# mark as processed so we don't re-assign on next iteration
			new_meta = {**meta, _CITATIONS_ASSIGNED_KEY: True}
			thread.messages[i] = msg.model_copy(
				update={
					"tool_output": new_output,
					"metadata": new_meta,
				}
			)

	def _inject_manifest(
		self,
		thread: SDKThread,
		entries: list[Citation | None],
	) -> None:
		"""replace the citation_sources sentinel with a reference card."""
		if len(entries) <= 1:
			self._replace_sentinel(thread, SENTINEL_CITATION_SOURCES, "")
			return

		lines = []
		for entry in entries:
			if entry is None:
				continue
			label = entry.title or entry.source_id or entry.source_type
			lines.append(f"[{entry.index}] {label}")

		manifest = "\n".join(lines)
		self._replace_sentinel(thread, SENTINEL_CITATION_SOURCES, manifest)


# -- seeding and rebuild helpers (module-level for testability) ----------------


async def _seed_entries(
	entries: list[Citation | None],
	thread: SDKThread,
	session: AsyncSession,
) -> None:
	"""ensure entries has at least ``next_citation_index`` slots.

	walks assistant messages in reverse to find the latest
	next_citation_index. if none found in the loaded window,
	falls back to an overfetch query.
	"""
	nci = _find_nci_in_window(thread)
	if nci is None:
		# overfetch: walk the branch upward from the oldest loaded
		# message until an assistant message with the key is found.
		oldest_id = _oldest_message_id(thread)
		if oldest_id is not None:
			nci = await _overfetch_nci(session, oldest_id)
	if nci is not None and nci > len(entries):
		while len(entries) < nci:
			entries.append(None)


def _find_nci_in_window(thread: SDKThread) -> int | None:
	"""find the highest next_citation_index on assistant messages."""
	best: int | None = None
	for msg in thread.messages:
		if not isinstance(msg, SDKAssistantMessage):
			continue
		meta = msg.metadata or {}
		val = meta.get(_NCI_KEY)
		if isinstance(val, int) and val > 1:
			if best is None or val > best:
				best = val
	return best


def _oldest_message_id(thread: SDKThread) -> str | None:
	"""get message_id of the first loaded message (oldest in branch)."""
	for msg in thread.messages:
		mid = (msg.metadata or {}).get("message_id")
		if mid:
			return str(mid)
	return None


async def _overfetch_nci(
	session: AsyncSession,
	oldest_loaded_id: str,
) -> int | None:
	"""walk the branch upward from oldest_loaded_id to find next_citation_index.

	uses a recursive CTE limited to assistant messages that have the key.
	stops as soon as one is found (LIMIT 1, ordered by depth ASC).
	"""
	from api.models.message import Message

	msg_t = Message.__table__

	# anchor: parent of the oldest loaded message
	anchor = (
		select(
			msg_t.c.parent_id.label("cur_id"),
			literal(0).label("depth"),
		)
		.where(msg_t.c.id == oldest_loaded_id)
		.cte(name="ancestors", recursive=True)
	)

	recursive = select(
		msg_t.c.parent_id.label("cur_id"),
		(anchor.c.depth + 1).label("depth"),
	).where(msg_t.c.id == anchor.c.cur_id)

	ancestors_cte = anchor.union_all(recursive)

	# join back to messages to read metadata, filter to assistant + has key
	stmt = (
		select(
			msg_t.c.metadata[_NCI_KEY].astext.cast(type_=String).label("nci"),
		)
		.join(ancestors_cte, msg_t.c.id == ancestors_cte.c.cur_id)
		.where(
			msg_t.c.type == "assistant",
			msg_t.c.metadata.has_key(_NCI_KEY),
		)
		.order_by(ancestors_cte.c.depth.asc())
		.limit(1)
	)

	result = await session.execute(stmt)
	row = result.one_or_none()
	if row is not None:
		try:
			return int(row.nci)
		except (TypeError, ValueError):
			pass
	return None


def _rebuild_from_existing(
	thread: SDKThread,
	entries: list[Citation | None],
) -> None:
	"""scan assistant messages for persisted citations and rebuild map."""
	for msg in thread.messages:
		if not isinstance(msg, SDKAssistantMessage):
			continue
		msg_meta = msg.metadata or {}
		raw_citations = msg_meta.get("citations")
		if not isinstance(raw_citations, list):
			continue
		for citation_data in raw_citations:
			if not isinstance(citation_data, dict):
				continue
			idx = citation_data.get("index")
			if not isinstance(idx, int) or idx < 1:
				continue
			_ensure_slot(entries, idx)
			if entries[idx] is not None:
				continue
			try:
				entries[idx] = Citation.model_validate(citation_data)
			except Exception:
				logger.debug("skipping invalid persisted citation at [%d]", idx)


def resolve_assistant_citations(
	text: str,
	entries: list[Citation | None],
) -> list[Citation]:
	"""extract [n] markers from assistant text, resolve to Citation objects.

	returns a list of Citation instances ready for message.citations persistence.
	"""
	if len(entries) <= 1 or not text:
		return []

	used_indices: set[int] = set()
	for match in re.finditer(r"\[(\d+)\]", text):
		idx = int(match.group(1))
		if 0 < idx < len(entries) and entries[idx] is not None:
			used_indices.add(idx)

	citations: list[Citation] = []
	for idx in sorted(used_indices):
		entry = entries[idx]
		if entry is not None:
			citations.append(entry)
	return citations
