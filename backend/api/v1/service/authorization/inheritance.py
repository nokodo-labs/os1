"""parent-child resource relationships for inherited ACL resolution."""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import Table, and_, exists, false, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute
from sqlalchemy.sql import ColumnElement

from api.models.access_rule import AccessLevel
from api.models.agent import Agent
from api.models.calendar import Calendar
from api.models.file import File
from api.models.many_to_many import (
	calendar_project_association,
	file_project_association,
	note_project_association,
	reminder_list_project_association,
	thread_project_association,
)
from api.models.message import Message
from api.models.message_attachment import MessageAttachment
from api.models.note import Note
from api.models.project import Project
from api.models.reminder import ReminderList
from api.models.thread import Thread
from api.models.thread_participant import ThreadParticipant
from api.permissions import ResourceType, highest_access
from api.v1.service.authentication import Principal
from api.v1.service.authorization.config import (
	CONTAINED_LEVELS,
	MAX_INHERITANCE_DEPTH,
	READ_ONLY_LEVELS,
	RESOURCE_CONFIG,
	InheritedLevels,
	ParentGrant,
	is_leaf_resource_config,
	level_satisfies,
)
from api.v1.service.authorization.types import AccessSubject
from nokodo_ai.utils.typeid import TypeID


ParentAccessPredicate = Callable[
	[AccessSubject, ResourceType, AccessLevel], ColumnElement[bool]
]

ParentTraversal = Callable[[AccessLevel], ColumnElement[bool]]
"""builds the join from child to parent, given the level required of the parent."""


@dataclass(frozen=True, slots=True)
class ParentResourceRef:
	"""a reachable parent plus the semantics of the edge that reached it."""

	parent_type: ResourceType
	parent_id: TypeID
	inherited_levels: InheritedLevels
	transitive: bool = True


@dataclass(frozen=True, slots=True)
class AccessTraversalState:
	"""depth and non-transitive state for one authorization path."""

	depth: int = 0
	non_transitive_used: bool = False


def _inherited_levels_predicate(
	grants: tuple[ParentGrant, ...],
	author_fk: InstrumentedAttribute | None,
	subject: AccessSubject,
	traverse: ParentTraversal,
) -> ColumnElement[bool]:
	"""turn one row of an inheritance table into SQL.

	shared by every link type so the table is interpreted identically no matter
	how the edge is stored.
	"""
	predicates: list[ColumnElement[bool]] = []
	for grant in grants:
		if not grant.requires_author:
			predicates.append(traverse(grant.parent_level))
			continue
		if author_fk is None:
			continue
		predicates.append(
			and_(
				author_fk
				== (subject.user.id if isinstance(subject, Principal) else subject),
				traverse(grant.parent_level),
			)
		)
	if not predicates:
		return false()
	return or_(*predicates)


class ResourceParentLink(Protocol):
	"""relationship path that lets a parent resource grant child access."""

	# properties: read-only members (implementations are frozen dataclasses).
	@property
	def parent_type(self) -> ResourceType: ...

	@property
	def child_type(self) -> ResourceType: ...

	@property
	def max_inherited_level(self) -> AccessLevel | None: ...

	@property
	def inherited_levels(self) -> InheritedLevels: ...

	@property
	def author_fk(self) -> InstrumentedAttribute | None: ...

	@property
	def link_key(self) -> str: ...

	@property
	def transitive(self) -> bool: ...

	def parent_access_predicate(
		self,
		subject: AccessSubject,
		required_level: AccessLevel,
		resolve_parent_access: ParentAccessPredicate,
	) -> ColumnElement[bool]: ...

	async def load_parent_ids(
		self,
		resource_id: TypeID,
		session: AsyncSession,
	) -> set[TypeID]: ...

	async def load_parent_ids_bulk(
		self,
		resource_ids: Iterable[TypeID],
		session: AsyncSession,
	) -> dict[TypeID, set[TypeID]]: ...


