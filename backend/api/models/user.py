"""User model."""

from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from api.core.database import Base


class User(Base):
	"""User model."""

	__tablename__ = "users"

	id: Mapped[int] = mapped_column(primary_key=True, index=True)
	email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
	username: Mapped[str] = mapped_column(String(100), unique=True, index=True)
	hashed_password: Mapped[str] = mapped_column(String(255))
	is_active: Mapped[bool] = mapped_column(default=True)
	is_superuser: Mapped[bool] = mapped_column(default=False)
	created_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), server_default=func.now()
	)
	updated_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
	)
