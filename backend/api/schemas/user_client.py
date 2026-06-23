"""user client schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from api.schemas.common import MISSING, MissingType, TimestampedModel
from api.schemas.preferences import (
	AccessibilityPreferences,
	AdvancedPreferences,
	AppearancePreferences,
)
from nokodo_ai.types.json import JSONObject
from nokodo_ai.utils.typeid import TypeID


class UserClientPreferences(BaseModel):
	"""client-specific preference overrides."""

	model_config = ConfigDict(extra="forbid", populate_by_name=True)

	appearance: AppearancePreferences | MissingType = Field(
		default=MISSING,
		description="client-specific appearance preference overrides",
	)
	accessibility: AccessibilityPreferences | MissingType = Field(
		default=MISSING,
		description="client-specific accessibility preference overrides",
	)
	advanced: AdvancedPreferences | MissingType = Field(
		default=MISSING,
		description="client-specific advanced preference overrides",
	)


class UserClientUpsert(BaseModel):
	"""request schema for registering a user client."""

	client_key: str = Field(min_length=8, max_length=128)
	name: str | None = Field(default=None, max_length=120)
	user_agent: str | None = Field(default=None, max_length=2048)
	info: JSONObject = Field(default_factory=dict)


class UserClientPatch(BaseModel):
	"""request schema for updating user-client-specific data."""

	name: str | None = Field(default=None, max_length=120)
	info: JSONObject | None = None


class UserClient(TimestampedModel):
	"""registered user client response."""

	id: TypeID
	user_id: TypeID
	client_key: str
	name: str | None = None
	user_agent: str | None = None
	info: JSONObject = Field(default_factory=dict)
	preferences: UserClientPreferences = Field(default_factory=UserClientPreferences)
	last_seen_at: datetime | None = None