@dataclass(frozen=True, slots=True)
class ManyToManyResourceParentLink:
	"""parent-child link represented by an association table."""

	parent_type: ResourceType
	child_type: ResourceType
	association: Table
	parent_fk: ColumnElement[str]
	child_fk: ColumnElement[str]
	parent_id_col: InstrumentedAttribute
	child_id_col: InstrumentedAttribute
	inherited_levels: InheritedLevels = CONTAINED_LEVELS
	author_fk: InstrumentedAttribute | None = None

	@property
	def link_key(self) -> str:
		return (
			f"m2m:{self.parent_type.value}:{self.child_type.value}:"
			f"{self.association.name}"
		)

	@property
	def transitive(self) -> bool:
		return True

	@property
	def max_inherited_level(self) -> AccessLevel | None:
		return highest_access(self.inherited_levels.keys())

	def parent_access_predicate(
		self,
		subject: AccessSubject,
		required_level: AccessLevel,
		resolve_parent_access: ParentAccessPredicate,
	) -> ColumnElement[bool]:
		return _inherited_levels_predicate(
			self.inherited_levels.get(required_level, ()),
			self.author_fk,
			subject,
			lambda parent_level: exists(
				select(1)
				.select_from(self.association)
				.where(
					self.child_fk == self.child_id_col,
					self.parent_fk == self.parent_id_col,
					resolve_parent_access(
						subject,
						self.parent_type,
						parent_level,
					),
				)
				.correlate_except(self.association, self.parent_id_col.class_)
			),
		)

	async def load_parent_ids(
		self,
		resource_id: TypeID,
		session: AsyncSession,
	) -> set[TypeID]:
		return (await self.load_parent_ids_bulk([resource_id], session)).get(
			resource_id,
			set(),
		)

	async def load_parent_ids_bulk(
		self,
		resource_ids: Iterable[TypeID],
		session: AsyncSession,
	) -> dict[TypeID, set[TypeID]]:
		resource_id_values = list(dict.fromkeys(resource_ids))
		if not resource_id_values:
			return {}
		rows = (
			await session.execute(
				select(self.child_fk, self.parent_fk).where(
					self.child_fk.in_(resource_id_values)
				)
			)
		).all()
		result: dict[TypeID, set[TypeID]] = {}
		for child_id, parent_id in rows:
			result.setdefault(TypeID(child_id), set()).add(TypeID(parent_id))
		return result


@dataclass(frozen=True, slots=True)
class MessageAttachmentThreadParentLink:
	"""resource-to-thread link through a message attachment."""

	parent_type: ResourceType
	child_type: ResourceType
	parent_id_col: InstrumentedAttribute
	child_id_col: InstrumentedAttribute
	attachment_fk: InstrumentedAttribute
	inherited_levels: InheritedLevels = READ_ONLY_LEVELS
	author_fk: InstrumentedAttribute | None = None

	@property
	def link_key(self) -> str:
		return f"attachment:{self.child_type.value}"

	@property
	def transitive(self) -> bool:
		return False

	@property
	def max_inherited_level(self) -> AccessLevel | None:
		return highest_access(self.inherited_levels.keys())

	def parent_access_predicate(
		self,
		subject: AccessSubject,
		required_level: AccessLevel,
		resolve_parent_access: ParentAccessPredicate,
	) -> ColumnElement[bool]:
		return _inherited_levels_predicate(
			self.inherited_levels.get(required_level, ()),
			self.author_fk,
			subject,
			lambda parent_level: exists(
				select(1)
				.select_from(MessageAttachment)
				.join(Message, MessageAttachment.message_id == Message.id)
				.where(
					self.attachment_fk == self.child_id_col,
					Message.thread_id.in_(
						select(self.parent_id_col).where(
							resolve_parent_access(
								subject,
								self.parent_type,
								parent_level,
							)
						)
					),
				)
				.correlate_except(MessageAttachment, Message)
			),
		)

	async def load_parent_ids(
		self,
		resource_id: TypeID,
		session: AsyncSession,
	) -> set[TypeID]:
		return (await self.load_parent_ids_bulk([resource_id], session)).get(
			resource_id,
			set(),
		)

	async def load_parent_ids_bulk(
		self,
		resource_ids: Iterable[TypeID],
		session: AsyncSession,
	) -> dict[TypeID, set[TypeID]]:
		resource_id_values = list(dict.fromkeys(resource_ids))
		if not resource_id_values:
			return {}
		rows = (
			await session.execute(
				select(self.attachment_fk, Message.thread_id)
				.select_from(MessageAttachment)
				.join(Message, MessageAttachment.message_id == Message.id)
				.where(self.attachment_fk.in_(resource_id_values))
			)
		).all()
		result: dict[TypeID, set[TypeID]] = {}
		for child_id, parent_id in rows:
			result.setdefault(TypeID(child_id), set()).add(TypeID(parent_id))
		return result


