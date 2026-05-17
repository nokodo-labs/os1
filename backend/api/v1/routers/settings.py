"""settings router."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.models.user import User
from api.redis import publish_invalidation
from api.service.pwa_manifest import invalidate_cache as invalidate_manifest_cache
from api.settings import Settings, settings
from api.v1.schemas.settings import (
	SettingsResponse,
	SettingsUpdateRequest,
	VapidKeypairResponse,
)
from api.v1.service import settings as svc
from api.v1.service import vectorstores as vectorstores_service
from api.v1.service import web_push as web_push_service
from api.v1.service.auth import Principal, get_current_principal, get_optional_user
from api.v1.service.authorization import require_permission
from api.v1.service.events import SessionId


router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=SettingsResponse, response_model_exclude_unset=True)
async def get_settings(
	user: User | None = Depends(get_optional_user),
	db: AsyncSession = Depends(get_db),
) -> SettingsResponse | JSONResponse:
	"""get all settings."""
	is_admin = bool(user is not None and user.is_active and user.is_superuser)
	versions = await svc.get_versions(db)
	if not is_admin:
		return JSONResponse(
			content=jsonable_encoder(
				{
					"versions": versions,
					"data": settings.custom_dump(exclude_private=True),
				}
			)
		)

	data_model = Settings.model_validate(settings.custom_dump(exclude_private=False))
	return SettingsResponse.model_validate(
		{
			"versions": versions,
			"data": data_model,
		}
	)


@router.patch("", response_model=SettingsResponse)
async def update_settings(
	body: SettingsUpdateRequest,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> SettingsResponse:
	"""partial update settings (admin only)."""
	require_permission(principal, "settings:manage")

	try:
		new_versions = await svc.update(
			db,
			body.data,
			expected_versions=body.expected_versions,
			changed_by_id=principal.user_id,
			origin_session_id=x_session_id,
		)
		await db.commit()
		settings.reload()
		invalidate_manifest_cache()
		await vectorstores_service.reset_runtime_state()

		# notify all workers to clear process-local caches
		await publish_invalidation("embedding_model")
		await publish_invalidation("task_models")
		await publish_invalidation("thread_maintenance_backfill")
	except svc.VersionConflictError as e:
		raise HTTPException(
			status.HTTP_409_CONFLICT,
			f"{e.section}: version conflict ({e.expected} != {e.actual})",
		)
	except ValueError as e:
		raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))

	return SettingsResponse.model_validate(
		{
			"versions": new_versions,
			"data": settings,
		}
	)


@router.post("/vapid-keypair", response_model=VapidKeypairResponse)
async def generate_vapid_keypair(
	principal: Principal = Depends(get_current_principal),
) -> VapidKeypairResponse:
	"""generate a VAPID key pair (admin only)."""
	require_permission(principal, "settings:manage")
	keypair = web_push_service.generate_vapid_keypair()
	return VapidKeypairResponse(
		public_key=keypair.public_key,
		private_key=keypair.private_key,
	)
