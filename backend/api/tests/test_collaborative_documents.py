"""the three gates on a collaborative editing room.

a room is in-memory and addressable by anyone who knows its ``document_id``,
which is ``"note:<typeid>"`` / ``"thread:<typeid>"`` - an id learned from a
thread, a link share, or a former collaboration is enough. so "the room
exists" is never authorization, and each frame type carries its own gate:

- ``doc.join``   -> READER on the resource. a reader gets a live read-only
                    view with presence and incoming edits.
- ``doc.update`` -> participant of THIS room under THIS ws session, AND
                    EDITOR on the resource, re-checked per frame so a revoke
                    lands on an already-open room.
- ``doc.awareness`` -> participant only. presence is reader-level, which is
                    the whole point of admitting join at READER.

the service functions are driven directly: the router only threads
``user_id`` through, and the interesting behaviour is entirely in the gates.
the accessible-users answer and the fanout are faked so a test can state
exactly who holds what, and assert on what was broadcast.
"""

from __future__ import annotations

import base64
from typing import Any
from uuid import uuid4

import pytest
from pycrdt import Doc, Text

from api.models.user import User
from api.permissions import AccessLevel, ResourceType
from api.v1.service import collaborative_documents as docs
from api.v1.service.document_sessions import DocumentSessionStore
from nokodo_ai.utils.typeid import TypeID, new_typeid


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch) -> DocumentSessionStore:
	"""a fresh room store per test, so rooms never leak between them."""
	fresh = DocumentSessionStore()
	monkeypatch.setattr(docs, "document_session_store", fresh)
	return fresh


