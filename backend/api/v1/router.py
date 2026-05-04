"""API v1 router."""

from fastapi import APIRouter

from api.v1.routers import (
	agents,
	auth,
	calendar,
	events,
	files,
	groups,
	integrations,
	memories,
	models,
	notes,
	notifications,
	openai,
	plugins,
	projects,
	prompts,
	providers,
	reminder_lists,
	roles,
	runs,
	scheduled_items,
	search,
	settings,
	tasks,
	threads,
	users,
	vectorstores,
)


api_router = APIRouter()

api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(threads.router)
api_router.include_router(runs.router)
api_router.include_router(tasks.router)
api_router.include_router(events.router)
api_router.include_router(calendar.router)
api_router.include_router(notifications.router)
api_router.include_router(memories.router)
api_router.include_router(notes.router)
api_router.include_router(groups.router)
api_router.include_router(projects.router)
api_router.include_router(files.router)
api_router.include_router(reminder_lists.router)
api_router.include_router(scheduled_items.router)
api_router.include_router(search.router)
api_router.include_router(providers.router)
api_router.include_router(models.router)
api_router.include_router(agents.router)
api_router.include_router(roles.router)
api_router.include_router(prompts.router)
api_router.include_router(openai.router)
api_router.include_router(plugins.router)
api_router.include_router(settings.router)
api_router.include_router(vectorstores.router)
api_router.include_router(integrations.router)
