"""find a run wherever it lives, and decide who may act on it."""

from dataclasses import dataclass

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.access_rule import AccessLevel
from api.v1.service.authentication import Principal
from api.v1.service.authorization import require_thread_access
from api.v1.service.runs.bus import read_run_route
from api.v1.service.runs.status import RunSnapshot, run_registry
from nokodo_ai.utils.typeid import TypeID


@dataclass(frozen=True, slots=True)
class ResolvedRun:
	"""one run's coordinates, from whichever worker knows them.

	a run lives in exactly one process, so every entry point that is not that
	process reads the same coordinates off its route. the two sources answer
	the same questions, which is why callers take this instead of branching on
	where the answer came from.
	"""

	run_id: TypeID
	"""the run these coordinates describe."""
	thread_id: TypeID | None
	"""conversation the run answers; None for an ephemeral run."""
	agent_id: TypeID
	"""agent doing the answering."""
	owner_id: TypeID
	"""user who started the run, which is who governs it when no thread does."""
	persist: bool
	"""whether the run writes its output to the conversation."""
	container_root_id: TypeID | None
	"""sub-thread the run answers in; None for the canon conversation."""
	local_status: RunSnapshot | None
	"""this process's view of the run, when it owns it."""

	@property
	def is_local(self) -> bool:
		"""whether this process owns the run and can reach it directly."""
		return self.local_status is not None

	@property
	def conversation_bound(self) -> bool:
		"""whether ``container_root_id`` names a resolved conversation.

		a route is only published once the run knows what it answers, so a
		remote run reached through one is bound by construction.
		"""
		if self.local_status is None:
			return True
		return self.local_status.conversation_bound


async def find_run(run_id: TypeID) -> ResolvedRun | None:
	"""locate a run in this process, then on the bus. None if neither knows it."""
	rs = await run_registry.get_run(run_id)
	if rs is not None:
		return ResolvedRun(
			run_id=run_id,
			thread_id=rs.thread_id,
			agent_id=rs.agent_id,
			owner_id=rs.user_id,
			persist=rs.persist,
			container_root_id=rs.container_root_id,
			local_status=rs,
		)
	route = await read_run_route(run_id)
	if route is None:
		return None
	return ResolvedRun(
		run_id=run_id,
		thread_id=route.thread_id,
		agent_id=route.agent_id,
		owner_id=route.user_id,
		persist=route.persist,
		container_root_id=route.container_root_id,
		local_status=None,
	)


async def resolve_authorized_run(
	run_id: TypeID,
	principal: Principal,
	db: AsyncSession,
	required_level: AccessLevel,
) -> ResolvedRun:
	"""locate a run and require the caller's access to what it answers.

	a thread-bound run is governed by its thread, so anyone with the required
	level there may act on it. an ephemeral run has no thread to govern it, so
	only its owner may - and to anyone else it does not exist.
	"""
	resolved = await find_run(run_id)
	if resolved is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="run not found",
		)
	await authorize_run(resolved, principal, db, required_level)
	return resolved


async def authorize_run(
	resolved: ResolvedRun,
	principal: Principal,
	db: AsyncSession,
	required_level: AccessLevel,
) -> None:
	"""require the caller's access to an already-located run."""
	if resolved.thread_id is not None:
		await require_thread_access(
			resolved.thread_id,
			db,
			principal,
			required_level=required_level,
		)
		return
	if resolved.owner_id != principal.user.id:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="run not found",
		)


def require_steerable_thread(resolved: ResolvedRun) -> TypeID:
	"""require a run whose conversation can take a steering write.

	steering writes into the conversation, so a run that persists nothing has
	nowhere to put it. a run with no thread always has ``persist=False``, so
	the one check covers both.
	"""
	if not resolved.persist or resolved.thread_id is None:
		raise HTTPException(
			status_code=status.HTTP_409_CONFLICT,
			detail="cannot steer a non-persisted run",
		)
	return resolved.thread_id
