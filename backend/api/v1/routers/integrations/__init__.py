"""integration routes."""

from fastapi import APIRouter

from api.v1.routers.integrations import open_webui


router = APIRouter(prefix="/integrations", tags=["integrations"])

router.include_router(open_webui.router)