@dataclass(frozen=True, slots=True)
class ColumnJoinResourceParentLink:
	"""parent-child link where one table carries both fk columns directly.

	the child fk may be nullable (e.g. agent columns on participant/message
	rows), so child id lookups filter nulls.
	"""

	parent_type: ResourceType
	child_type: ResourceType
	child_fk: InstrumentedAttribute
	parent_fk: InstrumentedAttribute
	parent_id_col: InstrumentedAttribute
	child_id_col: InstrumentedAttribute
	inherited_levels: InheritedLevels = CONTAINED_LEVELS
	author_fk: InstrumentedAttribute | None = None

	@property
	def link_key(self) -> str:
		return (
			f"column:{self.parent_type.value}:{self.child_type.value}:"
			f"{self.child_fk.class_.__tablename__}:{self.child_fk.key}:{self.parent_fk.key}"
		)

	@property
	def transitive(self) -> bool:
		return True

	@property
	def max_inherited_level(self) -> AccessLevel | None:
		return highest_access(self.inherited_levels.keys())

	def parent_access_predicate(
		self,
		subject: AccessSubject,
		required_level: AccessLevel,
		resolve_parent_access: ParentAccessPredicate,
	) -> ColumnElement[bool]:
		return _inherited_levels_predicate(
			self.inherited_levels.get(required_level, ()),
			self.author_fk,
			subject,
			lambda parent_level: exists(
				select(1)
				.where(
					self.child_fk == self.child_id_col,
					self.parent_fk == self.parent_id_col,
					resolve_parent_access(
						subject,
						self.parent_type,
						parent_level,
					),
				)
				.correlate_except(self.child_fk.class_, self.parent_id_col.class_)
			),
		)

	async def load_parent_ids(
		self,
		resource_id: TypeID,
		session: AsyncSession,
	) -> set[TypeID]:
		return (await self.load_parent_ids_bulk([resource_id], session)).get(
			resource_id,
			set(),
		)

	async def load_parent_ids_bulk(
		self,
		resource_ids: Iterable[TypeID],
		session: AsyncSession,
	) -> dict[TypeID, set[TypeID]]:
		resource_id_values = list(dict.fromkeys(resource_ids))
		if not resource_id_values:
			return {}
		rows = (
			await session.execute(
				select(self.child_fk, self.parent_fk).where(
					self.child_fk.in_(resource_id_values)
				)
			)
		).all()
		result: dict[TypeID, set[TypeID]] = {}
		for child_id, parent_id in rows:
			result.setdefault(TypeID(child_id), set()).add(TypeID(parent_id))
		return result


@dataclass(frozen=True, slots=True)
class DirectResourceParentLink:
	"""parent link stored on the child resource row."""

	parent_type: ResourceType
	child_type: ResourceType
	child_id_col: InstrumentedAttribute
	parent_fk: InstrumentedAttribute
	parent_id_col: InstrumentedAttribute
	inherited_levels: InheritedLevels = CONTAINED_LEVELS
	author_fk: InstrumentedAttribute | None = None

	@property
	def link_key(self) -> str:
		return (
			f"direct:{self.parent_type.value}:{self.child_type.value}:"
			f"{self.parent_fk.key}"
		)

	@property
	def transitive(self) -> bool:
		return True

	@property
	def max_inherited_level(self) -> AccessLevel | None:
		return highest_access(self.inherited_levels.keys())

	def parent_access_predicate(
		self,
		subject: AccessSubject,
		required_level: AccessLevel,
		resolve_parent_access: ParentAccessPredicate,
	) -> ColumnElement[bool]:
		return _inherited_levels_predicate(
			self.inherited_levels.get(required_level, ()),
			self.author_fk,
			subject,
			lambda parent_level: self.parent_fk.in_(
				select(self.parent_id_col).where(
					resolve_parent_access(
						subject,
						self.parent_type,
						parent_level,
					)
				)
			),
		)

	async def load_parent_ids(
		self,
		resource_id: TypeID,
		session: AsyncSession,
	) -> set[TypeID]:
		return (await self.load_parent_ids_bulk([resource_id], session)).get(
			resource_id,
			set(),
		)

	async def load_parent_ids_bulk(
		self,
		resource_ids: Iterable[TypeID],
		session: AsyncSession,
	) -> dict[TypeID, set[TypeID]]:
		resource_id_values = list(dict.fromkeys(resource_ids))
		if not resource_id_values:
			return {}
		rows = (
			await session.execute(
				select(self.child_id_col, self.parent_fk).where(
					self.child_id_col.in_(resource_id_values)
				)
			)
		).all()
		return {
			TypeID(child_id): {TypeID(parent_id)}
			for child_id, parent_id in rows
			if parent_id is not None
		}


