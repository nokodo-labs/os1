"""API v1 router."""

from fastapi import APIRouter

from api.v1.endpoints import users


api_router = APIRouter()

api_router.include_router(users.router, prefix="/users", tags=["users"])
