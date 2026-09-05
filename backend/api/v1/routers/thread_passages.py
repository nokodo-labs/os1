"""thread passage routes: read-only inspection plus rebuild controls."""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.models.access_rule import AccessLevel
from api.models.thread_passage import ThreadPassage
from api.schemas.thread import (
	ThreadPassageEnrichResponse,
	ThreadPassageReconcileResponse,
	ThreadPassageRecord,
	ThreadPassageUpdate,
)
from api.v1.service.authentication import Principal, get_current_principal
from api.v1.service.authorization import require_thread_access
from api.v1.service.chat.thread_maintenance import (
	enrich_thread_passages as enrich_thread_passages_service,
)
from api.v1.service.threads import (
	get_thread_passage as get_thread_passage_service,
)
from api.v1.service.threads import (
	list_thread_passages as list_thread_passages_service,
)
from api.v1.service.threads import (
	reconcile_thread_content_vectors,
	update_thread_passage_enrichment,
)
from nokodo_ai.utils.typeid import TypeID, assert_typeid


def resolve_passage_id(passage_id: str) -> TypeID:
	"""parse a passage typeid path parameter."""
	try:
		return TypeID(assert_typeid(passage_id))
	except ValueError as exc:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="passage not found",
		) from exc


PassageIDPath = Annotated[TypeID, Depends(resolve_passage_id)]


def create_thread_passages_router(
	resolve_thread_id: Callable[[str], TypeID],
) -> APIRouter:
	"""create passage routes mounted under the threads router.

	passages are derived state, so there is no create or supersede route:
	reconciliation is the only way to (re)produce them.
	"""
	router = APIRouter(prefix="/{thread_id}/passages", tags=["threads"])

	def parse_thread_id(thread_id: str) -> TypeID:
		"""parse a thread id using the owning router's resolver."""
		return resolve_thread_id(thread_id)

	@router.get("", response_model=list[ThreadPassageRecord])
	async def list_thread_passages(
		thread_id: Annotated[TypeID, Depends(parse_thread_id)],
		principal: Principal = Depends(get_current_principal),
		db: AsyncSession = Depends(get_db),
	) -> list[ThreadPassage]:
		"""list stored passage records for a thread. thread admin only."""
		return await list_thread_passages_service(
			thread_id,
			db,
			principal=principal,
		)

	@router.get("/{passage_id}", response_model=ThreadPassageRecord)
	async def get_thread_passage(
		thread_id: Annotated[TypeID, Depends(parse_thread_id)],
		passage_id: PassageIDPath,
		principal: Principal = Depends(get_current_principal),
		db: AsyncSession = Depends(get_db),
	) -> ThreadPassage:
		"""fetch one stored passage record. thread admin only."""
		return await get_thread_passage_service(
			thread_id,
			passage_id,
			db,
			principal=principal,
		)

	@router.patch("/{passage_id}", response_model=ThreadPassageRecord)
	async def update_thread_passage(
		thread_id: Annotated[TypeID, Depends(parse_thread_id)],
		passage_id: PassageIDPath,
		passage_in: ThreadPassageUpdate,
		principal: Principal = Depends(get_current_principal),
		db: AsyncSession = Depends(get_db),
	) -> ThreadPassage:
		"""override or clear a passage enrichment. thread admin only."""
		return await update_thread_passage_enrichment(
			thread_id,
			passage_id,
			passage_in,
			db,
			principal=principal,
		)

	@router.post("/reconcile", response_model=ThreadPassageReconcileResponse)
	async def reconcile_thread_passages(
		thread_id: Annotated[TypeID, Depends(parse_thread_id)],
		principal: Principal = Depends(get_current_principal),
		db: AsyncSession = Depends(get_db),
	) -> ThreadPassageReconcileResponse:
		"""converge stored passages and their vectors. thread admin only."""
		await require_thread_access(
			thread_id, db, principal, required_level=AccessLevel.ADMIN
		)
		summaries = await reconcile_thread_content_vectors(db, thread_ids=[thread_id])
		await db.flush()
		return ThreadPassageReconcileResponse.model_validate(summaries[0])

	@router.post("/enrich", response_model=ThreadPassageEnrichResponse)
	async def enrich_thread_passages(
		thread_id: Annotated[TypeID, Depends(parse_thread_id)],
		principal: Principal = Depends(get_current_principal),
		db: AsyncSession = Depends(get_db),
	) -> ThreadPassageEnrichResponse:
		"""generate search context for unenriched passages. thread admin only."""
		await require_thread_access(
			thread_id, db, principal, required_level=AccessLevel.ADMIN
		)
		enriched = await enrich_thread_passages_service(thread_id, db)
		await db.flush()
		return ThreadPassageEnrichResponse(thread_id=thread_id, enriched=enriched)

	return router