RESOURCE_PARENT_LINKS: tuple[ResourceParentLink, ...] = (
	ManyToManyResourceParentLink(
		parent_type=ResourceType.PROJECT,
		child_type=ResourceType.THREAD,
		association=thread_project_association,
		parent_fk=thread_project_association.c.project_id,
		child_fk=thread_project_association.c.thread_id,
		parent_id_col=Project.id,
		child_id_col=Thread.id,
	),
	ManyToManyResourceParentLink(
		parent_type=ResourceType.PROJECT,
		child_type=ResourceType.FILE,
		association=file_project_association,
		parent_fk=file_project_association.c.project_id,
		child_fk=file_project_association.c.file_id,
		parent_id_col=Project.id,
		child_id_col=File.id,
	),
	ManyToManyResourceParentLink(
		parent_type=ResourceType.PROJECT,
		child_type=ResourceType.NOTE,
		association=note_project_association,
		parent_fk=note_project_association.c.project_id,
		child_fk=note_project_association.c.note_id,
		parent_id_col=Project.id,
		child_id_col=Note.id,
	),
	ManyToManyResourceParentLink(
		parent_type=ResourceType.PROJECT,
		child_type=ResourceType.REMINDER_LIST,
		association=reminder_list_project_association,
		parent_fk=reminder_list_project_association.c.project_id,
		child_fk=reminder_list_project_association.c.reminder_list_id,
		parent_id_col=Project.id,
		child_id_col=ReminderList.id,
	),
	ManyToManyResourceParentLink(
		parent_type=ResourceType.PROJECT,
		child_type=ResourceType.CALENDAR,
		association=calendar_project_association,
		parent_fk=calendar_project_association.c.project_id,
		child_fk=calendar_project_association.c.calendar_id,
		parent_id_col=Project.id,
		child_id_col=Calendar.id,
	),
	*(
		MessageAttachmentThreadParentLink(
			parent_type=ResourceType.THREAD,
			child_type=child_type,
			parent_id_col=Thread.id,
			child_id_col=config.id_col,
			attachment_fk=attachment_fk,
			inherited_levels=READ_ONLY_LEVELS,
		)
		for child_type, config in RESOURCE_CONFIG.items()
		if (attachment_fk := config.attachment_fk) is not None
	),
	# containment edges are generated from the leaf configs so the parent
	# relationship and its inheritance table are declared exactly once.
	*(
		DirectResourceParentLink(
			parent_type=config.parent_type,
			child_type=child_type,
			parent_fk=config.parent_fk,
			parent_id_col=RESOURCE_CONFIG[config.parent_type].id_col,
			child_id_col=config.id_col,
			inherited_levels=config.inherited_levels,
			author_fk=config.author_fk,
		)
		for child_type, config in RESOURCE_CONFIG.items()
		if is_leaf_resource_config(config)
	),
	# agents referenced in a thread (participant or message author) inherit
	# read-only.
	ColumnJoinResourceParentLink(
		parent_type=ResourceType.THREAD,
		child_type=ResourceType.AGENT,
		child_fk=ThreadParticipant.agent_id,
		parent_fk=ThreadParticipant.thread_id,
		parent_id_col=Thread.id,
		child_id_col=Agent.id,
		inherited_levels=READ_ONLY_LEVELS,
	),
	ColumnJoinResourceParentLink(
		parent_type=ResourceType.THREAD,
		child_type=ResourceType.AGENT,
		child_fk=Message.sender_agent_id,
		parent_fk=Message.thread_id,
		parent_id_col=Thread.id,
		child_id_col=Agent.id,
		inherited_levels=READ_ONLY_LEVELS,
	),
)


