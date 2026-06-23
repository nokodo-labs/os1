"""user preferences schemas.

typed schema for user-level preferences stored as JSONB.
this provides validation and schema generation for the frontend.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from api.schemas.common import MISSING, MissingType


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


class _PreferencesSection(BaseModel):
	"""base schema for sparse preference sections."""

	model_config = ConfigDict(extra="forbid", populate_by_name=True)


# appearance preferences
class AppearancePreferences(_PreferencesSection):
	"""user appearance preferences."""

	theme_mode: Literal["light", "dark", "auto"] | MissingType = Field(
		default=MISSING,
		alias="themeMode",
		description="theme mode preference",
	)
	accent: (
		Literal["purple", "blue", "green", "orange", "pink", "red"] | MissingType
	) = Field(
		default=MISSING,
		description="accent color preference",
	)
	auto_accent_colors: bool | MissingType = Field(
		default=MISSING,
		alias="autoAccentColors",
		description="when enabled, accent colors change automatically based on context",
	)
	background: BackgroundType | MissingType = Field(
		default=MISSING,
		description="background wallpaper preference "
		"used when auto_background is disabled",
	)
	auto_background: bool | MissingType = Field(
		default=MISSING,
		alias="autoBackground",
		description="when enabled, background changes automatically based on context",
	)
	static_color: str | MissingType = Field(
		default=MISSING,
		alias="staticColor",
		description="hex color used when background is set to 'static'",
	)
	bubble_tail_style: Literal["none", "whatsapp", "imessage"] | MissingType = Field(
		default=MISSING,
		alias="bubbleTailStyle",
		description="chat bubble tail style preference",
	)
	bubble_animation: Literal["morph", "flyup", "none"] | MissingType = Field(
		default=MISSING,
		alias="bubbleAnimation",
		description="outgoing user message entrance animation",
	)


# account / profile preferences (stored alongside other prefs)
class AccountPreferences(_PreferencesSection):
	"""user account/profile preferences.

	profile data that doesn't warrant its own database column.
	"""

	bio: str | None | MissingType = Field(
		default=MISSING,
		description="personal bio visible to other users",
	)
	birth_date: str | None | MissingType = Field(
		default=MISSING,
		alias="birthDate",
		description="birth date in ISO 8601 format (YYYY-MM-DD)",
	)
	gender: str | None | MissingType = Field(
		default=MISSING,
		description="gender identity",
	)


# AI preferences
class AIPreferences(_PreferencesSection):
	"""user AI preferences."""

	default_agent_id: str | None | MissingType = Field(
		default=MISSING,
		alias="defaultAgentId",
		description="preferred default agent id",
	)
	bio: str | None | MissingType = Field(
		default=MISSING,
		description="AI-specific bio / about me for AI context",
	)
	use_account_bio: bool | MissingType = Field(
		default=MISSING,
		alias="useAccountBio",
		description="when true, use the account bio instead of a separate AI bio",
	)
	memories_enabled: bool | MissingType = Field(
		default=MISSING,
		alias="memoriesEnabled",
		description="whether AI memories are enabled",
	)
	chat_recall: bool | MissingType = Field(
		default=MISSING,
		alias="chatRecall",
		description="whether the AI can recall previous conversations",
	)
	custom_instructions: str | None | MissingType = Field(
		default=MISSING,
		alias="customInstructions",
		description="custom instructions for the AI to follow",
	)
	personality: str | None | MissingType = Field(
		default=MISSING,
		description="desired AI personality / tone description",
	)


# notification preferences
class NotificationPreferences(_PreferencesSection):
	"""user notification preferences."""

	enabled: bool | MissingType = Field(
		default=MISSING,
		description="whether notifications are enabled",
	)
	sound: bool | MissingType = Field(
		default=MISSING,
		description="whether notification sounds are enabled",
	)
	push_enabled: bool | MissingType = Field(
		default=MISSING,
		alias="pushEnabled",
		description="whether push notifications are enabled",
	)


# privacy preferences
class PrivacyPreferences(_PreferencesSection):
	"""user privacy preferences."""

	save_history: bool | MissingType = Field(
		default=MISSING,
		alias="saveHistory",
		description="whether to save chat history",
	)
	share_usage_data: bool | MissingType = Field(
		default=MISSING,
		alias="shareUsageData",
		description="whether to share anonymous usage data",
	)
	use_location: bool | MissingType = Field(
		default=MISSING,
		alias="useLocation",
		description="whether to send precise location to personalise AI responses",
	)
	use_device_context: bool | MissingType = Field(
		default=MISSING,
		alias="useDeviceContext",
		description=(
			"whether to send device information (timezone, OS, browser)"
			" to personalise AI responses"
		),
	)
	use_battery_status: bool | MissingType = Field(
		default=MISSING,
		alias="useBatteryStatus",
		description=(
			"whether to send battery status details to personalise AI responses"
		),
	)


# accessibility preferences
class AccessibilityPreferences(_PreferencesSection):
	"""user accessibility preferences."""

	haptic_feedback: bool | MissingType = Field(
		default=MISSING,
		alias="hapticFeedback",
		description="whether haptic feedback is enabled on compatible devices",
	)


# advanced preferences
class AdvancedPreferences(_PreferencesSection):
	"""user advanced preferences."""

	svg_liquid_glass: bool | MissingType = Field(
		default=MISSING,
		alias="svgLiquidGlass",
		description=(
			"whether to enable svg-based liquid glass when supported by the browser"
		),
	)
	svg_liquid_glass_island: bool | MissingType = Field(
		default=MISSING,
		alias="svgLiquidGlassIsland",
		description=(
			"whether to enable svg-based liquid glass "
			"specifically for the Island component"
		),
	)
	svg_liquid_metal: bool | MissingType = Field(
		default=MISSING,
		alias="svgLiquidMetal",
		description=(
			"whether to enable svg-based liquid metal effects "
			"when supported by the browser"
		),
	)


# debug preferences
class DebugPreferences(_PreferencesSection):
	"""user debug preferences (admin-only section)."""

	enable_debug_apps: bool | MissingType = Field(
		default=MISSING,
		alias="enableDebugApps",
		description="when enabled, placeholder/debug apps are shown on the home screen",
	)


# homepage preferences
class HomepagePreferences(_PreferencesSection):
	"""user homepage preferences

	controls which suggestion apps appear on the home screen."""

	chats: bool | MissingType = Field(
		default=MISSING,
		description="show chats in homepage suggestions",
	)
	reminders: bool | MissingType = Field(
		default=MISSING,
		description="show reminders in homepage suggestions",
	)
	notes: bool | MissingType = Field(
		default=MISSING,
		description="show notes in homepage suggestions",
	)
	projects: bool | MissingType = Field(
		default=MISSING,
		description="show projects in homepage suggestions",
	)
	friends: bool | MissingType = Field(
		default=MISSING,
		description="show friends in homepage suggestions",
	)
	library: bool | MissingType = Field(
		default=MISSING,
		description="show library in homepage suggestions",
	)
	calendar: bool | MissingType = Field(
		default=MISSING,
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

	appearance: AppearancePreferences | MissingType = Field(
		default=MISSING,
		description="appearance preferences",
	)
	account: AccountPreferences | MissingType = Field(
		default=MISSING,
		description="account / profile preferences",
	)
	ai: AIPreferences | MissingType = Field(
		default=MISSING,
		description="AI preferences",
	)
	notifications: NotificationPreferences | MissingType = Field(
		default=MISSING,
		description="notification preferences",
	)
	privacy: PrivacyPreferences | MissingType = Field(
		default=MISSING,
		description="privacy preferences",
	)
	accessibility: AccessibilityPreferences | MissingType = Field(
		default=MISSING,
		description="accessibility preferences",
	)
	advanced: AdvancedPreferences | MissingType = Field(
		default=MISSING,
		description="advanced preferences",
	)
	debug: DebugPreferences | MissingType = Field(
		default=MISSING,
		description="debug preferences (admin-only)",
	)
	homepage: HomepagePreferences | MissingType = Field(
		default=MISSING,
		description="homepage suggestion preferences",
	)
