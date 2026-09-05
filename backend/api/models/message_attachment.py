"""message attachment model."""

from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.models.base import TYPEID_LENGTH, Base
from api.models.mixins import TimestampMixin, TypeIDPrimaryKeyMixin
from api.permissions import ATTACHABLE_RESOURCE_TYPES, ResourceType
from nokodo_ai.utils.typeid import TypeID


if TYPE_CHECKING:
	from api.models.calendar import Calendar, CalendarEvent
	from api.models.file import File
	from api.models.message import Message
	from api.models.note import Note
	from api.models.project import Project
	from api.models.reminder import Reminder, ReminderList
	from api.models.thread import Thread


def resource_fk_name(resource_type: ResourceType) -> str:
	"""column holding the attached resource id for this resource type."""
	return f"{resource_type.value}_id"


class MessageAttachment(TypeIDPrimaryKeyMixin, TimestampMixin, Base):
	"""ordered resource attached to a message."""

	__tablename__ = "message_attachments"
	__typeid_prefix__ = "matt"
	__table_args__ = (
		CheckConstraint(
			"(CASE WHEN file_id IS NULL THEN 0 ELSE 1 END + "
			"CASE WHEN note_id IS NULL THEN 0 ELSE 1 END + "
			"CASE WHEN thread_id IS NULL THEN 0 ELSE 1 END + "
			"CASE WHEN project_id IS NULL THEN 0 ELSE 1 END + "
			"CASE WHEN reminder_id IS NULL THEN 0 ELSE 1 END + "
			"CASE WHEN reminder_list_id IS NULL THEN 0 ELSE 1 END + "
			"CASE WHEN calendar_event_id IS NULL THEN 0 ELSE 1 END + "
			"CASE WHEN calendar_id IS NULL THEN 0 ELSE 1 END) = 1",
			name="ck_message_attachments_single_resource",
		),
		Index(
			"uq_message_attachments_message_file",
			"message_id",
			"file_id",
			unique=True,
			postgresql_where=text("file_id IS NOT NULL"),
		),
		Index(
			"uq_message_attachments_message_note",
			"message_id",
			"note_id",
			unique=True,
			postgresql_where=text("note_id IS NOT NULL"),
		),
		Index(
			"uq_message_attachments_message_thread",
			"message_id",
			"thread_id",
			unique=True,
			postgresql_where=text("thread_id IS NOT NULL"),
		),
		Index(
			"uq_message_attachments_message_project",
			"message_id",
			"project_id",
			unique=True,
			postgresql_where=text("project_id IS NOT NULL"),
		),
		Index(
			"uq_message_attachments_message_reminder",
			"message_id",
			"reminder_id",
			unique=True,
			postgresql_where=text("reminder_id IS NOT NULL"),
		),
		Index(
			"uq_message_attachments_message_reminder_list",
			"message_id",
			"reminder_list_id",
			unique=True,
			postgresql_where=text("reminder_list_id IS NOT NULL"),
		),
		Index(
			"uq_message_attachments_message_calendar_event",
			"message_id",
			"calendar_event_id",
			unique=True,
			postgresql_where=text("calendar_event_id IS NOT NULL"),
		),
		Index(
			"uq_message_attachments_message_calendar",
			"message_id",
			"calendar_id",
			unique=True,
			postgresql_where=text("calendar_id IS NOT NULL"),
		),
	)

	message_id: Mapped[TypeID] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("messages.id", ondelete="CASCADE"),
		index=True,
	)
	position: Mapped[int] = mapped_column(Integer)
	file_id: Mapped[TypeID | None] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("files.id", ondelete="CASCADE"),
		index=True,
	)
	note_id: Mapped[TypeID | None] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("notes.id", ondelete="CASCADE"),
		index=True,
	)
	thread_id: Mapped[TypeID | None] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("threads.id", ondelete="CASCADE"),
		index=True,
	)
	project_id: Mapped[TypeID | None] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("projects.id", ondelete="CASCADE"),
		index=True,
	)
	reminder_id: Mapped[TypeID | None] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("reminders.id", ondelete="CASCADE"),
		index=True,
	)
	reminder_list_id: Mapped[TypeID | None] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("reminder_lists.id", ondelete="CASCADE"),
		index=True,
	)
	calendar_event_id: Mapped[TypeID | None] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("calendar_events.id", ondelete="CASCADE"),
		index=True,
	)
	calendar_id: Mapped[TypeID | None] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("calendars.id", ondelete="CASCADE"),
		index=True,
	)

	message: Mapped[Message] = relationship(
		"Message",
		back_populates="attachment_links",
		foreign_keys=[message_id],
	)
	file: Mapped[File | None] = relationship("File", foreign_keys=[file_id])
	note: Mapped[Note | None] = relationship("Note", foreign_keys=[note_id])
	thread: Mapped[Thread | None] = relationship("Thread", foreign_keys=[thread_id])
	project: Mapped[Project | None] = relationship("Project", foreign_keys=[project_id])
	reminder: Mapped[Reminder | None] = relationship(
		"Reminder", foreign_keys=[reminder_id]
	)
	reminder_list: Mapped[ReminderList | None] = relationship(
		"ReminderList", foreign_keys=[reminder_list_id]
	)
	calendar_event: Mapped[CalendarEvent | None] = relationship(
		"CalendarEvent", foreign_keys=[calendar_event_id]
	)
	calendar: Mapped[Calendar | None] = relationship(
		"Calendar", foreign_keys=[calendar_id]
	)

	@property
	def resource_ref(self) -> dict[str, object]:
		"""public resource reference for this attachment."""
		for resource_type in ATTACHABLE_RESOURCE_TYPES:
			value = self.__dict__.get(resource_fk_name(resource_type))
			if value is not None:
				return {"type": resource_type, "id": value}
		raise RuntimeError("message attachment has no resource")
