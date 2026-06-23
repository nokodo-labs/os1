"""thread summary routes."""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.models.thread_summary import SummaryPurpose, ThreadSummary
from api.schemas.thread import ThreadSummaryRecord, ThreadSummaryUpdate
from api.v1.service.auth import Principal, get_current_principal
from api.v1.service.threads import summaries as thread_summary_service
from nokodo_ai.utils.typeid import TypeID, assert_typeid


def resolve_summary_id(summary_id: str) -> TypeID:
	"""parse a summary typeid path parameter."""
	try:
		return TypeID(assert_typeid(summary_id))
	except ValueError as exc:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="summary not found",
		) from exc


SummaryIDPath = Annotated[TypeID, Depends(resolve_summary_id)]


def create_thread_summaries_router(
	resolve_thread_id: Callable[[str], TypeID],
) -> APIRouter:
	"""create summary routes mounted under the threads router."""
	router = APIRouter(prefix="/{thread_id}/summaries", tags=["threads"])

	def parse_thread_id(thread_id: str) -> TypeID:
		"""parse a thread id using the owning router's resolver."""
		return resolve_thread_id(thread_id)

	@router.get("", response_model=list[ThreadSummaryRecord])
	async def list_thread_summaries(
		thread_id: Annotated[TypeID, Depends(parse_thread_id)],
		include_superseded: bool = False,
		purpose: SummaryPurpose | None = None,
		principal: Principal = Depends(get_current_principal),
		db: AsyncSession = Depends(get_db),
	) -> list[ThreadSummary]:
		"""list stored summary records for a thread."""
		return await thread_summary_service.list_thread_summaries(
			thread_id,
			db,
			principal=principal,
			include_superseded=include_superseded,
			purpose=purpose,
		)

	@router.get(
		"/{summary_id}",
		response_model=ThreadSummaryRecord,
	)
	async def get_thread_summary(
		thread_id: Annotated[TypeID, Depends(parse_thread_id)],
		summary_id: SummaryIDPath,
		principal: Principal = Depends(get_current_principal),
		db: AsyncSession = Depends(get_db),
	) -> ThreadSummary:
		"""fetch one stored summary record."""
		return await thread_summary_service.get_thread_summary(
			thread_id,
			summary_id,
			db,
			principal=principal,
		)

	@router.patch(
		"/{summary_id}",
		response_model=ThreadSummaryRecord,
	)
	async def update_thread_summary(
		thread_id: Annotated[TypeID, Depends(parse_thread_id)],
		summary_id: SummaryIDPath,
		summary_in: ThreadSummaryUpdate,
		principal: Principal = Depends(get_current_principal),
		db: AsyncSession = Depends(get_db),
	) -> ThreadSummary:
		"""update a stored summary record. admin only."""
		return await thread_summary_service.update_thread_summary(
			thread_id,
			summary_id,
			summary_in,
			db,
			principal=principal,
		)

	@router.delete(
		"/{summary_id}",
		status_code=status.HTTP_204_NO_CONTENT,
	)
	async def delete_thread_summary(
		thread_id: Annotated[TypeID, Depends(parse_thread_id)],
		summary_id: SummaryIDPath,
		principal: Principal = Depends(get_current_principal),
		db: AsyncSession = Depends(get_db),
	) -> None:
		"""delete a stored summary record. admin only."""
		await thread_summary_service.delete_thread_summary(
			thread_id,
			summary_id,
			db,
			principal=principal,
		)

	return router
