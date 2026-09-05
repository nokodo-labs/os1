"""thread schemas."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from api.models.message import Message
from api.models.thread import Thread as ThreadModel
from api.models.thread_summary import SummaryPurpose
from api.schemas.access_rule import ResourceAccessListFilters
from api.schemas.common import (
	MISSING,
	ForbidExtraModel,
	MetadataModel,
	MetadataUpdateModel,
	MissingType,
	ORMModel,
	PrivateFacetModel,
	PrivateInputFacetModel,
	PrivateInputModel,
	PrivateModel,
	TimestampedModel,
)
from api.schemas.message import Message as MessageSchema
from api.schemas.project import Project as ProjectSchema
from api.schemas.sorting import CommonSortBy
from api.schemas.thread_participant import ThreadParticipant as ThreadParticipantSchema
from nokodo_ai.utils.typeid import TypeID


type ThreadSortBy = (
	CommonSortBy
	| Literal[
		"last_activity_at",
		"title",
	]
)


type ParticipantScope = Literal["solo", "people", "all"]

# per-user thread state flags a listing can be filtered by.
type ParticipantStatus = Literal["archived", "pinned", "muted", "invite_pending"]


class ThreadListFilters(ResourceAccessListFilters):
	"""filters for listing threads."""

	owner_id: TypeID | None = None
	project_id: TypeID | None = None
	include_hidden: bool = False
	include_deleted: bool = False
	q: str | None = Field(default=None, min_length=1, max_length=500)
	participant_scope: ParticipantScope = "all"
	archived_by: TypeID | None = None
	not_archived_by: TypeID | None = None
	pinned_by: TypeID | None = None
	not_pinned_by: TypeID | None = None
	muted_by: TypeID | None = None
	not_muted_by: TypeID | None = None
	invite_pending_for: TypeID | None = None
	not_invite_pending_for: TypeID | None = None


class ThreadSearchFilters(BaseModel):
	"""structured filters applied to thread search (vector + autocomplete).

	every filter here is enforced NATIVELY at the vector layer (keyword payload
	fields), so a filtered search still returns a full page. the SQL pass that
	follows mirrors them as a redundant second layer, never as the gate.
	"""

	owner_id: TypeID | None = None
	project_id: TypeID | None = None
	include_hidden: bool = False
	include_deleted: bool = False
	participant_scope: ParticipantScope = "all"
	include_all_branches: bool = Field(
		default=False,
		description=(
			"include message hits from inactive branches (edited or "
			"regenerated away) instead of only the active branch"
		),
	)
	archived_by: TypeID | None = None
	not_archived_by: TypeID | None = None
	pinned_by: TypeID | None = None
	not_pinned_by: TypeID | None = None
	muted_by: TypeID | None = None
	not_muted_by: TypeID | None = None
	invite_pending_for: TypeID | None = None
	not_invite_pending_for: TypeID | None = None


def participant_state_filters(
	filters: ThreadListFilters | ThreadSearchFilters,
) -> list[tuple[ParticipantStatus, TypeID | None, TypeID | None]]:
	"""return (status, include_user_id, exclude_user_id) for each state.

	the ``*_by`` / ``not_*_by`` pairs filter on a NAMED user's per-thread state
	(archive, pin, mute, pending invite). each names its own subject, so an
	inbox is ``not_archived_by=<me>&not_invite_pending_for=<me>`` and operators
	can inspect another user's views without impersonation. neither listing nor
	search ever reads the caller's own state implicitly.
	"""
	return [
		("archived", filters.archived_by, filters.not_archived_by),
		("pinned", filters.pinned_by, filters.not_pinned_by),
		("muted", filters.muted_by, filters.not_muted_by),
		(
			"invite_pending",
			filters.invite_pending_for,
			filters.not_invite_pending_for,
		),
	]


@dataclass(frozen=True)
class SiblingBranchCount:
	"""how many branches hang off one message."""

	parent_id: TypeID
	"""the message the branches hang off."""
	total: int
	"""how many there are, counting past the page's per-message cap."""


class SiblingBranchCountOut(BaseModel):
	"""wire shape of one message's branch count."""

	parent_id: TypeID
	"""the message the branches hang off."""
	total: int
	"""how many there are, counting past the page's per-message cap."""


