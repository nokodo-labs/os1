"""main fastapi application entry point."""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from api.boot_settings import boot_settings
from api.constants import API_V1_MOUNT_PATH
from api.database import init_db, session_scope
from api.exceptions import (
	http_exception_handler,
	unhandled_exception_handler,
	validation_exception_handler,
)
from api.logging import configure_logging, get_logger
from api.middleware import (
	APIVersionHeaderMiddleware,
	RateLimitMiddleware,
	RequestIDMiddleware,
	RequestLoggingMiddleware,
	SecurityHeadersMiddleware,
)
from api.openapi import DEFAULT_RESPONSES
from api.redis import redis_client, start_invalidation_subscriber
from api.routers import system as system_router
from api.settings import settings
from api.storage import close_all as close_storage
from api.storage import configure_storage_backends
from api.taskiq import shutdown_taskiq, startup_taskiq
from api.v1.router import api_router
from api.v1.service.events import start_remote_fanout_relay
from api.v1.service.integrations.mcp import (
	initialize_global_mcp_servers,
	start_mcp_list_change_listeners,
	stop_mcp_list_change_listeners,
)
from api.v1.tasks.calendar import reconcile_calendar_event_notification_schedules
from api.v1.tasks.files import (
	clear_disabled_file_maintenance_backfill_schedule,
	fail_stale_file_tasks,
	reconcile_file_maintenance_backfill_schedule,
)
from api.v1.tasks.reminders import reconcile_reminder_notification_schedules
from api.v1.tasks.threads import (
	clear_disabled_thread_maintenance_backfill_schedule,
	fail_stale_thread_related_tasks,
	reconcile_thread_maintenance_backfill_schedule,
)


# configure logging early, before anything else logs
configure_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
	"""application lifespan events."""
	logger.info(
		"starting %s v%s [%s]",
		settings.branding.site_name,
		settings.branding.app_version,
		boot_settings.ENV,
	)

	settings.validate_runtime_security()

	if not boot_settings.TESTING:
		await init_db()
		async with session_scope() as session:
			await initialize_global_mcp_servers(session)
		await redis_client.connect()
		await clear_disabled_thread_maintenance_backfill_schedule()
		await clear_disabled_file_maintenance_backfill_schedule()
		await startup_taskiq()
		await fail_stale_thread_related_tasks()
		await fail_stale_file_tasks()
		await reconcile_calendar_event_notification_schedules()
		await reconcile_reminder_notification_schedules()
		await reconcile_thread_maintenance_backfill_schedule()
		await reconcile_file_maintenance_backfill_schedule()

	# start the cross-worker cache invalidation subscriber. handlers are
	# self-registered at import time by the modules that own resettable
	# state (imported transitively through the router tree).
	invalidation_task: asyncio.Task[None] | None = None
	event_task: asyncio.Task[None] | None = None
	mcp_list_change_tasks: list[asyncio.Task[None]] = []
	if not boot_settings.TESTING:
		mcp_list_change_tasks = await start_mcp_list_change_listeners()
		invalidation_task = await start_invalidation_subscriber()
		event_task = await start_remote_fanout_relay()

	await configure_storage_backends()

	logger.info("startup complete")
	yield

	# shutdown
	logger.info("shutting down")
	if invalidation_task is not None:
		invalidation_task.cancel()
	if event_task is not None:
		event_task.cancel()
	await stop_mcp_list_change_listeners(mcp_list_change_tasks)
	await close_storage()
	if not boot_settings.TESTING:
		await shutdown_taskiq()
		await redis_client.aclose()


app = FastAPI(
	title=settings.branding.site_name,
	version=settings.branding.app_version,
	lifespan=lifespan,
	docs_url="/v1/docs",
	redoc_url="/v1/redoc",
	openapi_url="/v1/openapi.json",
)

# middleware stack (executed in reverse order of addition)
# 5. request id (outermost - runs first)
app.add_middleware(RequestIDMiddleware)

# 4. security headers
app.add_middleware(SecurityHeadersMiddleware)

# 3. request logging
app.add_middleware(RequestLoggingMiddleware)

# 2. api version header
app.add_middleware(APIVersionHeaderMiddleware, version="v1")

# 1. cors
app.add_middleware(
	CORSMiddleware,
	allow_origins=settings.security.cors_origins,
	allow_origin_regex="|".join(
		f"({pattern})" for pattern in settings.security.cors_origins_regex
	),
	allow_credentials=True,
	allow_methods=["*"],
	allow_headers=["*"],
)

# 0. rate limiting (closest to app - after cors handles preflight)
app.add_middleware(RateLimitMiddleware)

# exception handlers
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)


@app.get("/", tags=["root"])
async def root() -> dict[str, str]:
	"""API root with information and links."""
	return {
		"name": settings.branding.site_name,
		"version": settings.branding.app_version,
		"api_version": "v1",
		"docs": "/v1/docs",
		"openapi": "/v1/openapi.json",
		"health": "/health",
	}


@app.get("/health")
async def health_check() -> dict[str, str]:
	"""Health check endpoint."""
	return {"status": "healthy"}


# non-versioned routes
app.include_router(system_router.router)

# v1 api routes
app.include_router(api_router, prefix=API_V1_MOUNT_PATH, responses=DEFAULT_RESPONSES)
