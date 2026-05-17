"""system endpoints outside API versioning."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.models.user import User
from api.service import pwa_manifest
from api.settings import settings


router = APIRouter(prefix="/system", tags=["system"])

SOURCE_REPO = "https://github.com/nokodo-labs/os1"


@router.get("/about")
async def get_about() -> dict[str, str]:
	"""Attribution and program information (API Attribution Surface)."""
	return {
		"program": "OS1",
		"attribution": "by nokodo",
		"source": SOURCE_REPO,
		"version": settings.branding.app_version,
		"license": "OS1 License (open-source, permissive attribution)",
		"license_url": "https://github.com/nokodo-labs/os1/blob/dev/LICENSE",
	}


@router.get("/status")
async def get_system_status(db: AsyncSession = Depends(get_db)) -> dict[str, bool]:
	"""Check system initialization status.

	A system is considered initialized once at least one user exists.
	"""
	result = await db.execute(select(func.count()).select_from(User))
	user_count = result.scalar() or 0
	return {"initialized": user_count > 0}


@router.get("/manifest.json", response_class=Response)
async def get_manifest(request: Request) -> Response:
	"""serve a compiled PWA manifest derived from settings."""
	body, etag = pwa_manifest.get_manifest_response(str(request.base_url))
	return Response(
		content=body,
		media_type="application/manifest+json",
		headers={
			"Cache-Control": "public, max-age=3600",
			"ETag": f'"{etag}"',
		},
	)