PARENT_LINKS_BY_CHILD: dict[ResourceType, tuple[ResourceParentLink, ...]] = {
	resource_type: tuple(
		link for link in RESOURCE_PARENT_LINKS if link.child_type == resource_type
	)
	for resource_type in ResourceType
}

PARENT_LINKS_BY_PARENT: dict[ResourceType, tuple[ResourceParentLink, ...]] = {
	resource_type: tuple(
		link for link in RESOURCE_PARENT_LINKS if link.parent_type == resource_type
	)
	for resource_type in ResourceType
}


def affected_resource_types(
	resource_types: list[ResourceType],
) -> list[ResourceType]:
	"""return resource types whose access can inherit from the given types."""
	result: list[ResourceType] = []
	visited: set[tuple[ResourceType, bool]] = set()
	frontier = [
		(resource_type, False) for resource_type in dict.fromkeys(resource_types)
	]
	while frontier:
		resource_type, non_transitive_used = frontier.pop()
		state = (resource_type, non_transitive_used)
		if state in visited:
			continue
		visited.add(state)
		if resource_type not in result:
			result.append(resource_type)
		for link in PARENT_LINKS_BY_PARENT[resource_type]:
			if not link.transitive and non_transitive_used:
				continue
			frontier.append(
				(link.child_type, non_transitive_used or not link.transitive)
			)
	return result


for _validated_link in RESOURCE_PARENT_LINKS:
	if (
		any(
			grant.requires_author
			for grants in _validated_link.inherited_levels.values()
			for grant in grants
		)
		and _validated_link.author_fk is None
	):
		raise RuntimeError(
			f"{_validated_link.child_type.value} author-gated parent link has no "
			"author column"
		)


def inherited_resource_access_predicate(
	subject: AccessSubject,
	resource_type: ResourceType,
	required_level: AccessLevel,
	parent_access_predicate: Callable[
		[AccessSubject, ResourceType, AccessLevel, AccessTraversalState],
		ColumnElement[bool],
	],
	traversal: AccessTraversalState = AccessTraversalState(),
) -> ColumnElement[bool] | None:
	"""build inherited SQL access within the shared traversal bound."""
	if traversal.depth >= MAX_INHERITANCE_DEPTH:
		return None
	# skip links whose cap cannot satisfy the required level.
	predicates = [
		link.parent_access_predicate(
			subject,
			required_level,
			lambda nested_subject, nested_type, nested_level, link=link: (
				parent_access_predicate(
					nested_subject,
					nested_type,
					nested_level,
					AccessTraversalState(
						depth=traversal.depth + 1,
						non_transitive_used=(
							traversal.non_transitive_used or not link.transitive
						),
					),
				)
			),
		)
		for link in PARENT_LINKS_BY_CHILD[resource_type]
		if not (not link.transitive and traversal.non_transitive_used)
		and (
			link.max_inherited_level is None
			or level_satisfies(link.max_inherited_level, required_level)
		)
	]
	if not predicates:
		return None
	return or_(*predicates)


async def load_parent_resource_refs(
	resource_type: ResourceType,
	resource_id: TypeID,
	session: AsyncSession,
) -> list[ParentResourceRef]:
	"""return parent resources that can grant inherited access."""
	parents: list[ParentResourceRef] = []
	for link in PARENT_LINKS_BY_CHILD[resource_type]:
		parent_ids = await link.load_parent_ids(resource_id, session)
		parents.extend(
			ParentResourceRef(
				parent_type=link.parent_type,
				parent_id=parent_id,
				inherited_levels=link.inherited_levels,
				transitive=link.transitive,
			)
			for parent_id in parent_ids
		)
	return parents
