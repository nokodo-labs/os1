"""calendar models."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
	ARRAY,
	Boolean,
	DateTime,
	Float,
	ForeignKey,
	ForeignKeyConstraint,
	Index,
	Integer,
	String,
	Text,
	UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.models.base import TYPEID_LENGTH, Base
from api.models.many_to_many import calendar_project_association
from api.models.mixins import (
	MetadataJSONMixin,
	TimestampMixin,
	TypeIDPrimaryKeyMixin,
)
from nokodo_ai.types import JSONObject
from nokodo_ai.utils.typeid import TypeID


if TYPE_CHECKING:
	from api.models.access_rule import AccessRule
	from api.models.event import Event
	from api.models.project import Project
	from api.models.user import User


class Calendar(
	TypeIDPrimaryKeyMixin,
	TimestampMixin,
	MetadataJSONMixin,
	Base,
):
	"""user-owned calendar grouping for events."""

	__tablename__ = "calendars"
	__typeid_prefix__ = "cal"
	__table_args__ = (
		UniqueConstraint("owner_id", "name", name="uq_calendars_owner_name"),
		UniqueConstraint("id", "owner_id", name="uq_calendars_id_owner"),
		Index("ix_calendars_owner_default", "owner_id", "is_default"),
		Index(
			"idx_calendars_name_trgm",
			"name",
			postgresql_using="gin",
			postgresql_ops={"name": "gin_trgm_ops"},
		),
	)

	owner_id: Mapped[TypeID] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("users.id", ondelete="CASCADE"),
		index=True,
	)
	name: Mapped[str] = mapped_column(String(100))
	description: Mapped[str | None] = mapped_column(Text)
	color: Mapped[str] = mapped_column(String(7), default="#d45446")
	position: Mapped[float] = mapped_column(Float, default=0.0)
	is_default: Mapped[bool] = mapped_column(Boolean, default=False)
	timezone: Mapped[str | None] = mapped_column(String(64))

	owner: Mapped[User] = relationship("User", back_populates="calendars")
	projects: Mapped[list[Project]] = relationship(
		"Project",
		secondary=calendar_project_association,
		back_populates="calendars",
	)

	@property
	def project_ids(self) -> list[TypeID]:
		"""ids of linked projects (requires projects to be loaded)."""
		return [project.id for project in self.projects]

	events: Mapped[list[CalendarEvent]] = relationship(
		"CalendarEvent",
		back_populates="calendar",
		cascade="all, delete-orphan",
		foreign_keys="CalendarEvent.calendar_id",
	)
	access_rules: Mapped[list[AccessRule]] = relationship(
		"AccessRule",
		back_populates="calendar",
		cascade="all, delete-orphan",
	)
	activity_events: Mapped[list[Event]] = relationship(
		"Event",
		back_populates="calendar",
	)


class CalendarEvent(
	TypeIDPrimaryKeyMixin,
	TimestampMixin,
	MetadataJSONMixin,
	Base,
):
	"""user-owned calendar event."""

	__tablename__ = "calendar_events"
	__typeid_prefix__ = "calev"
	__table_args__ = (
		ForeignKeyConstraint(
			["calendar_id", "owner_id"],
			["calendars.id", "calendars.owner_id"],
			ondelete="CASCADE",
		),
		Index("ix_calendar_events_owner_start", "owner_id", "start_at"),
		Index("ix_calendar_events_owner_end", "owner_id", "end_at"),
		Index("ix_calendar_events_owner_calendar", "owner_id", "calendar_id"),
		Index("ix_calendar_events_calendar_start", "calendar_id", "start_at"),
		Index(
			"ix_calendar_events_calendar_recurrence_until",
			"calendar_id",
			"recurrence_until",
		),
		Index(
			"idx_calendar_events_title_trgm",
			"title",
			postgresql_using="gin",
			postgresql_ops={"title": "gin_trgm_ops"},
		),
		Index(
			"idx_calendar_events_description_trgm",
			"description",
			postgresql_using="gin",
			postgresql_ops={"description": "gin_trgm_ops"},
		),
		Index(
			"idx_calendar_events_location_trgm",
			"location",
			postgresql_using="gin",
			postgresql_ops={"location": "gin_trgm_ops"},
		),
		Index(
			"idx_calendar_events_virtual_url_trgm",
			"virtual_url",
			postgresql_using="gin",
			postgresql_ops={"virtual_url": "gin_trgm_ops"},
		),
	)

	owner_id: Mapped[TypeID] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("users.id", ondelete="CASCADE"),
		index=True,
	)
	title: Mapped[str] = mapped_column(String(200))
	description: Mapped[str | None] = mapped_column(Text)
	start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
	end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
	all_day: Mapped[bool] = mapped_column(Boolean, default=False)
	calendar_id: Mapped[TypeID] = mapped_column(
		String(TYPEID_LENGTH),
	)
	timezone: Mapped[str | None] = mapped_column(String(64))
	recurrence: Mapped[JSONObject | None] = mapped_column(JSONB)
	recurrence_until: Mapped[datetime | None] = mapped_column(
		DateTime(timezone=True),
		index=True,
	)
	series_origin_id: Mapped[TypeID | None] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("calendar_events.id"),
	)
	notification_offsets: Mapped[list[int]] = mapped_column(
		ARRAY(Integer),
		default=list,
	)
	location: Mapped[str | None] = mapped_column(String(255))
	virtual_url: Mapped[str | None] = mapped_column(String(512))
	labels: Mapped[list[str]] = mapped_column(ARRAY(String(50)), default=list)

	owner: Mapped[User] = relationship(
		"User",
		back_populates="calendar_events",
	)
	calendar: Mapped[Calendar] = relationship(
		"Calendar",
		back_populates="events",
		foreign_keys=[calendar_id],
	)
	series_origin: Mapped[CalendarEvent | None] = relationship(
		"CalendarEvent",
		remote_side="CalendarEvent.id",
	)
	overrides: Mapped[list[CalendarEventOverride]] = relationship(
		"CalendarEventOverride",
		back_populates="event",
		cascade="all, delete-orphan",
	)
	events: Mapped[list[Event]] = relationship(
		"Event",
		back_populates="calendar_event",
	)


class CalendarEventOverride(TimestampMixin, Base):
	"""single calendar event occurrence override."""

	__tablename__ = "calendar_event_overrides"
	__table_args__ = (
		Index(
			"ix_calendar_event_overrides_event_original",
			"event_id",
			"original_occurrence_at",
		),
	)

	event_id: Mapped[TypeID] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("calendar_events.id", ondelete="CASCADE"),
		primary_key=True,
	)
	original_occurrence_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True),
		primary_key=True,
	)
	cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
	new_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
	new_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
	payload_patch: Mapped[JSONObject] = mapped_column(JSONB, default=dict)

	event: Mapped[CalendarEvent] = relationship(
		"CalendarEvent",
		back_populates="overrides",
	)