@pytest.fixture
def broadcasts(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
	"""capture every payload the service fans out."""
	sent: list[dict[str, Any]] = []

	async def _capture(
		stream_payload: dict[str, Any],
		recipient_ids: list[TypeID] | None,
		user_id: TypeID | str | None,
		broadcast: bool,
		exclude_user_id: TypeID | str | None = None,
	) -> None:
		_ = user_id, broadcast, exclude_user_id
		sent.append({**stream_payload, "_recipients": list(recipient_ids or [])})

	monkeypatch.setattr(docs, "fanout_live_payload", _capture)
	return sent


def _grant(
	monkeypatch: pytest.MonkeyPatch,
	levels: dict[TypeID, AccessLevel],
) -> None:
	"""fake the accessible-users answer from a per-user level map.

	the service asks "who holds at least this level"; a level map is the
	honest shape of that question and keeps the READER/EDITOR distinction -
	the one this surface turns on - visible in each test's setup.
	"""
	rank = {AccessLevel.READER: 0, AccessLevel.EDITOR: 1, AccessLevel.ADMIN: 2}

	async def _accessible(
		resource_refs: list[tuple[ResourceType, TypeID]],
		session: object,
		required_level: AccessLevel = AccessLevel.READER,
	) -> list[TypeID]:
		_ = resource_refs, session
		return [
			user_id
			for user_id, level in levels.items()
			if rank[level] >= rank[required_level]
		]

	monkeypatch.setattr(docs, "list_accessible_user_ids_for_resources", _accessible)

	class _NullSession:
		async def __aenter__(self) -> _NullSession:
			return self

		async def __aexit__(self, *_exc: object) -> None:
			return None

	# the faked resolver never touches the session, so the gates can run
	# without a database.
	monkeypatch.setattr(docs, "async_session_local", _NullSession)


def _user(slug: str) -> User:
	"""an unpersisted user row - `handle_join` reads only name and avatar."""
	return User(
		id=TypeID(new_typeid("user")),
		email=f"{slug}-{uuid4().hex[:8]}@example.com",
		username=slug,
		hashed_password="x",
		is_active=True,
		display_name=slug,
	)


def _update_bytes(text: str) -> bytes:
	"""a real Yjs update, so `apply_update` succeeds or fails for real."""
	doc = Doc()
	doc["body"] = Text(text)
	return doc.get_update()


def _update_b64(text: str) -> str:
	return base64.b64encode(_update_bytes(text)).decode("ascii")


def _document_id() -> str:
	return f"note:{new_typeid('note')}"


@pytest.mark.asyncio
async def test_a_reader_may_join_and_receives_later_updates(
	store: DocumentSessionStore,
	broadcasts: list[dict[str, Any]],
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""the decided shape: join is READER, so a reader gets the live view.

	the reader is also in the update fanout - a read-only view that did not
	receive incoming edits would not be a live view at all.
	"""
	editor, reader = _user("edt"), _user("rdr")
	_grant(
		monkeypatch,
		{editor.id: AccessLevel.EDITOR, reader.id: AccessLevel.READER},
	)
	document_id = _document_id()

	editor_join = await docs.handle_join(document_id, editor, editor.id, "ws-edt")
	assert isinstance(editor_join, docs.JoinResult)
	reader_join = await docs.handle_join(document_id, reader, reader.id, "ws-rdr")
	assert isinstance(reader_join, docs.JoinResult)
	assert {p["user_id"] for p in reader_join.participants} == {editor.id, reader.id}

	broadcasts.clear()
	assert (
		await docs.handle_update(document_id, _update_b64("hi"), editor.id, "ws-edt")
		is None
	)

	update_frames = [frame for frame in broadcasts if frame["type"] == "doc.update"]
	assert len(update_frames) == 1
	assert reader.id in update_frames[0]["_recipients"]


@pytest.mark.asyncio
async def test_a_reader_participant_cannot_send_an_update(
	store: DocumentSessionStore,
	broadcasts: list[dict[str, Any]],
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""being IN the room is not permission to write in it.

	this is the half the join gate cannot carry: joining is admitted at
	READER on purpose, so the level has to be checked again on the frame.
	"""
	editor, reader = _user("edt"), _user("rdr")
	_grant(
		monkeypatch,
		{editor.id: AccessLevel.EDITOR, reader.id: AccessLevel.READER},
	)
	document_id = _document_id()
	await docs.handle_join(document_id, editor, editor.id, "ws-edt")
	await docs.handle_join(document_id, reader, reader.id, "ws-rdr")

	broadcasts.clear()
	result = await docs.handle_update(
		document_id, _update_b64("sneaky"), reader.id, "ws-rdr"
	)

	assert isinstance(result, docs.DocError)
	assert result.error == "access denied"
	assert broadcasts == []
	assert _room_text(store, document_id) == ""


@pytest.mark.asyncio
async def test_a_non_participant_cannot_send_an_update(
	store: DocumentSessionStore,
	broadcasts: list[dict[str, Any]],
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""the injection this gate exists for.

	the attacker here holds EDITOR, so ONLY the participant check can reject
	them - which is exactly the case a level check alone would let through.
	nothing is applied to the shared doc and nothing is broadcast.
	"""
	editor, stranger = _user("edt"), _user("str")
	_grant(
		monkeypatch,
		{editor.id: AccessLevel.EDITOR, stranger.id: AccessLevel.EDITOR},
	)
	document_id = _document_id()
	await docs.handle_join(document_id, editor, editor.id, "ws-edt")

	broadcasts.clear()
	result = await docs.handle_update(
		document_id, _update_b64("injected"), stranger.id, "ws-str"
	)

	assert isinstance(result, docs.DocError)
	assert result.error == "not a participant of this document"
	assert broadcasts == []
	assert _room_text(store, document_id) == ""


@pytest.mark.asyncio
async def test_an_editor_participants_update_is_applied_and_broadcast(
	store: DocumentSessionStore,
	broadcasts: list[dict[str, Any]],
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""the allowed path still works - the gates are not a blanket refusal."""
	editor = _user("edt")
	_grant(monkeypatch, {editor.id: AccessLevel.EDITOR})
	document_id = _document_id()
	await docs.handle_join(document_id, editor, editor.id, "ws-edt")

	broadcasts.clear()
	update_b64 = _update_b64("applied")
	assert (
		await docs.handle_update(document_id, update_b64, editor.id, "ws-edt") is None
	)

	assert _room_text(store, document_id) == "applied"
	assert broadcasts == [
		{
			"type": "doc.update",
			"document_id": document_id,
			"update": update_b64,
			"sender_session_id": "ws-edt",
			"_recipients": [editor.id],
		}
	]


@pytest.mark.asyncio
async def test_a_session_cannot_send_an_update_as_another_user(
	store: DocumentSessionStore,
	broadcasts: list[dict[str, Any]],
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""the ws session and the user id must belong to each other.

	the session is a real participant and the claimed user really holds
	EDITOR, so neither half of the gate rejects this alone - only binding
	them together does.
	"""
	reader, editor = _user("rdr"), _user("edt")
	_grant(
		monkeypatch,
		{reader.id: AccessLevel.READER, editor.id: AccessLevel.EDITOR},
	)
	document_id = _document_id()
	await docs.handle_join(document_id, reader, reader.id, "ws-rdr")

	broadcasts.clear()
	result = await docs.handle_update(
		document_id, _update_b64("borrowed"), editor.id, "ws-rdr"
	)

	assert isinstance(result, docs.DocError)
	assert result.error == "not a participant of this document"
	assert broadcasts == []


@pytest.mark.asyncio
async def test_losing_editor_stops_updates_on_an_already_open_room(
	store: DocumentSessionStore,
	broadcasts: list[dict[str, Any]],
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""the level is re-read per frame, not captured at join.

	a gate evaluated once at join would leave a revoked editor writing for as
	long as they kept the socket open.
	"""
	editor = _user("edt")
	_grant(monkeypatch, {editor.id: AccessLevel.EDITOR})
	document_id = _document_id()
	await docs.handle_join(document_id, editor, editor.id, "ws-edt")
	assert (
		await docs.handle_update(
			document_id, _update_b64("before"), editor.id, "ws-edt"
		)
		is None
	)

	# demoted to reader while the room stays open
	_grant(monkeypatch, {editor.id: AccessLevel.READER})
	broadcasts.clear()
	result = await docs.handle_update(
		document_id, _update_b64("after"), editor.id, "ws-edt"
	)

	assert isinstance(result, docs.DocError)
	assert result.error == "access denied"
	assert broadcasts == []
	assert _room_text(store, document_id) == "before"


@pytest.mark.asyncio
async def test_a_malformed_document_id_is_rejected_before_any_lookup(
	store: DocumentSessionStore,
	broadcasts: list[dict[str, Any]],
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""an unparseable id is a client error, not a room."""
	editor = _user("edt")
	_grant(monkeypatch, {editor.id: AccessLevel.EDITOR})

	for bad_id in ("no-separator", "wombat:abc"):
		result = await docs.handle_update(bad_id, _update_b64("x"), editor.id, "ws-edt")
		assert isinstance(result, docs.DocError)
		assert result.error == "invalid document_id format"
	assert broadcasts == []


@pytest.mark.asyncio
async def test_a_non_participants_awareness_is_neither_stored_nor_broadcast(
	store: DocumentSessionStore,
	broadcasts: list[dict[str, Any]],
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""presence frames carry the sender's identity, so they need the gate too.

	``update_awareness`` already no-ops for a non-participant, but the
	broadcast used to go out regardless - letting a stranger inject a cursor
	labelled with their user_id into any room whose id they knew.
	"""
	editor, stranger = _user("edt"), _user("str")
	_grant(
		monkeypatch,
		{editor.id: AccessLevel.EDITOR, stranger.id: AccessLevel.EDITOR},
	)
	document_id = _document_id()
	await docs.handle_join(document_id, editor, editor.id, "ws-edt")

	broadcasts.clear()
	result = await docs.handle_awareness(
		document_id, {"cursor": 3}, stranger.id, "ws-str"
	)

	assert isinstance(result, docs.DocError)
	assert result.error == "not a participant of this document"
	assert broadcasts == []
	assert await store.get_all_awareness(document_id) == [
		{"user_id": editor.id, "session_id": "ws-edt"}
	]


@pytest.mark.asyncio
async def test_a_reader_participants_awareness_is_stored_and_broadcast(
	store: DocumentSessionStore,
	broadcasts: list[dict[str, Any]],
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""presence is reader-level: the awareness gate is participation only."""
	editor, reader = _user("edt"), _user("rdr")
	_grant(
		monkeypatch,
		{editor.id: AccessLevel.EDITOR, reader.id: AccessLevel.READER},
	)
	document_id = _document_id()
	await docs.handle_join(document_id, editor, editor.id, "ws-edt")
	await docs.handle_join(document_id, reader, reader.id, "ws-rdr")

	broadcasts.clear()
	assert (
		await docs.handle_awareness(document_id, {"cursor": 7}, reader.id, "ws-rdr")
		is None
	)

	assert broadcasts == [
		{
			"type": "doc.awareness",
			"document_id": document_id,
			"session_id": "ws-rdr",
			"user_id": reader.id,
			"data": {"cursor": 7},
			"_recipients": [editor.id],
		}
	]
	assert {"user_id": reader.id, "session_id": "ws-rdr", "cursor": 7} in (
		await store.get_all_awareness(document_id)
	)


def _room_text(store: DocumentSessionStore, document_id: str) -> str:
	"""read the room's CRDT text, or "" when nothing was ever applied.

	asserting on the shared document itself - not just on the return value -
	is what proves a rejected frame changed nothing.
	"""
	room = store._rooms.get(document_id)
	if room is None:
		return ""
	body = room.doc.get("body", type=Text)
	return str(body)
