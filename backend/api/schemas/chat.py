"""Chat (branching thread) schemas.

In nokodo AI backend, a "chat" is currently represented by a Thread.
These DTOs exist to expose branching-chat endpoints under /chats.
"""

from __future__ import annotations

from pydantic import BaseModel

from api.typeid import TypeID


class ChatSwitchRequest(BaseModel):
	message_id: TypeID


class ChatSwitchResponse(BaseModel):
	ok: bool
	current_message_id: TypeID | None = None
