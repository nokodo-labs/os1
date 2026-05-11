"""Open WebUI durable task runners."""

from __future__ import annotations

from typing import Literal

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
	include_notes: bool = False,
	include_archived_chats: bool = False,
	chat_import_mode: Literal["batched", "bulk"] = "batched",
	started_by_user_id: str | None = None,
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
			"include_notes": include_notes,
			"include_archived_chats": include_archived_chats,
			"chat_import_mode": chat_import_mode,
			"started_by_user_id": started_by_user_id or principal.user_id,
		},
		runtime={"credential": credential},
		stage="starting import",
	)


@task_service.register_task_runner(OPEN_WEBUI_IMPORT_TASK)
async def run_open_webui_import_task(ctx: task_service.TaskContext) -> JSONObject:
	"""import Open WebUI data for the owning user."""
	credential = ctx.runtime.get("credential")
	if not isinstance(credential, str) or credential.strip() == "":
		raise ValueError("Open WebUI credential is required")
	deployment_origin = ctx.metadata.get("deployment_origin")
	if not isinstance(deployment_origin, str):
		raise ValueError("deployment_origin metadata is required")
	include_chats = ctx.metadata.get("include_chats") is True
	include_memories = ctx.metadata.get("include_memories") is True
	include_notes = ctx.metadata.get("include_notes") is True
	include_archived_chats = ctx.metadata.get("include_archived_chats") is True
	chat_import_mode: Literal["batched", "bulk"] = "batched"
	metadata_chat_import_mode = ctx.metadata.get("chat_import_mode")
	if metadata_chat_import_mode == "bulk":
		chat_import_mode = "bulk"

	await ctx.update(progress=10, stage="connecting")

	async def update_progress(progress: int, stage: str) -> None:
		await ctx.update(progress=progress, stage=stage)

	async with async_session_local() as session:
		principal = await load_principal_for_user(ctx.user_id, session)
		summary = await open_webui_service.import_from_open_webui(
			deployment_origin=deployment_origin,
			credential=credential,
			include_chats=include_chats,
			include_memories=include_memories,
			include_notes=include_notes,
			session=session,
			principal=principal,
			include_archived_chats=include_archived_chats,
			chat_import_mode=chat_import_mode,
			progress_callback=update_progress,
		)
		errors: list[JSONValue] = [str(error) for error in summary.errors or []]
		payload: JSONObject = {
			"deployment_origin": summary.deployment_origin,
			"chats_imported": summary.chats_imported,
			"chats_skipped": summary.chats_skipped,
			"messages_imported": summary.messages_imported,
			"projects_imported": summary.projects_imported,
			"projects_skipped": summary.projects_skipped,
			"files_imported": summary.files_imported,
			"files_skipped": summary.files_skipped,
			"memories_imported": summary.memories_imported,
			"memories_skipped": summary.memories_skipped,
			"notes_imported": summary.notes_imported,
			"notes_skipped": summary.notes_skipped,
			"errors": errors,
		}
		return payload
