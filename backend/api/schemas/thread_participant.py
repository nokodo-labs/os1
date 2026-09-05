"""thread participant + per-user state schemas.

the roster ("who is in a thread") is a read-projection of the ACL plus agent
presence: each entry carries identity and access level only. a user's private
per-thread state (read cursor, mute/pin/archive, pending-invite status) is a
separate model, ``ThreadUserState``, only ever delivered to its owner.
"""

from typing import Annotated, Literal

from pydantic import Field

from api.permissions import AccessLevel
from api.schemas.agent import AgentSummary
from api.schemas.common import ORMModel
from api.schemas.group import GroupSummary
from api.schemas.user import UserSummary
from nokodo_ai.utils.typeid import TypeID


class _ThreadParticipantBase(ORMModel):
	"""fields shared by every roster entry kind - identity + ACL, never state.

	``id`` is the subject's id (user / agent / group id). ``access_level`` and
	``is_owner`` are read from the ACL so clients can show owner/admin/reader
	labels (editor is the unmarked default). this is membership, not state.
	"""

	id: TypeID
	thread_id: TypeID
	access_level: AccessLevel | None = None
	is_owner: bool = False


class UserThreadParticipant(_ThreadParticipantBase):
	"""a human in the thread (resolved from a user AccessRule or the owner)."""

	kind: Literal["user"] = "user"
	user: UserSummary


class AgentThreadParticipant(_ThreadParticipantBase):
	"""an AI agent present in the thread."""

	kind: Literal["agent"] = "agent"
	agent: AgentSummary
	invoke_on_mention: bool | None = None
	"""whether addressing this agent here also asks it to answer; null inherits
	the agent's own setting."""


class GroupThreadParticipant(_ThreadParticipantBase):
	"""a group shared into the thread (its live members inherit access)."""

	kind: Literal["group"] = "group"
	group: GroupSummary


ThreadParticipant = Annotated[
	UserThreadParticipant | AgentThreadParticipant | GroupThreadParticipant,
	Field(discriminator="kind"),
]


class ThreadUserState(ORMModel):
	"""a user's private per-thread state, distinct from the ACL roster.

	this is the caller's own relationship to a thread - read cursor, mute / pin
	/ archive flags, and whether they still have a pending invite. a READER on a
	thread need not have a pending invite, so invite status lives here (state),
	not on the roster (membership). only ever delivered to the user it concerns.
	"""

	thread_id: TypeID
	invite_status: str | None = None
	last_read_message_id: TypeID | None = None
	muted: bool = False
	pinned: bool = False
	archived: bool = False


class ThreadUnreadCount(ORMModel):
	"""unread count for a single thread."""

	thread_id: TypeID
	unread_count: int
