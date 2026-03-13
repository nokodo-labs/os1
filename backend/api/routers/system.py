"""system endpoints outside API versioning."""

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.models.user import User
from api.service import pwa_manifest


router = APIRouter(prefix="/system", tags=["system"])


@router.get("/status")
async def get_system_status(db: AsyncSession = Depends(get_db)) -> dict[str, bool]:
	"""Check system initialization status.

	A system is considered initialized once at least one user exists.
	"""
	result = await db.execute(select(func.count()).select_from(User))
	user_count = result.scalar() or 0
	return {"initialized": user_count > 0}


@router.get("/manifest.json", response_class=Response)
async def get_manifest() -> Response:
	"""serve a compiled PWA manifest derived from settings."""
	body, etag = pwa_manifest.get_manifest_response()
	return Response(
		content=body,
		media_type="application/manifest+json",
		headers={
			"Cache-Control": "public, max-age=3600",
			"ETag": f'"{etag}"',
		},
	)
