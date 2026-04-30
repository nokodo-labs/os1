"""Open WebUI integration endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.schemas.task import Task as TaskSchema
from api.v1.service.auth import Principal, get_current_principal
from api.v1.service.integrations import open_webui as open_webui_service
from api.v1.tasks.open_webui import spawn_open_webui_import_task


router = APIRouter(prefix="/open-webui", tags=["integrations: Open WebUI"])


class OpenWebUIDeploymentOut(BaseModel):
	"""public-facing deployment listing entry."""

	name: str
	description: str
	origin: HttpUrl


class OpenWebUISourcesOut(BaseModel):
	"""list of available Open WebUI deployments users can import from."""

	enabled: bool
	deployments: list[OpenWebUIDeploymentOut]


class OpenWebUIImportRequest(BaseModel):
	"""payload to trigger an Open WebUI import for the current user."""

	deployment_origin: HttpUrl
	jwt: str = Field(min_length=1, description="user's Open WebUI JWT or API key")
	include_chats: bool = True
	include_memories: bool = True


class OpenWebUIImportSummaryOut(BaseModel):
	"""serializable Open WebUI import summary."""

	deployment_origin: str
	chats_imported: int
	chats_skipped: int
	messages_imported: int
	memories_imported: int
	memories_skipped: int
	errors: list[str] = []

	@classmethod
	def from_summary(
		cls, summary: open_webui_service.ImportSummary
	) -> OpenWebUIImportSummaryOut:
		return cls(
			deployment_origin=summary.deployment_origin,
			chats_imported=summary.chats_imported,
			chats_skipped=summary.chats_skipped,
			messages_imported=summary.messages_imported,
			memories_imported=summary.memories_imported,
			memories_skipped=summary.memories_skipped,
			errors=summary.errors or [],
		)


@router.get(
	"/sources",
	response_model=OpenWebUISourcesOut,
	summary="List Open WebUI sources",
)
async def list_open_webui_sources(
	principal: Principal = Depends(get_current_principal),
) -> OpenWebUISourcesOut:
	"""return admin-allowlisted Open WebUI deployments users can import from."""
	sources = open_webui_service.list_sources(principal)
	return OpenWebUISourcesOut(
		enabled=sources.enabled,
		deployments=[
			OpenWebUIDeploymentOut(
				name=deployment.name,
				description=deployment.description,
				origin=deployment.origin,
			)
			for deployment in sources.deployments
		],
	)


@router.post(
	"/import/task",
	response_model=TaskSchema,
	status_code=202,
	summary="Start Open WebUI import task",
)
async def start_open_webui_import_task(
	body: OpenWebUIImportRequest,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> TaskSchema:
	"""enqueue an Open WebUI import as a durable Task."""
	task = await spawn_open_webui_import_task(
		db,
		principal=principal,
		deployment_origin=str(body.deployment_origin),
		credential=body.jwt,
		include_chats=body.include_chats,
		include_memories=body.include_memories,
	)
	return TaskSchema.model_validate(task)


@router.post(
	"/import",
	response_model=OpenWebUIImportSummaryOut,
	summary="Import from Open WebUI",
)
async def import_open_webui(
	body: OpenWebUIImportRequest,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> OpenWebUIImportSummaryOut:
	"""import chats and/or memories from an Open WebUI deployment for the user."""
	summary = await open_webui_service.import_from_open_webui(
		deployment_origin=str(body.deployment_origin),
		credential=body.jwt,
		include_chats=body.include_chats,
		include_memories=body.include_memories,
		session=db,
		principal=principal,
	)
	return OpenWebUIImportSummaryOut.from_summary(summary)
