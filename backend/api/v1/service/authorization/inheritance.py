"""parent-child resource relationships for inherited ACL resolution."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import Table, exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute
from sqlalchemy.sql import ColumnElement

from api.models.access_rule import AccessLevel
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
from api.models.note import Note
from api.models.project import Project
from api.models.reminder import ReminderList
from api.models.thread import Thread
from api.permissions import ResourceType
from api.v1.service.auth import Principal
from nokodo_ai.utils.typeid import TypeID


ParentAccessPredicate = Callable[
	[Principal, ResourceType, AccessLevel], ColumnElement[bool]
]


class ResourceParentLink(Protocol):
	"""relationship path that lets a parent resource grant child access."""

	parent_type: ResourceType
	child_type: ResourceType

	def parent_access_predicate(
		self,
		principal: Principal,
		required_level: AccessLevel,
		parent_access_predicate: ParentAccessPredicate,
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

	async def load_child_ids(
		self,
		resource_id: TypeID,
		session: AsyncSession,
	) -> set[TypeID]: ...

	async def load_child_ids_bulk(
		self,
		resource_ids: Iterable[TypeID],
		session: AsyncSession,
	) -> set[TypeID]: ...


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

	def parent_access_predicate(
		self,
		principal: Principal,
		required_level: AccessLevel,
		parent_access_predicate: ParentAccessPredicate,
	) -> ColumnElement[bool]:
		return exists(
			select(1)
			.select_from(self.association)
			.where(
				self.child_fk == self.child_id_col,
				self.parent_fk == self.parent_id_col,
				parent_access_predicate(
					principal,
					self.parent_type,
					required_level,
				),
			)
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
			result.setdefault(TypeID(str(child_id)), set()).add(TypeID(str(parent_id)))
		return result

	async def load_child_ids(
		self,
		resource_id: TypeID,
		session: AsyncSession,
	) -> set[TypeID]:
		return await self.load_child_ids_bulk([resource_id], session)

	async def load_child_ids_bulk(
		self,
		resource_ids: Iterable[TypeID],
		session: AsyncSession,
	) -> set[TypeID]:
		resource_id_values = list(dict.fromkeys(resource_ids))
		if not resource_id_values:
			return set()
		rows = (
			await session.scalars(
				select(self.child_fk).where(self.parent_fk.in_(resource_id_values))
			)
		).all()
		return {TypeID(str(child_id)) for child_id in rows}


@dataclass(frozen=True, slots=True)
class FileMessageThreadParentLink:
	"""file-to-thread link through the message a file is attached to."""

	parent_type: ResourceType
	child_type: ResourceType
	parent_id_col: InstrumentedAttribute
	child_id_col: InstrumentedAttribute
	message_id_col: InstrumentedAttribute
	message_parent_fk: InstrumentedAttribute
	child_message_fk: InstrumentedAttribute

	def parent_access_predicate(
		self,
		principal: Principal,
		required_level: AccessLevel,
		parent_access_predicate: ParentAccessPredicate,
	) -> ColumnElement[bool]:
		return exists(
			select(1)
			.select_from(Message)
			.where(
				self.child_message_fk == self.message_id_col,
				self.message_parent_fk == self.parent_id_col,
				parent_access_predicate(
					principal,
					self.parent_type,
					required_level,
				),
			)
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
				select(self.child_id_col, self.message_parent_fk)
				.select_from(File)
				.join(Message, self.child_message_fk == self.message_id_col)
				.where(self.child_id_col.in_(resource_id_values))
			)
		).all()
		result: dict[TypeID, set[TypeID]] = {}
		for child_id, parent_id in rows:
			result.setdefault(TypeID(str(child_id)), set()).add(TypeID(str(parent_id)))
		return result

	async def load_child_ids(
		self,
		resource_id: TypeID,
		session: AsyncSession,
	) -> set[TypeID]:
		return await self.load_child_ids_bulk([resource_id], session)

	async def load_child_ids_bulk(
		self,
		resource_ids: Iterable[TypeID],
		session: AsyncSession,
	) -> set[TypeID]:
		resource_id_values = list(dict.fromkeys(resource_ids))
		if not resource_id_values:
			return set()
		rows = (
			await session.scalars(
				select(self.child_id_col)
				.select_from(File)
				.join(Message, self.child_message_fk == self.message_id_col)
				.where(self.message_parent_fk.in_(resource_id_values))
			)
		).all()
		return {TypeID(str(file_id)) for file_id in rows}


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
	FileMessageThreadParentLink(
		parent_type=ResourceType.THREAD,
		child_type=ResourceType.FILE,
		parent_id_col=Thread.id,
		child_id_col=File.id,
		message_id_col=Message.id,
		message_parent_fk=Message.thread_id,
		child_message_fk=File.message_id,
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


def inherited_resource_access_predicate(
	principal: Principal,
	resource_type: ResourceType,
	required_level: AccessLevel,
	parent_access_predicate: ParentAccessPredicate,
) -> ColumnElement[bool] | None:
	predicates = [
		link.parent_access_predicate(
			principal,
			required_level,
			parent_access_predicate,
		)
		for link in PARENT_LINKS_BY_CHILD[resource_type]
	]
	if not predicates:
		return None
	return or_(*predicates)


def inherited_parent_resource_types(
	resource_type: ResourceType,
) -> tuple[ResourceType, ...]:
	result: list[ResourceType] = []
	visited: set[ResourceType] = set()

	def visit(child_type: ResourceType) -> None:
		if child_type in visited:
			return
		visited.add(child_type)
		for link in PARENT_LINKS_BY_CHILD[child_type]:
			if link.parent_type not in result:
				result.append(link.parent_type)
			visit(link.parent_type)

	visit(resource_type)
	return tuple(result)


async def load_parent_resource_refs(
	resource_type: ResourceType,
	resource_id: TypeID,
	session: AsyncSession,
) -> list[tuple[ResourceType, TypeID]]:
	"""return parent resources that can grant inherited access."""
	parents: list[tuple[ResourceType, TypeID]] = []
	for link in PARENT_LINKS_BY_CHILD[resource_type]:
		parent_ids = await link.load_parent_ids(resource_id, session)
		parents.extend((link.parent_type, parent_id) for parent_id in parent_ids)
	return parents


async def load_descendant_resource_ids(
	resource_type: ResourceType,
	resource_id: TypeID,
	session: AsyncSession,
) -> dict[ResourceType, set[TypeID]]:
	"""return resources whose access may inherit from this resource."""
	descendants: dict[ResourceType, set[TypeID]] = {}
	visited: set[tuple[ResourceType, str]] = {(resource_type, str(resource_id))}
	frontier: dict[ResourceType, set[TypeID]] = {resource_type: {resource_id}}
	while frontier:
		next_frontier: dict[ResourceType, set[TypeID]] = {}
		for parent_type, parent_ids in frontier.items():
			for link in PARENT_LINKS_BY_PARENT[parent_type]:
				child_ids = await link.load_child_ids_bulk(parent_ids, session)
				new_child_ids: set[TypeID] = set()
				for child_id in child_ids:
					child_key = (link.child_type, str(child_id))
					if child_key in visited:
						continue
					visited.add(child_key)
					new_child_ids.add(child_id)
				if not new_child_ids:
					continue
				descendants.setdefault(link.child_type, set()).update(new_child_ids)
				next_frontier.setdefault(link.child_type, set()).update(new_child_ids)
		frontier = next_frontier
	return descendants
