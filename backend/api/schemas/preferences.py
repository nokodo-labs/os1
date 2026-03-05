"""user preferences schemas.

typed schema for user-level preferences stored as JSONB.
this provides validation and schema generation for the frontend.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# shared literal type for background options
BackgroundType = Literal[
	"galaxy",
	"darkveil",
	"lightbends",
	"lightrays",
	"silk",
	"fog",
	"clouds",
	"clouds-dark",
	"clouds2",
	"clouds2-dark",
	"grainient",
	"iridescence",
	"static",
	"none",
]


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
	background: BackgroundType | None = Field(
		default=None,
		description="background wallpaper preference "
		"used when auto_background is disabled",
	)
	auto_background: bool | None = Field(
		default=None,
		alias="autoBackground",
		description="when enabled, background changes automatically based on context",
	)
	static_color: str | None = Field(
		default=None,
		alias="staticColor",
		description="hex color used when background is set to 'static'",
	)
	bubble_tail_style: Literal["none", "whatsapp", "imessage"] | None = Field(
		default=None,
		alias="bubbleTailStyle",
		description="chat bubble tail style preference",
	)


# account / profile preferences (stored alongside other prefs)
class AccountPreferences(BaseModel):
	"""user account/profile preferences.

	profile data that doesn't warrant its own database column.
	"""

	model_config = ConfigDict(extra="forbid")

	bio: str | None = Field(
		default=None,
		description="personal bio visible to other users",
	)
	birth_date: str | None = Field(
		default=None,
		alias="birthDate",
		description="birth date in ISO 8601 format (YYYY-MM-DD)",
	)
	gender: str | None = Field(
		default=None,
		description="gender identity",
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
	bio: str | None = Field(
		default=None,
		description="AI-specific bio / about me for AI context",
	)
	use_account_bio: bool | None = Field(
		default=None,
		alias="useAccountBio",
		description="when true, use the account bio instead of a separate AI bio",
	)
	memories_enabled: bool | None = Field(
		default=None,
		alias="memoriesEnabled",
		description="whether AI memories are enabled",
	)
	chat_recall: bool | None = Field(
		default=None,
		alias="chatRecall",
		description="whether the AI can recall previous conversations",
	)
	custom_instructions: str | None = Field(
		default=None,
		alias="customInstructions",
		description="custom instructions for the AI to follow",
	)
	personality: str | None = Field(
		default=None,
		description="desired AI personality / tone description",
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
	use_location: bool | None = Field(
		default=None,
		alias="useLocation",
		description="whether to send precise location to personalise AI responses",
	)
	use_device_context: bool | None = Field(
		default=None,
		alias="useDeviceContext",
		description=(
			"whether to send device information (timezone, OS, browser)"
			" to personalise AI responses"
		),
	)
	use_battery_status: bool | None = Field(
		default=None,
		alias="useBatteryStatus",
		description=(
			"whether to send battery status details to personalise AI responses"
		),
	)


# accessibility preferences
class AccessibilityPreferences(BaseModel):
	"""user accessibility preferences."""

	model_config = ConfigDict(extra="ignore")

	haptic_feedback: bool | None = Field(
		default=None,
		alias="hapticFeedback",
		description="whether haptic feedback is enabled on compatible devices",
	)


# advanced preferences
class AdvancedPreferences(BaseModel):
	"""user advanced preferences."""

	model_config = ConfigDict(extra="forbid")

	svg_liquid_glass: bool | None = Field(
		default=None,
		alias="svgLiquidGlass",
		description=(
			"whether to enable svg-based liquid glass when supported by the browser"
		),
	)
	svg_liquid_glass_island: bool | None = Field(
		default=None,
		alias="svgLiquidGlassIsland",
		description=(
			"whether to enable svg-based liquid glass "
			"specifically for the Island component"
		),
	)
	svg_liquid_metal: bool | None = Field(
		default=None,
		alias="svgLiquidMetal",
		description=(
			"whether to enable svg-based liquid metal effects "
			"when supported by the browser"
		),
	)


# debug preferences
class DebugPreferences(BaseModel):
	"""user debug preferences (admin-only section)."""

	model_config = ConfigDict(extra="forbid")

	enable_debug_apps: bool | None = Field(
		default=None,
		alias="enableDebugApps",
		description="when enabled, placeholder/debug apps are shown on the home screen",
	)


# homepage preferences
class HomepagePreferences(BaseModel):
	"""user homepage preferences

	controls which suggestion apps appear on the home screen."""

	model_config = ConfigDict(extra="forbid")

	chats: bool | None = Field(
		default=None,
		description="show chats in homepage suggestions",
	)
	reminders: bool | None = Field(
		default=None,
		description="show reminders in homepage suggestions",
	)
	notes: bool | None = Field(
		default=None,
		description="show notes in homepage suggestions",
	)
	friends: bool | None = Field(
		default=None,
		description="show friends in homepage suggestions",
	)
	library: bool | None = Field(
		default=None,
		description="show library in homepage suggestions",
	)
	calendar: bool | None = Field(
		default=None,
		description="show calendar in homepage suggestions",
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
	account: AccountPreferences | None = Field(
		default=None,
		description="account / profile preferences",
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
	advanced: AdvancedPreferences | None = Field(
		default=None,
		description="advanced preferences",
	)
	debug: DebugPreferences | None = Field(
		default=None,
		description="debug preferences (admin-only)",
	)
	homepage: HomepagePreferences | None = Field(
		default=None,
		description="homepage suggestion preferences",
	)
