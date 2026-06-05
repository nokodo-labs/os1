"""citation index filter - assigns citation indices to tool results.

runs before each model call. scans context for citeable tool outputs,
assigns conversation-cumulative [n] indices,
rewrites tool output to include markers, and injects a reference card
into the system prompt so the model knows which sources are available.

citation state is seeded from ``_next_citation_index`` stored in assistant
message metadata, so partial branch loads (future) don't require walking
the full history.
"""

from __future__ import annotations

import logging
import re

from pydantic import Field
from sqlalchemy import String, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.event import Event, EventScope
from api.models.event_types import EventType
from api.schemas.message import Citation, CitationSource
from api.v1.service.chat.context import AppContext
from api.v1.service.chat.filters.base import Filter
from api.v1.service.chat.message_metadata import (
	CITABLE_SOURCES_KEY,
	CITATIONS_ASSIGNED_KEY,
	CITATIONS_KEY,
	NEXT_CITATION_INDEX_KEY,
	get_message_id,
)
from api.v1.service.prompts import SENTINEL_CITATION_SOURCES
from nokodo_ai.agents import AgentIterationState
from nokodo_ai.context import AgentContext
from nokodo_ai.messages import (
	AssistantMessage as SDKAssistantMessage,
)
from nokodo_ai.messages import (
	ToolMessage as SDKToolMessage,
)
from nokodo_ai.threads import Thread as SDKThread


logger = logging.getLogger(__name__)


class CitationIndexFilter(Filter):
	"""assign citation indices to tool results and build a reference card.

	tools can attach private ``_citable_sources`` metadata to their output.
	this filter turns those sources into stable numbered citations, appends
	the numbers to the tool result visible to the model, emits per-message
	source events for the UI, and replaces the citation sentinel in the
	system prompt with a compact source list.

	indices continue from persisted ``_next_citation_index`` metadata so a
	windowed thread does not reuse old citation numbers.
	"""

	name: str = Field(default="citation_index")
	description: str = Field(
		default=(
			"turns citeable tool sources into stable numbered citations and "
			"adds the source list to the prompt"
		),
	)

	async def process(
		self,
		state: AgentIterationState[AppContext],
		agent_context: AgentContext,
		app_context: AppContext | None,
	) -> AgentIterationState[AppContext]:
		"""assign citation indices and inject the citation manifest for a run."""
		_ = agent_context
		if app_context is None:
			return state
		thread = state.thread

		entries = app_context.citations

		# resolve the next-citation-index floor from persisted metadata.
		# this tells us where new indices should start even when the
		# original citations aren't in the loaded window.
		nci = await _resolve_nci(thread, app_context.session)

		# rebuild individual citation entries from persisted citations
		_rebuild_from_existing(thread, entries)
		# assign indices to new tool results
		citations_by_msg = self._assign_new_citations(thread, entries, nci)
		# inject reference card into system prompt
		self._inject_manifest(thread, entries)

		# emit per-message citation source events so frontends can build
		# the sources map before the assistant message streams.
		thread_id = app_context.thread_id
		if citations_by_msg and not thread_id:
			logger.warning("skipping citation event: no thread_id on app_context")
		elif citations_by_msg and thread_id:
			for msg_id, citations in citations_by_msg.items():
				await app_context.event_emitter(
					Event(
						scope=EventScope.MESSAGE,
						scope_id=msg_id,
						type=EventType.CITATION_SOURCES,
						data={
							"thread_id": str(thread_id),
							"citations": [c.model_dump(mode="json") for c in citations],
						},
						user_id=app_context.user_id,
						thread_id=thread_id,
						message_id=msg_id,
					)
				)

		return state

	def _assign_new_citations(
		self,
		thread: SDKThread,
		entries: list[Citation],
		nci: int,
	) -> dict[str, list[Citation]]:
		"""find tool messages with citeable sources and assign indices.

		deduplicates by (source_type, source_id): if the same source was
		already assigned an index (within the current window), reuse it
		instead of allocating a new one. sources without a meaningful
		source_id (empty string) are never deduplicated.

		returns a dict mapping tool message_id to newly assigned citations.
		"""
		by_message: dict[str, list[Citation]] = {}
		# dedup index: reuse existing citation when the same source appears again
		seen: dict[tuple[str, str], Citation] = {
			(c.source_type, c.source_id): c for c in entries if c.source_id
		}
		for i, msg in enumerate(thread.messages):
			if not isinstance(msg, SDKToolMessage):
				continue
			meta = msg.metadata or {}
			if meta.get(CITATIONS_ASSIGNED_KEY):
				continue
			sources = meta.get(CITABLE_SOURCES_KEY)
			if sources is None:
				continue
			if not isinstance(sources, list):
				raise TypeError("_citable_sources must be a list")

			assigned: list[Citation] = []
			for src in sources:
				if not isinstance(src, dict):
					raise TypeError("_citable_sources items must be objects")
				src_type = str(src["source_type"])
				src_id = str(src.get("source_id", ""))
				dedup_key = (src_type, src_id)
				if src_id and dedup_key in seen:
					assigned.append(seen[dedup_key])
					continue
				idx = _next_index(entries, nci)
				raw_title = src.get("title")
				entry = Citation(
					index=idx,
					source_type=CitationSource(src_type),
					source_id=src_id,
					title=str(raw_title) if raw_title is not None else None,
				)
				entries.append(entry)
				if src_id:
					seen[dedup_key] = entry
				assigned.append(entry)

			if not assigned:
				continue

			# track per source tool message for event scoping
			msg_id = get_message_id(msg)
			if msg_id:
				by_message.setdefault(msg_id, []).extend(assigned)

			# rewrite tool output to append citation markers
			source_lines = [
				f"[{e.index}] {e.title or e.source_id or e.source_type}"
				for e in assigned
			]
			new_output = msg.tool_output + "\n\nsources:\n" + "\n".join(source_lines)
			# mark as processed so we don't re-assign on next iteration
			new_meta = {**meta, CITATIONS_ASSIGNED_KEY: True}
			thread.messages[i] = msg.model_copy(
				update={
					"tool_output": new_output,
					"metadata": new_meta,
				}
			)

		return by_message

	def _inject_manifest(
		self,
		thread: SDKThread,
		entries: list[Citation],
	) -> None:
		"""replace the citation_sources sentinel with a reference card."""
		if not entries:
			self._replace_sentinel(thread, SENTINEL_CITATION_SOURCES, "")
			return

		lines = []
		for entry in entries:
			label = entry.title or entry.source_id or entry.source_type
			lines.append(f"[{entry.index}] {label}")

		manifest = "\n".join(lines)
		self._replace_sentinel(thread, SENTINEL_CITATION_SOURCES, manifest)


