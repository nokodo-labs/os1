"""run reconciliation for thread access changes and deletion."""

import asyncio
import logging

from fastapi import HTTPException

from api.database import async_session_local
from api.models.access_rule import AccessLevel
from api.permissions import ResourceType
from api.v1.service.authentication import load_principal_for_user
from api.v1.service.authorization import (
	read_access_change_batch,
	require_thread_access,
)
from api.v1.service.runs.access_cursors import (
	access_revision_cursor,
	drop_access_revision_cursor,
	set_access_revision_cursor,
)
from api.v1.service.runs.contracts import KeyedLockRegistry, keyed_lock
from api.v1.service.runs.failures import terminate_run
from api.v1.service.runs.status import run_registry, run_streams
from api.v1.service.threads import filter_active_thread_ids
from nokodo_ai.utils.typeid import TypeID, is_typeid


logger = logging.getLogger(__name__)

_access_replay_locks: KeyedLockRegistry = {}
"""per-thread locks serializing ACL replays for one thread."""
_access_replay_locks_guard = asyncio.Lock()
"""guards the replay lock registry itself."""


async def handle_access_updated(payload: dict[str, object]) -> None:
	"""replay a thread's durable access revisions for its local runs."""
	data = payload.get("data")
	if not isinstance(data, dict) or data.get("resource_type") != "thread":
		return
	resource_id = data.get("resource_id")
	if not isinstance(resource_id, str):
		return
	if not is_typeid(resource_id, prefix="thread"):
		return
	thread_id = TypeID(resource_id)
	await replay_thread_acl_updates(thread_id)


async def handle_thread_deleted(payload: dict[str, object]) -> None:
	"""terminate local runs when their thread is deleted."""
	data = payload.get("data")
	if not isinstance(data, dict):
		return
	thread_id_raw = data.get("id")
	if not isinstance(thread_id_raw, str):
		return
	if not is_typeid(thread_id_raw, prefix="thread"):
		return
	thread_id = TypeID(thread_id_raw)
	await terminate_local_thread_runs(thread_id)


async def handle_access_defaults_changed(payload: dict[str, object]) -> None:
	"""terminate local thread runs when coarse authorization defaults change."""
	data = payload.get("data")
	if not isinstance(data, dict):
		return
	resource_types = data.get("resource_types")
	if not isinstance(resource_types, list) or not all(
		isinstance(value, str) for value in resource_types
	):
		return
	if not {ResourceType.THREAD.value, ResourceType.PROJECT.value} & set(
		resource_types
	):
		return
	thread_ids = {
		run.thread_id
		for run in await run_registry.get_all_active_runs()
		if run.thread_id is not None
	}
	for thread_id in thread_ids:
		await terminate_local_thread_runs(thread_id)


async def replay_local_thread_acl_updates() -> None:
	"""reconcile local thread runs, then catch up their access revisions."""
	thread_ids = {
		run.thread_id
		for run in await run_registry.get_all_active_runs()
		if run.thread_id is not None
	}
	if not thread_ids:
		return
	async with async_session_local() as session:
		active_thread_ids = await filter_active_thread_ids(
			session,
			thread_ids,
		)
	for thread_id in thread_ids - active_thread_ids:
		await terminate_local_thread_runs(thread_id)
	for thread_id in active_thread_ids:
		await replay_thread_acl_updates(thread_id)


async def terminate_local_thread_runs(thread_id: TypeID) -> None:
	"""terminate every active run owned locally for one thread."""
	for run_id in await run_registry.local_run_ids(thread_id):
		cancelled = await run_registry.cancel_run(run_id, reason="access changed")
		if not cancelled:
			await terminate_run(run_id, reason="access changed")
	drop_access_revision_cursor(thread_id)


def _is_writer_model_transition(transition: object) -> bool:
	"""whether one access record crossed the thread's writer model."""
	return isinstance(transition, dict) and transition.get(
		"before"
	) is not transition.get("after")


async def replay_thread_acl_updates(thread_id: TypeID) -> None:
	"""replay resolved access events after the process cursor."""
	async with keyed_lock(_access_replay_locks, _access_replay_locks_guard, thread_id):
		await _replay_thread_acl_updates(thread_id)


async def _replay_thread_acl_updates(thread_id: TypeID) -> None:
	"""reconcile one thread's local runs against its access revisions.

	fails CLOSED: a replay that cannot read the revisions cannot prove the runs
	are still authorized, so it ends them rather than assuming.
	"""
	if not await run_registry.local_run_ids(thread_id):
		drop_access_revision_cursor(thread_id)
		return
	try:
		async with async_session_local() as session:
			batch = await read_access_change_batch(
				(ResourceType.THREAD, thread_id),
				access_revision_cursor(thread_id),
				session,
			)
			writer_model_changed = any(
				_is_writer_model_transition(
					record.metadata.get("thread.writer_model.multi_writer")
				)
				for record in batch.records
			)
	except Exception:
		logger.exception(
			"thread access revision replay failed closed",
			extra={"thread_id": str(thread_id)},
		)
		await terminate_local_thread_runs(thread_id)
		return

	# the writer model picks the thread's topology, so a run that crossed it
	# is answering into a conversation shaped differently from the one it was
	# built for. every other ACL revision leaves the topology alone - most of
	# them only widen access - and a live answer survives it.
	if writer_model_changed:
		await terminate_local_thread_runs(thread_id)
		return
	# the run survives, but the people watching it are re-checked: access was
	# resolved once when each stream attached, so a revocation since then is
	# only enforced here.
	await detach_unauthorized_subscribers(thread_id)
	set_access_revision_cursor(thread_id, batch.current_revision)


async def detach_unauthorized_subscribers(thread_id: TypeID) -> None:
	"""end the streams of users who no longer read this thread's runs.

	resolved per user rather than per stream: one person watching a run from
	three tabs is one access question, and the answer is the same for all
	three.
	"""
	watchers = await run_streams.subscribed_user_ids(thread_id)
	if not watchers:
		return
	revoked: set[TypeID] = set()
	async with async_session_local() as session:
		for user_id in watchers:
			principal = await load_principal_for_user(user_id, session)
			try:
				await require_thread_access(
					thread_id,
					session,
					principal,
					required_level=AccessLevel.READER,
				)
			except HTTPException:
				revoked.add(user_id)
	detached = await run_streams.detach_thread_subscribers(thread_id, revoked)
	if detached:
		logger.info(
			"detached run subscribers who lost thread access",
			extra={"thread_id": str(thread_id), "streams": detached},
		)