@dataclass(frozen=True)
class BranchPage:
	"""one page of a thread branch, as the service returns it."""

	messages: list[Message]
	"""page messages in root-first order."""
	total: int
	"""messages in the whole branch."""
	skip: int
	"""page offset from the leaf end of the branch."""
	siblings: list[Message]
	"""branches hanging off this page's messages, capped per message."""
	sibling_counts: list[SiblingBranchCount]
	"""every forked message on this page with its full branch count."""
	cursor_toward_root: str | None = None
	"""resumes at the message above this page, unaffected by concurrent writes."""
	cursor_toward_leaf: str | None = None
	"""resumes at the message below this page."""

	@property
	def has_toward_root(self) -> bool:
		return self.skip + len(self.messages) < self.total

	@property
	def has_toward_leaf(self) -> bool:
		return self.skip > 0


class BranchPageOut[T](BaseModel):
	"""wire shape of one page of a thread branch."""

	messages: list[T]
	"""page messages in root-first order."""
	total: int
	"""messages in the whole branch."""
	skip: int
	"""page offset from the leaf end of the branch."""
	has_toward_root: bool
	"""messages exist between this page and the branch root."""
	has_toward_leaf: bool
	"""messages exist between this page and the branch leaf."""
	siblings: list[T]
	"""branches hanging off this page's messages, capped per message; page the
	rest from the siblings endpoint."""
	sibling_counts: list[SiblingBranchCountOut]
	"""every forked message on this page with its full branch count, so a fork
	can be labelled without fetching the branches."""
	cursor_toward_root: str | None = None
	"""pass as ``cursor`` to load the next page toward the branch root. prefer
	it over ``skip``: offsets shift when anyone writes mid-scroll, cursors do
	not."""
	cursor_toward_leaf: str | None = None
	"""pass as ``cursor`` to load the next page toward the branch leaf."""


def _populate_project_ids(data: Any) -> Any:
	"""attach project_ids to ORM instances without mutating schema defaults."""
	if isinstance(data, ThreadModel) and getattr(data, "is_temporary", None) is None:
		data.is_temporary = False

	if isinstance(data, ThreadModel) and not getattr(data, "project_ids", None):
		projects = getattr(data, "__dict__", {}).get("projects")
		if projects:
			project_ids = [
				project.id for project in projects if getattr(project, "id", None)
			]
			setattr(data, "project_ids", project_ids)
	return data


def _thread_scalar_payload(data: Any) -> Any:
	"""project an ORM thread to a dict of scalar fields without participants.

	participant identity is resolved asynchronously in the service layer
	(``build_thread_payload``) and assigned to the payload afterwards. this
	projection never reads the participants relationship, so payloads built
	from partially-loaded threads (event fanout, etc.) never lazy-load it.
	"""
	if not isinstance(data, ThreadModel):
		return data

	_populate_project_ids(data)
	return {
		"id": data.id,
		"owner_id": data.owner_id,
		"title": data.title,
		"tags": data.tags,
		"is_temporary": data.is_temporary,
		"project_ids": getattr(data, "project_ids", []),
		"projects": data.projects,
		"participants": [],
		"origin_message_id": data.origin_message_id,
		"current_message_id": data.current_message_id,
		"last_activity_at": data.last_activity_at,
		"deleted_at": data.deleted_at,
		"created_at": data.created_at,
		"updated_at": data.updated_at,
		"metadata": data.public_metadata,
	}


class ThreadBase(MetadataModel):
	"""fields shared across thread payloads."""

	title: str | None = None
	tags: list[str] = Field(default_factory=list)
	is_temporary: bool = False
	project_ids: list[TypeID] = Field(default_factory=list)


class ThreadCreate(ThreadBase, ForbidExtraModel):
	"""payload for creating a thread of any kind.

	a thread's nature is emergent from who is in it: pass no members for a solo
	AI chat, one member for a 1:1 DM (reused if one already exists), or several
	for a group. groups can be added as live participants (their current members
	get access continuously). agents can be added at creation, with an optional
	per-thread auto-reply agent.
	"""

	owner_id: TypeID
	member_user_ids: list[TypeID] = Field(default_factory=list)
	agent_ids: list[TypeID] = Field(default_factory=list)
	group_ids: list[TypeID] = Field(default_factory=list)


class ThreadPrivate(PrivateModel):
	"""operator-only view of a thread: its private metadata (content/state vectors).

	no private columns yet, so the inherited ``metadata`` is the whole facet.
	it is still a named type so the generated client schema does not have to be
	renamed when a private column is added.
	"""


class ThreadPrivateInput(PrivateInputModel):
	"""operator-only fields on a thread write (see ``ThreadPrivate``)."""


