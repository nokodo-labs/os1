"""Open WebUI deployment lookup service."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException, status

from api.permissions import ActionPermission
from api.settings import OpenWebUIDeployment, settings
from api.v1.service.auth import Principal


@dataclass(frozen=True, slots=True)
class OpenWebUISources:
	"""available Open WebUI deployments for the current principal."""

	enabled: bool
	deployments: list[OpenWebUIDeployment]


def list_sources(principal: Principal) -> OpenWebUISources:
	"""return configured deployments visible to an authenticated principal."""
	_require_sources_access(principal)
	return OpenWebUISources(
		enabled=settings.integrations.open_webui.enabled,
		deployments=list(settings.integrations.open_webui.deployments),
	)


def get_deployment(deployment_origin: str) -> OpenWebUIDeployment:
	"""return the configured deployment matching an origin."""
	if not settings.integrations.open_webui.enabled:
		raise HTTPException(
			status_code=status.HTTP_403_FORBIDDEN,
			detail="Open WebUI integration is disabled",
		)
	normalized_origin = normalize_origin(deployment_origin).lower()
	for deployment in settings.integrations.open_webui.deployments:
		if normalize_origin(str(deployment.origin)).lower() == normalized_origin:
			return deployment
	raise HTTPException(
		status_code=status.HTTP_404_NOT_FOUND,
		detail="unknown Open WebUI deployment",
	)


def normalize_origin(origin: str) -> str:
	"""normalize deployment origins for comparison and metadata."""
	return origin.rstrip("/")


def _require_sources_access(principal: Principal) -> None:
	if principal.has_permission(ActionPermission.THREADS_CREATE.value):
		return
	if principal.has_permission(ActionPermission.MEMORIES_CREATE.value):
		return
	if principal.has_permission(ActionPermission.NOTES_CREATE.value):
		return
	raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
