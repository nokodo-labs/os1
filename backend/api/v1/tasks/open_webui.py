"""Open WebUI durable task runners."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from api.database import async_session_local
from api.models.task import Task, TaskType
from api.v1.service import tasks as task_service
from api.v1.service.auth import Principal, load_principal_for_user
from api.v1.service.integrations import open_webui as open_webui_service
from nokodo_ai.types.json import JSONObject, JSONValue


OPEN_WEBUI_IMPORT_TASK = "integrations.open_webui.import"


async def spawn_open_webui_import_task(
	session: AsyncSession,
	principal: Principal,
	deployment_origin: str,
	credential: str,
	include_chats: bool,
	include_memories: bool,
) -> Task:
	"""enqueue an Open WebUI import task without storing the credential on the row."""
	deployment = open_webui_service.get_deployment(deployment_origin)
	origin = open_webui_service.normalize_origin(str(deployment.origin))
	return await task_service.start_task(
		session,
		principal=principal,
		task_type=TaskType.IMPORT,
		task_name=OPEN_WEBUI_IMPORT_TASK,
		metadata={
			"integration": "open_webui",
			"deployment_origin": origin,
			"include_chats": include_chats,
			"include_memories": include_memories,
		},
		runtime={"credential": credential},
		stage="starting import",
	)


@task_service.register_task_runner(OPEN_WEBUI_IMPORT_TASK)
async def run_open_webui_import_task(ctx: task_service.TaskContext) -> JSONObject:
	"""import Open WebUI chats/memories for the owning user."""
	credential = ctx.runtime.get("credential")
	if not isinstance(credential, str) or credential.strip() == "":
		raise ValueError("Open WebUI credential is required")
	deployment_origin = ctx.metadata.get("deployment_origin")
	if not isinstance(deployment_origin, str):
		raise ValueError("deployment_origin metadata is required")
	include_chats = ctx.metadata.get("include_chats") is True
	include_memories = ctx.metadata.get("include_memories") is True

	await ctx.update(progress=10, stage="connecting")
	async with async_session_local() as session:
		principal = await load_principal_for_user(ctx.user_id, session)
		summary = await open_webui_service.import_from_open_webui(
			deployment_origin=deployment_origin,
			credential=credential,
			include_chats=include_chats,
			include_memories=include_memories,
			session=session,
			principal=principal,
		)
		await ctx.update(progress=90, stage="finalizing")
		errors: list[JSONValue] = [str(error) for error in summary.errors or []]
		payload: JSONObject = {
			"deployment_origin": summary.deployment_origin,
			"chats_imported": summary.chats_imported,
			"chats_skipped": summary.chats_skipped,
			"messages_imported": summary.messages_imported,
			"memories_imported": summary.memories_imported,
			"memories_skipped": summary.memories_skipped,
			"errors": errors,
		}
		return payload
