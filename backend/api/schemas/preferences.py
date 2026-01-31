"""user preferences schemas.

typed schema for user-level preferences stored as JSONB.
this provides validation and schema generation for the frontend.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# appearance preferences
class AppearancePreferences(BaseModel):
	"""user appearance preferences."""

	model_config = ConfigDict(extra="forbid")

	theme_mode: Literal["light", "dark", "system"] | None = Field(
		default=None,
		alias="themeMode",
		description="theme mode preference",
	)
	accent: Literal["purple", "blue", "green", "orange", "pink", "red"] | None = Field(
		default=None,
		description="accent color preference",
	)
	auto_accent_colors: bool | None = Field(
		default=None,
		alias="autoAccentColors",
		description="when enabled, accent colors change automatically based on context",
	)
	background: (
		Literal[
			"galaxy",
			"darkveil",
			"lightbends",
			"lightrays",
			"silk",
			"static",
			"none",
		]
		| None
	) = Field(
		default=None,
		description="background wallpaper preference",
	)


# AI preferences
class AIPreferences(BaseModel):
	"""user AI preferences."""

	model_config = ConfigDict(extra="forbid")

	default_agent_id: str | None = Field(
		default=None,
		alias="defaultAgentId",
		description="preferred default agent id",
	)


# notification preferences
class NotificationPreferences(BaseModel):
	"""user notification preferences."""

	model_config = ConfigDict(extra="forbid")

	enabled: bool | None = Field(
		default=None,
		description="whether notifications are enabled",
	)
	sound: bool | None = Field(
		default=None,
		description="whether notification sounds are enabled",
	)


# privacy preferences
class PrivacyPreferences(BaseModel):
	"""user privacy preferences."""

	model_config = ConfigDict(extra="forbid")

	save_history: bool | None = Field(
		default=None,
		alias="saveHistory",
		description="whether to save chat history",
	)
	share_usage_data: bool | None = Field(
		default=None,
		alias="shareUsageData",
		description="whether to share anonymous usage data",
	)


# accessibility preferences
class AccessibilityPreferences(BaseModel):
	"""user accessibility preferences."""

	model_config = ConfigDict(extra="forbid")

	haptic_feedback: bool | None = Field(
		default=None,
		alias="hapticFeedback",
		description="whether haptic feedback is enabled on compatible devices",
	)


# the main preferences schema
class UserPreferences(BaseModel):
	"""complete user preferences schema.

	all fields are optional to support partial updates.
	stored as JSONB in the user table.
	"""

	model_config = ConfigDict(
		extra="allow",  # allow extra fields for forward compatibility
		populate_by_name=True,  # allow both snake_case and camelCase
	)

	appearance: AppearancePreferences | None = Field(
		default=None,
		description="appearance preferences",
	)
	ai: AIPreferences | None = Field(
		default=None,
		description="AI preferences",
	)
	notifications: NotificationPreferences | None = Field(
		default=None,
		description="notification preferences",
	)
	privacy: PrivacyPreferences | None = Field(
		default=None,
		description="privacy preferences",
	)
	accessibility: AccessibilityPreferences | None = Field(
		default=None,
		description="accessibility preferences",
	)