class ThreadUpdate(
	MetadataUpdateModel,
	ForbidExtraModel,
	PrivateInputFacetModel[ThreadPrivateInput],
):
	"""payload for updating a thread."""

	title: str | None | MissingType = MISSING
	tags: list[str] | MissingType = MISSING
	is_temporary: bool | MissingType = MISSING
	project_ids: list[TypeID] | MissingType = MISSING
	owner_id: TypeID | MissingType = MISSING
	current_message_id: TypeID | None | MissingType = MISSING


class ThreadSummary(ORMModel):
	"""compact representation for listings."""

	id: TypeID
	title: str | None = None
	is_temporary: bool = False
	last_activity_at: datetime
	project_ids: list[TypeID] = Field(default_factory=list)

	@model_validator(mode="before")
	@classmethod
	def _ensure_project_ids(cls, data: Any) -> Any:
		return _populate_project_ids(data)


class Thread(ThreadBase, TimestampedModel, PrivateFacetModel[ThreadPrivate]):
	"""detailed response schema."""

	id: TypeID
	owner_id: TypeID
	origin_message_id: TypeID | None = None
	current_message_id: TypeID | None = None
	last_activity_at: datetime
	deleted_at: datetime | None = None
	projects: list[ProjectSchema] = Field(default_factory=list)
	participants: list[ThreadParticipantSchema] = Field(default_factory=list)
	last_message: MessageSchema | None = Field(
		default=None,
		description="the thread's current message, when the caller asked for it.",
	)

	@model_validator(mode="before")
	@classmethod
	def _project_scalar_payload(cls, data: Any) -> Any:
		return _thread_scalar_payload(data)


class ParticipantsAddRequest(BaseModel):
	"""participants to add to a thread in one operation."""

	model_config = ConfigDict(extra="forbid")

	user_ids: list[TypeID] = Field(default_factory=list)
	group_ids: list[TypeID] = Field(default_factory=list)
	agent_ids: list[TypeID] = Field(default_factory=list)


class AgentParticipantUpdate(BaseModel):
	"""fields that may be changed on an agent's thread participation."""

	model_config = ConfigDict(extra="forbid")

	invoke_on_mention: bool | None = Field(
		description="null inherits the agent's own setting.",
	)


class ThreadUserStateUpdate(BaseModel):
	"""payload to update the caller's private per-thread state.

	each flag is optional; omitted flags are left unchanged. these are personal
	to the user (mute / pin / archive their own view), distinct from membership.
	"""

	model_config = ConfigDict(extra="forbid")

	muted: bool | None = None
	pinned: bool | None = None
	archived: bool | None = None


class ThreadSummaryRecord(MetadataModel, TimestampedModel):
	"""stored summary record for a thread."""

	id: TypeID
	thread_id: TypeID
	purpose: SummaryPurpose
	start_message_id: TypeID | None = None
	end_message_id: TypeID | None = None
	message_count: int = 0
	content: str = ""
	superseded_by_id: TypeID | None = None


class ThreadSummaryUpdate(MetadataUpdateModel):
	"""payload for updating a stored summary."""

	content: str | MissingType = Field(default=MISSING, min_length=1)


class ThreadPassageRecord(TimestampedModel):
	"""stored transcript passage record for a thread."""

	id: TypeID
	first_message_id: TypeID
	last_message_id: TypeID
	anchor_message_id: TypeID
	part_index: int
	content_hash: str
	content: str
	enrichment: str | None = None
	enrichment_model_id: TypeID | None = None
	enriched_at: datetime | None = None
	enrichment_pipeline_v: int | None = None


class ThreadPassageUpdate(ForbidExtraModel):
	"""payload for overriding or clearing a stored passage enrichment."""

	enrichment: str | None | MissingType = Field(default=MISSING)


class ThreadPassageReconcileResponse(ORMModel):
	"""result of reconciling a thread's persisted passages and vectors."""

	thread_id: TypeID
	passages: int = 0
	built: int = 0
	deleted: int = 0
	purged: bool = False
	skipped: bool = False


class ThreadPassageEnrichResponse(ORMModel):
	"""result of running the passage enrichment pass for a thread."""

	thread_id: TypeID
	enriched: int = 0


class ThreadSwitchRequest(ForbidExtraModel):
	"""payload to switch a thread's active branch."""

	message_id: TypeID


class ThreadSwitchResponse(ORMModel):
	"""response for a thread branch switch."""

	ok: bool
	current_message_id: TypeID | None = None


class ThreadMaintenanceRunRequest(ForbidExtraModel):
	"""request body for running thread maintenance."""

	replace_metadata: bool = False
