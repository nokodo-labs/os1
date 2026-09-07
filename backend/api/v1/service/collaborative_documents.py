"""collaborative document editing service.

orchestrates document room management, access checks, CRDT updates,
and participant notifications. the events router delegates all doc.*
message handling here.
"""

import base64
from dataclasses import dataclass
from typing import TYPE_CHECKING

from api.database import async_session_local
from api.logging import get_logger
from api.permissions import AccessLevel, ResourceType
from api.v1.service.authorization import list_accessible_user_ids_for_resources
from api.v1.service.document_sessions import (
	DocumentParticipant,
	document_session_store,
)
from api.v1.service.events import fanout_live_payload
from nokodo_ai.utils.typeid import TypeID


if TYPE_CHECKING:
	from api.models.user import User

logger = get_logger(__name__)


# document_id format: "resource_type:resource_id" e.g. "note:abc-123"
_DOC_RESOURCE_MAP: dict[str, ResourceType] = {
	"note": ResourceType.NOTE,
	"thread": ResourceType.THREAD,
}


def _parse_document_id(document_id: str) -> tuple[ResourceType, TypeID] | None:
	"""parse a document_id like 'note:{uuid}' into (ResourceType, TypeID)."""
	parts = document_id.split(":", 1)
	if len(parts) != 2:
		return None
	resource_type = _DOC_RESOURCE_MAP.get(parts[0])
	if resource_type is None:
		return None
	return (resource_type, TypeID(parts[1]))


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
	user_id: TypeID,
	ws_session_id: str,
) -> JoinResult | DocError:
	"""validate access, join the room, notify peers, return state.

	joining is deliberately admitted at READER: a reader gets a live read-only
	view with presence and incoming edits. sending edits is a separate,
	higher gate - see ``handle_update``, which requires EDITOR.
	"""
	parsed = _parse_document_id(document_id)
	if not parsed:
		return DocError(error="invalid document_id format")

	resource_type, resource_id = parsed
	async with async_session_local() as db_session:
		accessible = await list_accessible_user_ids_for_resources(
			[(resource_type, resource_id)], db_session
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
	other_ids = list({p.user_id for p in participants if p.session_id != ws_session_id})
	if other_ids:
		await fanout_live_payload(
			{
				"type": "doc.participant_joined",
				"document_id": document_id,
				"user_id": user_id,
				"session_id": ws_session_id,
				"user_name": user_name,
				"avatar_url": user_avatar,
			},
			other_ids,
			None,
			False,
		)

	return JoinResult(
		state_b64=base64.b64encode(state_bytes).decode("ascii"),
		participants=[_serialize_participant(p) for p in participants],
	)


async def handle_leave(
	document_id: str,
	user_id: TypeID,
	ws_session_id: str,
) -> None:
	"""leave a document room and notify remaining participants."""
	remaining = await document_session_store.leave(document_id, ws_session_id)
	other_ids = list({p.user_id for p in remaining})
	if other_ids:
		await fanout_live_payload(
			{
				"type": "doc.participant_left",
				"document_id": document_id,
				"user_id": user_id,
				"session_id": ws_session_id,
			},
			other_ids,
			None,
			False,
		)


async def handle_update(
	document_id: str,
	update_b64: str,
	user_id: TypeID,
	ws_session_id: str,
) -> DocError | None:
	"""apply a Yjs CRDT update and broadcast to all participants.

	two gates, both required. the room is addressable by anyone who knows the
	document_id, so "the room exists" is not authorization:

	1. the sender must be a participant of this room under this ws session.
	2. the sender must hold EDITOR on the resource. joining is admitted at
		READER (a reader gets a live read-only view with presence), so the
		join gate does not carry this one.

	the level is re-checked per frame rather than captured at join time, so a
	revoke takes effect on an already-open room.
	"""
	parsed = _parse_document_id(document_id)
	if not parsed:
		return DocError(error="invalid document_id format")

	participant = await document_session_store.get_participant(
		document_id, ws_session_id
	)
	if participant is None or participant.user_id != user_id:
		return DocError(error="not a participant of this document")

	resource_type, resource_id = parsed
	async with async_session_local() as db_session:
		editors = await list_accessible_user_ids_for_resources(
			[(resource_type, resource_id)],
			db_session,
			required_level=AccessLevel.EDITOR,
		)
	if user_id not in editors:
		return DocError(error="access denied")

	update_bytes = base64.b64decode(update_b64)
	ok = await document_session_store.apply_update(document_id, update_bytes)
	if not ok:
		return None

	participants = await document_session_store.get_participants(document_id)
	peer_ids = list({p.user_id for p in participants})
	if peer_ids:
		await fanout_live_payload(
			{
				"type": "doc.update",
				"document_id": document_id,
				"update": update_b64,
				"sender_session_id": ws_session_id,
			},
			peer_ids,
			None,
			False,
		)
	return None


async def handle_awareness(
	document_id: str,
	awareness_data: dict[str, object],
	user_id: TypeID,
	ws_session_id: str,
) -> DocError | None:
	"""store awareness data and relay to peers.

	the same participant gate ``handle_update`` carries, for the same reason:
	a room is addressable by anyone who knows the document_id. ``update_awareness``
	already no-ops for a non-participant, but WITHOUT this the broadcast still
	went out - so a stranger could inject a cursor carrying their user_id and
	session_id into any open room.

	no EDITOR check: presence is a reader-level capability, which is the whole
	point of admitting join at READER.
	"""
	participant = await document_session_store.get_participant(
		document_id, ws_session_id
	)
	if participant is None or participant.user_id != user_id:
		return DocError(error="not a participant of this document")

	await document_session_store.update_awareness(
		document_id,
		ws_session_id,
		awareness_data,
	)
	participants = await document_session_store.get_participants(document_id)
	peer_ids = list({p.user_id for p in participants if p.session_id != ws_session_id})
	if peer_ids:
		await fanout_live_payload(
			{
				"type": "doc.awareness",
				"document_id": document_id,
				"session_id": ws_session_id,
				"user_id": user_id,
				"data": awareness_data,
			},
			peer_ids,
			None,
			False,
		)
	return None


async def handle_disconnect(
	user_id: TypeID,
	ws_session_id: str,
) -> None:
	"""clean up all document sessions for a disconnected WS and notify peers."""
	left_docs = await document_session_store.leave_all(ws_session_id)
	for doc_id in left_docs:
		remaining = await document_session_store.get_participants(doc_id)
		other_ids = list({p.user_id for p in remaining})
		if other_ids:
			await fanout_live_payload(
				{
					"type": "doc.participant_left",
					"document_id": doc_id,
					"user_id": user_id,
					"session_id": ws_session_id,
				},
				other_ids,
				None,
				False,
			)
