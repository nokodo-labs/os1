"""vectorstore admin router - collection management and diagnostics."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.schemas.search import SearchMode
from api.v1.service.authentication import Principal, get_current_principal
from api.v1.service.authorization import require_admin
from api.v1.service.embeddings import embed_text
from api.v1.service.search.aggregator import vectorize
from api.v1.service.vectorstores import (
	delete_collection as delete_collection_service,
)
from api.v1.service.vectorstores import (
	get_collection as get_collection_service,
)
from api.v1.service.vectorstores import (
	get_collection_info,
	search,
)
from api.v1.service.vectorstores import (
	list_collections as list_collections_service,
)
from api.v1.service.vectorstores import (
	wipe_all_collections as wipe_all_collections_service,
)
from nokodo_ai.types.json import JSONObject


router = APIRouter(prefix="/vectorstores", tags=["vectorstores"])


# collection management


@router.get("/collections")
async def list_collections(
	principal: Principal = Depends(get_current_principal),
) -> list[dict[str, object]]:
	"""list all vectorstore collections. admin only."""
	require_admin(principal)
	return await list_collections_service()


@router.get("/collections/{name}")
async def get_collection(
	name: str,
	principal: Principal = Depends(get_current_principal),
) -> dict[str, object]:
	"""get detailed info for a specific collection. admin only."""
	require_admin(principal)
	try:
		return await get_collection_info(name)
	except Exception as exc:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail=f"collection not found: {name}",
		) from exc


@router.delete("/collections/{name}")
async def delete_collection(
	name: str,
	principal: Principal = Depends(get_current_principal),
) -> dict[str, str]:
	"""delete a collection. admin only."""
	require_admin(principal)
	deleted = await delete_collection_service(name)
	if not deleted:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail=f"collection not found: {name}",
		)
	return {"status": "deleted", "name": name}


@router.delete("/collections")
async def wipe_all_collections(
	principal: Principal = Depends(get_current_principal),
) -> dict[str, list[str]]:
	"""delete ALL collections. admin only. use with caution."""
	require_admin(principal)
	deleted = await wipe_all_collections_service()
	return {"deleted": deleted}


# search diagnostics


@router.post("/search")
async def search_collection(
	q: str = Query(min_length=1, max_length=500),
	collection: str | None = Query(default=None),
	limit: int = Query(default=10, ge=1, le=100),
	mode: SearchMode = Query(default=SearchMode.HYBRID),
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[dict[str, object]]:
	"""run a raw search against a collection. admin only.

	returns raw chunk results with scores for diagnostics.
	"""
	require_admin(principal)
	coll = collection or await get_collection_service(db)
	query_emb = await embed_text(q, db, input_type="query")

	text_query: str | None = q
	query_vec: list[float] | None = query_emb
	if mode == SearchMode.DENSE:
		text_query = None
	elif mode == SearchMode.SPARSE:
		query_vec = None

	results = await search(
		session=db,
		query=query_vec,
		text_query=text_query,
		limit=limit,
		collection=coll,
	)
	return [
		{
			"id": r.id,
			"score": r.score,
			"content": r.content[:200] if r.content else "",
			"metadata": r.metadata,
		}
		for r in results
	]


# revectorize


@router.post("/revectorize")
async def revectorize_all(
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> JSONObject:
	"""vectorize all searchable resources. admin only."""
	require_admin(principal)
	return await vectorize(db)
