"""API v1 router."""

from fastapi import APIRouter

from api.v1.routers import (
	agents,
	auth,
	events,
	memories,
	models,
	notifications,
	providers,
	tasks,
	threads,
	users,
)


api_router = APIRouter()

api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(threads.router)
api_router.include_router(tasks.router)
api_router.include_router(events.router)
api_router.include_router(notifications.router)
api_router.include_router(memories.router)
api_router.include_router(providers.router)
api_router.include_router(models.router)
api_router.include_router(agents.router)
