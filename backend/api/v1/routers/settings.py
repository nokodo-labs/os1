"""settings router."""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.permissions import ActionPermission
from api.settings import Settings, settings
from api.v1.schemas.settings import (
	SettingsResponse,
	SettingsUpdateRequest,
	VapidKeypairResponse,
)
from api.v1.service.authentication import (
	Principal,
	get_current_principal,
	get_optional_principal,
)
from api.v1.service.authorization import require_permission
from api.v1.service.events import SessionId
from api.v1.service.settings import (
	VersionConflictError,
	get_versions,
	update,
)
from api.v1.service.web_push import (
	generate_vapid_keypair as generate_vapid_keypair_service,
)


router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=SettingsResponse, response_model_exclude_unset=True)
async def get_settings(
	principal: Principal | None = Depends(get_optional_principal),
	db: AsyncSession = Depends(get_db),
) -> SettingsResponse | JSONResponse:
	"""get all settings."""
	can_read_private = principal is not None and principal.has_permission(
		ActionPermission.SETTINGS_MANAGE
	)
	versions = await get_versions(db)
	if not can_read_private:
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
	require_permission(principal, ActionPermission.SETTINGS_MANAGE)

	try:
		new_versions = await update(
			db,
			body.data,
			expected_versions=body.expected_versions,
			changed_by_id=principal.user.id,
			origin_session_id=x_session_id,
		)
	except VersionConflictError as e:
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
	require_permission(principal, ActionPermission.SETTINGS_MANAGE)
	keypair = generate_vapid_keypair_service()
	return VapidKeypairResponse(
		public_key=keypair.public_key,
		private_key=keypair.private_key,
	)
