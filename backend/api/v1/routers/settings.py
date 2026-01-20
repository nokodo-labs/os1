"""settings router."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.database import get_db
from api.models.user import User
from api.settings import Settings, settings
from api.v1.schemas.settings import (
	SettingsResponse,
	SettingsUpdateRequest,
)
from api.v1.service import settings as svc
from api.v1.service.auth import Principal, get_current_principal, get_optional_user
from api.v1.service.authorization import require_permission


router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=SettingsResponse, response_model_exclude_unset=True)
async def get_settings(
	user: User | None = Depends(get_optional_user),
	db: AsyncSession = Depends(get_db),
) -> SettingsResponse:
	"""get all settings."""
	is_admin = bool(user is not None and user.is_active and user.is_superuser)
	versions = await svc.get_versions(db)
	data = settings.custom_dump(exclude_private=not is_admin)
	data_model = Settings.model_validate(data)
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
) -> SettingsResponse:
	"""partial update settings (admin only)."""
	require_permission(principal, "settings:manage")

	try:
		new_versions = await svc.update(
			db,
			body.data,
			expected_versions=body.expected_versions,
			changed_by_id=principal.user_id,
		)
		await db.commit()
		settings.reload()
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
