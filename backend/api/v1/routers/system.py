"""System routers."""

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.database import get_db
from api.models.user import User
from api.settings import settings
from api.v1.schemas.system import RuntimeConfigOut


router = APIRouter(prefix="/system", tags=["system"])


@router.get("/status")
async def get_system_status(db: AsyncSession = Depends(get_db)) -> dict[str, bool]:
	"""Check system initialization status."""
	result = await db.execute(select(func.count()).select_from(User))
	user_count = result.scalar() or 0
	return {"initialized": user_count > 0}


@router.get("/config")
async def get_runtime_config() -> RuntimeConfigOut:
	"""Return runtime configuration values safe for clients."""
	return RuntimeConfigOut(
		frontend_origin=settings.branding.public_frontend_origin,
		cdn_origin=settings.branding.public_cdn_origin,
	)
