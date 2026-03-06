"""chat context filter - injects context from other chats into the system prompt."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from api.models.access_rule import AccessLevel
from api.models.thread import Thread
from api.schemas.search import SearchMode, SearchParams
from api.settings import settings as app_settings
from api.settings.settings import AIChatContextSettings
from api.v1.service import threads as thread_service
from api.v1.service.authorization import thread_access_predicate
from api.v1.service.chat.filters.base import Filter
from api.v1.service.prompt_runtime import SENTINEL_CHAT_CONTEXT
from api.v1.service.sorting import apply_sort
from nokodo_ai.threads import Thread as SDKThread
from nokodo_ai.utils.typeid import TypeID


if TYPE_CHECKING:
	from api.v1.service.chat.context import AppContext


logger = logging.getLogger(__name__)


class ChatContextFilter(Filter):
	"""pre-filter that injects context from other conversations.

	supports two modes controlled by settings.ai.chat_context.mode:
	- recent: top K chats ordered by last_activity_at descending.
	- relevant: top K chats by semantic similarity to current messages.

	the retrieval query and embedding are built explicitly in agents.py
	before filters run; this filter only reads from the shared
	RetrievalContext.

	only activates when the admin includes {{ chat_context }} in the
	agent's system prompt. if the variable is absent, the filter is a
	no-op. also gated by settings.ai.chat_context.enabled.
	"""

	name: str = Field(default="chat_context")
	description: str = Field(
		default="injects context from other conversations into the system prompt"
	)

	async def process(
		self,
		thread: SDKThread,
		app_context: AppContext | None,
	) -> SDKThread:
		if app_context is None:
			raise ValueError("AppContext is required for ChatContextFilter")

		cfg = app_settings.ai.chat_context
		if not cfg.enabled:
			self._replace_sentinel(thread, SENTINEL_CHAT_CONTEXT, "")
			return thread

		# locate system message and check for the injection sentinel.
		system_msg = thread.system_message
		if system_msg is None:
			return thread

		system_text = system_msg.text
		if not system_text or SENTINEL_CHAT_CONTEXT not in system_text:
			return thread

		current_thread_id = app_context.thread_id

		if cfg.mode == "relevant":
			threads = await self._fetch_relevant(
				thread, app_context, cfg=cfg, exclude_id=current_thread_id
			)
		else:
			threads = await self._fetch_recent(
				app_context, cfg=cfg, exclude_id=current_thread_id
			)

		content = self._format_threads(threads) if threads else ""
		self._replace_sentinel(thread, SENTINEL_CHAT_CONTEXT, content)
		return thread

	# -- mode implementations --

	async def _fetch_recent(
		self,
		app_context: AppContext,
		*,
		cfg: AIChatContextSettings,
		exclude_id: TypeID | None,
	) -> list[Thread]:
		"""top K most recently active threads."""
		session = app_context.session
		principal = app_context.principal

		stmt = (
			select(Thread)
			.options(selectinload(Thread.summaries))
			.where(
				thread_access_predicate(
					principal,
					required_level=AccessLevel.READER,
				),
				Thread.is_temporary.is_(False),
			)
		)
		if exclude_id is not None:
			stmt = stmt.where(Thread.id != exclude_id)

		stmt = apply_sort(
			stmt,
			sort_by="last_activity_at",
			sort_dir="desc",
			columns={"last_activity_at": Thread.last_activity_at},
			tie_breaker=Thread.id,
		)
		stmt = stmt.limit(cfg.top_k)

		result = await session.execute(stmt)
		return list(result.scalars().unique().all())

	async def _fetch_relevant(
		self,
		thread: SDKThread,
		app_context: AppContext,
		*,
		cfg: AIChatContextSettings,
		exclude_id: TypeID | None,
	) -> list[Thread]:
		"""top K most semantically relevant threads using FULL search mode.

		scored results (from vector search) come first filtered by
		similarity_threshold; unscored autocomplete results fill remaining
		slots up to top_k.
		"""
		session = app_context.session
		principal = app_context.principal
		retrieval = app_context.retrieval

		query_text = retrieval.query_text
		if query_text is None:
			# retrieval_pre_build is off; try to build the query here.
			_turns = thread.recent_turns(app_settings.ai.retrieval_turns)
			if not _turns:
				return []
			query_text = "\n".join(_turns)

		try:
			page = await thread_service.search_threads(
				query_text,
				session,
				principal=principal,
				limit=cfg.top_k * 2,
				query_embedding=retrieval.query_embedding,
				search_params=SearchParams(mode=SearchMode.FULL),
			)
		except Exception:
			logger.exception("chat context: relevant search failed")
			return []

		if not page.items:
			return []

		# split by score presence: vector results have a score, autocomplete do not.
		scored = [
			item
			for item in page.items
			if item.score is not None and item.score >= cfg.similarity_threshold
		]
		unscored = [item for item in page.items if item.score is None]

		# scored results first, then fill remaining slots with unscored.
		merged: list = []
		seen: set[str] = set()
		for item in (*scored, *unscored):
			sid = str(item.id)
			if sid not in seen:
				merged.append(item)
				seen.add(sid)
			if len(merged) >= cfg.top_k:
				break

		result_ids = [item.id for item in merged]
		# exclude current thread
		if exclude_id is not None:
			result_ids = [rid for rid in result_ids if str(rid) != str(exclude_id)]

		if not result_ids:
			return []

		stmt = (
			select(Thread)
			.options(selectinload(Thread.summaries))
			.where(Thread.id.in_(result_ids))
		)
		db_result = await session.execute(stmt)
		by_id = {str(t.id): t for t in db_result.scalars().unique().all()}
		# preserve relevance order
		return [by_id[str(rid)] for rid in result_ids if str(rid) in by_id]

	# -- helpers --

	def _format_threads(self, threads: list[Thread]) -> str:
		"""serialize thread context as a JSON document."""
		entries = []
		for t in threads:
			entry: dict[str, object] = {}
			if t.title:
				entry["title"] = t.title
			if t.tags:
				entry["tags"] = t.tags

			# prefer the most recent summary if available
			summary_text = None
			if t.summaries:
				latest = max(t.summaries, key=lambda s: s.created_at)
				summary_text = latest.content

			if summary_text:
				entry["summary"] = summary_text

			if t.last_activity_at:
				entry["last_activity"] = t.last_activity_at.isoformat()

			if entry:
				entries.append(entry)

		if not entries:
			return ""

		context_json = json.dumps(entries, indent=2, ensure_ascii=False)
		return context_json