# helpers (module-level for testability)


def _next_index(entries: list[Citation], nci: int) -> int:
	"""compute the next 1-based citation index.

	takes the highest existing index in entries and nci (persisted floor)
	into account so indices never collide or go backwards.
	"""
	highest = entries[-1].index if entries else 0
	return max(highest, nci - 1) + 1


async def _resolve_nci(
	thread: SDKThread,
	session: AsyncSession,
) -> int:
	"""find the next-citation-index from the loaded window or overfetch.

	returns 0 when no nci metadata is found anywhere.
	"""
	nci = _find_nci_in_window(thread)
	if nci is None:
		oldest_id = _oldest_message_id(thread)
		if oldest_id is not None:
			nci = await _overfetch_nci(session, oldest_id)
	return nci or 0


def _find_nci_in_window(thread: SDKThread) -> int | None:
	"""find the highest next_citation_index on assistant messages."""
	best: int | None = None
	for msg in thread.messages:
		if not isinstance(msg, SDKAssistantMessage):
			continue
		meta = msg.metadata or {}
		val = meta.get(NEXT_CITATION_INDEX_KEY)
		if isinstance(val, int) and val > 1:
			if best is None or val > best:
				best = val
	return best


def _oldest_message_id(thread: SDKThread) -> str | None:
	"""get message_id of the first loaded message (oldest in branch)."""
	for msg in thread.messages:
		mid = get_message_id(msg)
		if mid:
			return mid
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
			msg_t.c.metadata[NEXT_CITATION_INDEX_KEY]
			.astext.cast(type_=String)
			.label("nci"),
		)
		.join(ancestors_cte, msg_t.c.id == ancestors_cte.c.cur_id)
		.where(
			msg_t.c.type == "assistant",
			msg_t.c.metadata.has_key(NEXT_CITATION_INDEX_KEY),
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
	entries: list[Citation],
) -> None:
	"""scan assistant messages for persisted citations and fill entries."""
	seen: set[int] = {c.index for c in entries}
	for msg in thread.messages:
		if not isinstance(msg, SDKAssistantMessage):
			continue
		msg_meta = msg.metadata or {}
		raw_citations = msg_meta.get(CITATIONS_KEY)
		if not isinstance(raw_citations, list):
			continue
		for citation_data in raw_citations:
			if not isinstance(citation_data, dict):
				continue
			idx = citation_data.get("index")
			if not isinstance(idx, int) or idx < 1:
				continue
			if idx in seen:
				continue
			try:
				entries.append(Citation.model_validate(citation_data))
				seen.add(idx)
			except Exception:
				logger.debug("skipping invalid persisted citation at [%d]", idx)
	# keep entries sorted by index for consistent ordering
	entries.sort(key=lambda c: c.index)


def resolve_assistant_citations(
	text: str,
	entries: list[Citation],
) -> list[Citation]:
	"""extract citation markers from assistant text, resolve to Citation objects.

	matches both ``[n]`` and markdown footnote ``[^n]`` syntax so that
	citations are captured regardless of how the model formats them.

	returns a list of Citation instances ready for message.citations persistence.
	"""
	if not entries or not text:
		return []

	by_index: dict[int, Citation] = {c.index: c for c in entries}

	used_indices: set[int] = set()
	for match in re.finditer(r"\[\^?(\d+)\]", text):
		idx = int(match.group(1))
		if idx in by_index:
			used_indices.add(idx)

	return [by_index[idx] for idx in sorted(used_indices)]
