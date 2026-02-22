"""collaborative document editing service.

orchestrates document room management, access checks, CRDT updates,
and participant notifications. the events router delegates all doc.*
message handling here.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import TYPE_CHECKING

from api.core.database import AsyncSessionLocal
from api.core.logging import get_logger
from api.permissions import ResourceType
from api.v1.service import events as event_service
from api.v1.service.authorization import list_accessible_user_ids
from api.v1.service.document_sessions import (
	DocumentParticipant,
	document_session_store,
)


if TYPE_CHECKING:
	from api.models.user import User

logger = get_logger(__name__)


# document_id format: "resource_type:resource_id" e.g. "note:abc-123"
_DOC_RESOURCE_MAP: dict[str, ResourceType] = {
	"note": ResourceType.NOTE,
	"thread": ResourceType.THREAD,
}


def _parse_document_id(document_id: str) -> tuple[ResourceType, str] | None:
	"""parse a document_id like 'note:{uuid}' into (ResourceType, uuid)."""
	parts = document_id.split(":", 1)
	if len(parts) != 2:
		return None
	resource_type = _DOC_RESOURCE_MAP.get(parts[0])
	if resource_type is None:
		return None
	return (resource_type, parts[1])


def _serialize_participant(p: DocumentParticipant) -> dict[str, str | None]:
	return {
		"user_id": p.user_id,
		"session_id": p.session_id,
		"user_name": p.user_name,
		"avatar_url": p.avatar_url,
		"color": p.color,
	}


@dataclass
class JoinResult:
	"""returned by handle_join on success."""

	state_b64: str
	participants: list[dict[str, str | None]]


@dataclass
class DocError:
	"""returned when a doc operation should send an error to the caller."""

	error: str


async def handle_join(
	document_id: str,
	user: User,
	user_id: str,
	ws_session_id: str,
) -> JoinResult | DocError:
	"""validate access, join the room, notify peers, return state."""
	parsed = _parse_document_id(document_id)
	if not parsed:
		return DocError(error="invalid document_id format")

	resource_type, resource_id = parsed
	async with AsyncSessionLocal() as db_session:
		accessible = await list_accessible_user_ids(
			resource_type,
			resource_id,
			db_session,
		)
	if user_id not in accessible:
		return DocError(error="access denied")

	user_name = user.display_name or user.email.split("@")[0]
	user_avatar = user.avatar_url
	state_bytes = await document_session_store.join(
		document_id,
		user_id,
		ws_session_id,
		user_name=user_name,
		avatar_url=user_avatar,
	)
	participants = await document_session_store.get_participants(document_id)

	# notify other participants
	other_ids = list(
		{p.user_id for p in participants if p.session_id != ws_session_id}
	)
	if other_ids:
		await event_service.event_connections.send_to_users(
			other_ids,
			{
				"type": "doc.participant_joined",
				"document_id": document_id,
				"user_id": user_id,
				"session_id": ws_session_id,
				"user_name": user_name,
				"avatar_url": user_avatar,
			},
		)

	return JoinResult(
		state_b64=base64.b64encode(state_bytes).decode("ascii"),
		participants=[_serialize_participant(p) for p in participants],
	)


async def handle_leave(
	document_id: str,
	user_id: str,
	ws_session_id: str,
) -> None:
	"""leave a document room and notify remaining participants."""
	remaining = await document_session_store.leave(document_id, ws_session_id)
	other_ids = list({p.user_id for p in remaining})
	if other_ids:
		await event_service.event_connections.send_to_users(
			other_ids,
			{
				"type": "doc.participant_left",
				"document_id": document_id,
				"user_id": user_id,
				"session_id": ws_session_id,
			},
		)


async def handle_update(
	document_id: str,
	update_b64: str,
	ws_session_id: str,
) -> None:
	"""apply a Yjs CRDT update and broadcast to all participants."""
	update_bytes = base64.b64decode(update_b64)
	ok = await document_session_store.apply_update(document_id, update_bytes)
	if not ok:
		return

	participants = await document_session_store.get_participants(document_id)
	peer_ids = list({p.user_id for p in participants})
	if peer_ids:
		await event_service.event_connections.send_to_users(
			peer_ids,
			{
				"type": "doc.update",
				"document_id": document_id,
				"update": update_b64,
				"sender_session_id": ws_session_id,
			},
		)


async def handle_awareness(
	document_id: str,
	awareness_data: dict[str, object],
	user_id: str,
	ws_session_id: str,
) -> None:
	"""store awareness data and relay to peers."""
	await document_session_store.update_awareness(
		document_id,
		ws_session_id,
		awareness_data,
	)
	participants = await document_session_store.get_participants(document_id)
	peer_ids = list(
		{p.user_id for p in participants if p.session_id != ws_session_id}
	)
	if peer_ids:
		await event_service.event_connections.send_to_users(
			peer_ids,
			{
				"type": "doc.awareness",
				"document_id": document_id,
				"session_id": ws_session_id,
				"user_id": user_id,
				"data": awareness_data,
			},
		)


async def handle_disconnect(
	user_id: str,
	ws_session_id: str,
) -> None:
	"""clean up all document sessions for a disconnected WS and notify peers."""
	left_docs = await document_session_store.leave_all(ws_session_id)
	for doc_id in left_docs:
		remaining = await document_session_store.get_participants(doc_id)
		other_ids = list({p.user_id for p in remaining})
		if other_ids:
			await event_service.event_connections.send_to_users(
				other_ids,
				{
					"type": "doc.participant_left",
					"document_id": doc_id,
					"user_id": user_id,
					"session_id": ws_session_id,
				},
			)
