"""application settings models and singleton."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Mapping
from enum import StrEnum
from functools import cache as functools_cache
from typing import Any, Final, Literal, Self, overload

from pydantic import (
	BaseModel,
	HttpUrl,
	computed_field,
	field_validator,
	model_validator,
)
from pydantic import (
	Field as PydanticField,
)
from pydantic.fields import FieldInfo
from pydantic_core import PydanticUndefined
from pydantic_settings import (
	BaseSettings,
	DotEnvSettingsSource,
	EnvSettingsSource,
	PydanticBaseSettingsSource,
	SettingsConfigDict,
)

from api.permissions import (
	ActionPermission,
	DefaultResourceAccess,
	strip_unknown_action_permissions,
)
from api.schemas.preferences import BackgroundType
from api.service.web_assets import (
	MEDIA_ASSETS,
	cdn_asset_url,
	resolve_asset_source,
)
from nokodo_ai.utils.typing import extract_literal_values


FieldFlag = Literal["public", "write_locked"]


_settings_logger = logging.getLogger(__name__)

ENV_PREFIX: Final[str] = "NOKODO__"
ENV_NESTED_DELIMITER: Final[str] = "__"
DEFAULT_SECRET_KEY: Final[str] = "dev-secret-key-change-me-in-production"
MINIMUM_SECRET_KEY_BYTES: Final[int] = 14
DEFAULT_API_PORT: Final[int] = 1383
DEFAULT_FRONTEND_PORT: Final[int] = 888
DEFAULT_CONSOLE_PORT: Final[int] = 8383
UNSAFE_SECRET_KEYS: Final[frozenset[str]] = frozenset(
	{
		DEFAULT_SECRET_KEY,
		"changeme",
		"your-secret-key-here-change-in-production",
	}
)


@overload
def settings_field[T](
	default: T,
	description: str | None = None,
	ge: int | float | None = None,
	le: int | float | None = None,
	min_length: int | None = None,
	max_length: int | None = None,
	examples: list[object] | None = None,
	json_schema_extra: dict[str, object] | None = None,
	default_factory: None = None,
	public: bool = False,
	write_locked: bool = False,
) -> T: ...


@overload
def settings_field[T](
	default: object = PydanticUndefined,
	description: str | None = None,
	ge: int | float | None = None,
	le: int | float | None = None,
	min_length: int | None = None,
	max_length: int | None = None,
	examples: list[object] | None = None,
	json_schema_extra: dict[str, object] | None = None,
	default_factory: Callable[[], T] = ...,
	public: bool = False,
	write_locked: bool = False,
) -> T: ...


def settings_field[T](
	default: T | object = PydanticUndefined,
	description: str | None = None,
	ge: int | float | None = None,
	le: int | float | None = None,
	min_length: int | None = None,
	max_length: int | None = None,
	examples: list[object] | None = None,
	json_schema_extra: dict[str, object] | None = None,
	default_factory: Callable[[], T] | None = None,
	public: bool = False,
	write_locked: bool = False,
) -> Any:
	"""field with access flags.
	args:
		public: if True, included in non-admin API responses
		write_locked: if True, cannot be updated via API (env-only)
	"""
	if default is not PydanticUndefined and default_factory is not None:
		raise TypeError("settings_field cannot use both default and default_factory")
	extra = dict(json_schema_extra or {})
	if public:
		extra["public"] = True
	if write_locked:
		extra["write_locked"] = True
	return PydanticField(
		default=default,
		default_factory=default_factory,
		description=description,
		ge=ge,
		le=le,
		min_length=min_length,
		max_length=max_length,
		examples=examples,
		json_schema_extra=extra or None,
		frozen=write_locked,
	)


def settings_computed_field(
	description: str | None = None,
	public: bool = False,
) -> Any:
	"""computed field with access flags."""
	extra: dict[str, object] = {}
	if public:
		extra["public"] = True
	return computed_field(
		description=description,
		json_schema_extra=extra or None,
	)


def get_field_flags(schema: type[BaseModel], field_name: str) -> dict[FieldFlag, bool]:
	"""get access flags for a field."""
	info = schema.model_fields.get(field_name)
	if not info:
		info = schema.model_computed_fields.get(field_name)
	if not info:
		return {}
	extra = info.json_schema_extra
	if not extra:
		return {}
	if callable(extra):
		return {}
	return {
		flag: bool(extra.get(flag))
		for flag in extract_literal_values(FieldFlag)
		if extra.get(flag)
	}


# section models


class UISettings(BaseModel):
	default_theme: str = settings_field(
		default="auto", public=True, description="'light', 'dark', or 'auto'"
	)
	default_background: BackgroundType = settings_field(
		default="darkveil",
		public=True,
		description="default background for the app",
	)
	auth_pages_background: BackgroundType = settings_field(
		default="lightrays",
		public=True,
		description="background for auth pages (login, signup)",
	)
	sidebar_collapsed: bool = settings_field(
		default=False, public=True, description="collapse sidebar"
	)


class AIMemorySettings(BaseModel):
	enable_memory: bool = settings_field(default=True, description="enable memory")
	similarity_threshold: float = settings_field(
		default=0.65,
		ge=0.0,
		le=1.0,
		description="similarity minimum threshold for memory retrieval. "
		"how similar a memory must be to be considered relevant. "
		"0.0 = all memories, 1.0 = exact match",
	)
	top_k: int = settings_field(
		default=15,
		ge=1,
		description="number of relevant memories to retrieve",
	)
	post_processing_turns: int = settings_field(
		default=6,
		ge=1,
		description="number of recent conversation turns fed to the dedicated "
		"memory maintenance agent that runs after each turn. a turn is a "
		"contiguous block of user or assistant messages.",
	)


class AIChatContextSettings(BaseModel):
	enabled: bool = settings_field(
		default=True,
		description="enable cross-chat context enrichment",
	)
	mode: Literal["recent", "relevant"] = settings_field(
		default="relevant",
		description="how chats are selected for Agent context enrichment. "
		"recent: top K by last_activity_at. "
		"relevant: top K by semantic similarity to the current conversation.",
	)
	top_k: int = settings_field(
		default=3,
		ge=1,
		description="number of chats to use for context enrichment",
	)
	similarity_threshold: float = settings_field(
		default=0.65,
		ge=0.0,
		le=1.0,
		description="similarity minimum threshold for chat context retrieval. "
		"how similar a chat must be to be considered relevant. "
		"0.0 = all chats, 1.0 = exact match",
	)


class AITaskSettings(BaseModel):
	"""per-task model overrides for background AI tasks.

	resolution order: per-task model_id -> default_model_id -> error.
	"""

	default_model_id: str | None = settings_field(
		default=None,
		description="fallback model id for all background tasks",
	)
	thread_metadata_model_id: str | None = settings_field(
		default=None,
		description="model for thread metadata generation (title, tags)",
	)
	thread_maintenance_model_id: str | None = settings_field(
		default=None,
		description="model for inactive thread metadata and summary maintenance",
	)
	input_autocomplete_model_id: str | None = settings_field(
		default=None,
		description="model for input autocomplete suggestions",
	)
	summarization_model_id: str | None = settings_field(
		default=None,
		description="model for thread context summarization",
	)
	memory_post_processing_model_id: str | None = settings_field(
		default=None,
		description="model for memory post-processing (dedup, update, delete)",
	)
	web_search_model_id: str | None = settings_field(
		default=None,
		description="model for native agentic web search",
	)
	asset_description_model_id: str | None = settings_field(
		default=None,
		description="model for asset summaries and non-text descriptions",
	)
	asset_text_extraction_model_id: str | None = settings_field(
		default=None,
		description="model for asset file, document, and media text extraction",
	)
	maintenance_max_chars_per_message: int | None = settings_field(
		default=2000,
		ge=1,
		description=(
			"max characters per message in thread maintenance transcripts. "
			"null for unlimited"
		),
	)


class AIAttachmentSettings(BaseModel):
	"""protection windows for native media fetched onto tool messages.

	native media only ever lives on tool messages (file_get fetches and
	media generators). two tiers govern its lifetime, both measured in
	iterations (one agent-loop restart within a single agent turn, i.e. one
	per assistant message):

	- hard window (always one iteration): the read iteration where the model
	first sees the fresh bytes. media here is the output the model is reading
	right now; compaction never cuts it. if the hard set alone busts budget,
	compaction throws clearly.
	- soft window (these settings): media stays native and hydrated for the
	configured iterations within the same agent turn, but is NOT protected
	from compaction. under budget pressure compaction may drop soft media (it
	is recoverable via file_get), so the soft window can be cut short down to
	the read iteration.
	"""

	image_decay_iterations: int = settings_field(
		default=3,
		ge=1,
		description="soft protection iterations for fetched image media",
	)
	audio_decay_iterations: int = settings_field(
		default=3,
		ge=1,
		description="soft protection iterations for fetched audio media",
	)
	video_decay_iterations: int = settings_field(
		default=1,
		ge=1,
		description="soft protection iterations for fetched video media (token-heavy)",
	)


class AIContextCompactionSettings(BaseModel):
	"""context compaction settings.

	controls token-aware compaction, summarization triggers, tool result
	truncation, and recursive summary condensation. all budget decisions
	are based on estimated token weight, not naive message counts.
	"""

	enabled: bool = settings_field(
		default=True,
		description=(
			"enable token-aware context compaction before chat generation. when "
			"enabled, the system preserves all messages that fit, compacts older "
			"tool output and summarized spans when needed, and can schedule "
			"background summaries for future runs"
		),
	)
	trigger_ratio: float = settings_field(
		default=0.70,
		ge=0.1,
		le=0.95,
		description=(
			"prompt pressure ratio that triggers background summarization while "
			"the full raw conversation still fits. lower values create summaries "
			"earlier and reduce future latency; higher values defer work until the "
			"thread is closer to the model budget"
		),
	)
	recovery_target_ratio: float = settings_field(
		default=0.55,
		ge=0.05,
		le=0.90,
		description=(
			"target prompt pressure after a summarization recovery pass. must be "
			"lower than trigger_ratio so compaction has hysteresis and does not "
			"immediately re-trigger after creating a summary"
		),
	)
	target_usage_cap_tokens: int | None = settings_field(
		default=None,
		ge=1,
		description=(
			"optional maximum context budget used for compaction before response "
			"reserve and prompt overhead are subtracted. set this below a model's "
			"advertised window to leave extra provider safety margin or to force "
			"smaller prompts during testing"
		),
	)
	summary_batch_min_tokens: int = settings_field(
		default=512,
		ge=1,
		description=(
			"minimum raw token span to include in a single summary job. prevents "
			"tiny summaries whose marker and metadata would cost more than the "
			"messages they replace"
		),
	)
	summary_batch_max_tokens: int = settings_field(
		default=16000,
		ge=1,
		description=(
			"maximum raw token span to send to one summary job. caps summary "
			"prompt size so very long threads are summarized in bounded batches "
			"instead of one large provider request"
		),
	)
	prompt_overhead_tokens: int = settings_field(
		default=300,
		ge=0,
		description=(
			"tokens reserved for provider framing, system wrappers, schema/tool "
			"instructions, and other prompt bytes that are not represented by "
			"stored chat messages. increasing this makes compaction more cautious"
		),
	)
	blocking_summarization_enabled: bool = settings_field(
		default=True,
		description=(
			"allow a last-resort inline summary during the user request when tool "
			"compaction and ready summaries cannot fit the prompt. disabling this "
			"avoids extra latency but may force older messages to be pruned sooner"
		),
	)
	blocking_summarization_timeout_seconds: float = settings_field(
		default=20.0,
		ge=1.0,
		le=120.0,
		description=(
			"maximum time to wait for an inline last-resort summary before giving "
			"up and trying the next compaction tier. this bounds user-visible "
			"latency when a provider is slow or rejects the summary request"
		),
	)
	tool_result_max_share: float = settings_field(
		default=0.25,
		ge=0.05,
		le=0.75,
		description=(
			"maximum fraction of the available prompt budget that one tool result "
			"may consume before it is compacted. lower values keep large search, "
			"file, or code outputs from crowding out conversational context"
		),
	)
	tool_result_hard_cap: int = settings_field(
		default=100_000,
		ge=1000,
		description=(
			"absolute character ceiling for a single tool result before token "
			"estimation. this protects the compaction pipeline from extremely "
			"large raw outputs even when the token budget is configured generously"
		),
	)
	tool_results_combined_max_share: float = settings_field(
		default=0.50,
		ge=0.10,
		le=0.95,
		description=(
			"maximum fraction of the available prompt budget that all tool "
			"results combined may consume. when the combined total exceeds this, "
			"older tool results are compacted first so tool-heavy runs do not "
			"displace the rest of the conversation"
		),
	)
	response_headroom: int = settings_field(
		default=4096,
		ge=256,
		description=(
			"tokens reserved for the assistant response after prompt compaction. "
			"larger values reduce prompt capacity but lower the chance that a "
			"provider stops because there is too little room left to answer"
		),
	)
	summarization_max_chars_per_message: int | None = settings_field(
		default=2000,
		ge=1,
		description=(
			"maximum characters copied from each raw message into a summary "
			"transcript. this limits single-message outliers before they reach "
			"the summarization model; null keeps full message text"
		),
	)

	@model_validator(mode="after")
	def validate_thresholds(self) -> Self:
		"""ensure proactive recovery has hysteresis."""
		if self.recovery_target_ratio >= self.trigger_ratio:
			raise ValueError("recovery_target_ratio must be less than trigger_ratio")
		if self.summary_batch_min_tokens > self.summary_batch_max_tokens:
			raise ValueError(
				"summary_batch_min_tokens must be less than or equal to "
				"summary_batch_max_tokens"
			)
		return self


class E2bSettings(BaseModel):
	"""E2B code interpreter sandbox settings."""

	api_key: str | None = settings_field(
		default=None,
		description="E2B API key for code execution",
	)
	template: str = settings_field(
		default="code-interpreter-v1",
		description="E2B sandbox template to use for code execution",
	)
	available_packages: list[str] = settings_field(
		default_factory=list,
		description="pre-installed Python packages available in the sandbox",
	)


CodeInterpreterEngine = Literal["native", "e2b"]


class CodeInterpreterSettings(BaseModel):
	"""code interpreter (sandbox) configuration."""

	enabled: bool = settings_field(
		default=True,
		description="enable code interpreter capabilities",
	)
	engine: CodeInterpreterEngine = settings_field(
		default="e2b",
		description="sandbox engine to use",
	)
	e2b: E2bSettings = settings_field(
		default_factory=E2bSettings,
		description="E2B sandbox settings",
	)
	timeout: int = settings_field(
		default=60,
		ge=5,
		description="execution timeout in seconds",
	)
	max_file_download_mb: int = settings_field(
		default=10,
		ge=1,
		description="max file size downloadable from sandbox in MB",
	)
	max_output_chars: int = settings_field(
		default=500_000,
		ge=1000,
		description="max output characters returned from code interpreter",
	)
	truncation_lines: int = settings_field(
		default=50,
		ge=5,
		description="lines kept at head and tail when truncating output",
	)


AssetContentLoader = Literal["auto", "plain", "markitdown", "chatmodel"]
AssetChunkingAlgorithm = Literal["auto", "recursive", "markdown", "semantic"]


class AssetContentVectorizationSettings(BaseModel):
	"""asset content vectorization resource limits."""

	loader: AssetContentLoader = settings_field(
		default="auto",
		description="asset content text loader",
	)
	chunking_algorithm: AssetChunkingAlgorithm = settings_field(
		default="auto",
		description="asset content chunking algorithm",
	)
	max_bytes: int | None = settings_field(
		default=5 * 1024 * 1024,
		ge=1,
		description="maximum bytes read from an asset; null means unlimited",
	)
	target_tokens: int = settings_field(
		default=700,
		ge=50,
		description="target token count per asset content chunk",
	)
	overlap_tokens: int = settings_field(
		default=80,
		ge=0,
		description="token overlap between adjacent asset content chunks",
	)
	max_chunks: int | None = settings_field(
		default=200,
		ge=1,
		description="maximum content chunks per asset; null means unlimited",
	)
	semantic_breakpoint_percentile: float = settings_field(
		default=95.0,
		ge=50.0,
		le=100.0,
		description="percentile threshold for semantic breakpoint detection",
	)
	semantic_min_sentences: int = settings_field(
		default=2,
		ge=1,
		description="minimum sentences per semantic chunk before merging",
	)
	semantic_buffer_size: int = settings_field(
		default=1,
		ge=0,
		description=(
			"neighbor sentence window size used when embedding for semantic splitting"
		),
	)


class AssetDescriptionSettings(BaseModel):
	"""asset description and summary limits."""

	max_input_chars: int | None = settings_field(
		default=24_000,
		ge=100,
		description=(
			"maximum extracted text characters sent to the description model; "
			"null means unlimited"
		),
	)
	max_chars: int | None = settings_field(
		default=1200,
		ge=50,
		description="maximum stored asset description characters; null means unlimited",
	)


class ImageGenerationSettings(BaseModel):
	"""image generation engine configuration."""

	enabled: bool = settings_field(
		default=True,
		description="enable image generation capabilities",
	)
	model: str | None = settings_field(
		default=None,
		description="model ID referencing a Model ORM record with IMAGE type",
	)
	default_size: str = settings_field(
		default="1024x1024",
		description="default image size in WIDTHxHEIGHT format",
	)
	default_steps: int | None = settings_field(
		default=None,
		ge=1,
		description=("default number of generation steps (if supported by the engine)"),
	)
	default_n: int = settings_field(
		default=1,
		ge=1,
		le=10,
		description="default number of images to generate per prompt",
	)
	max_n: int = settings_field(
		default=4,
		ge=1,
		le=10,
		description="maximum number of images per request",
	)


class VideoGenerationSettings(BaseModel):
	"""video generation engine configuration (scaffold)."""

	enabled: bool = settings_field(
		default=False,
		description="enable video generation capabilities",
	)
	model: str | None = settings_field(
		default=None,
		description="model ID referencing a Model ORM record with VIDEO type",
	)


class AudioGenerationSettings(BaseModel):
	"""audio generation engine configuration (scaffold)."""

	enabled: bool = settings_field(
		default=False,
		description="enable audio generation capabilities",
	)
	model: str | None = settings_field(
		default=None,
		description="model ID referencing a Model ORM record with AUDIO type",
	)


class AIMediaSettings(BaseModel):
	"""AI media generation settings."""

	images: ImageGenerationSettings = settings_field(
		default_factory=ImageGenerationSettings,
		description="image generation settings",
	)
	videos: VideoGenerationSettings = settings_field(
		default_factory=VideoGenerationSettings,
		description="video generation settings (future)",
	)
	audio: AudioGenerationSettings = settings_field(
		default_factory=AudioGenerationSettings,
		description="audio generation settings (future)",
	)


class AISettings(BaseModel):
	default_agent_ids: list[str] = settings_field(
		default_factory=list,
		public=True,
		description="ordered list of default agent ids (tried in order)",
	)
	retrieval_turns: int = settings_field(
		default=3,
		ge=1,
		description="number of recent conversation turns to use when building "
		"retrieval queries for memory and chat context enrichment. "
		"a turn is a contiguous block of user or assistant messages.",
	)
	retrieval_pre_build: bool = settings_field(
		default=True,
		description="pre-build the retrieval query (text + embedding) in agents.py "
		"before the filter loop. when disabled each filter builds its own query, "
		"which avoids the upfront embed cost if no retrieval filter is active.",
	)
	memory: AIMemorySettings = settings_field(
		default_factory=AIMemorySettings,
		description="AI memory settings",
	)
	chat_context: AIChatContextSettings = settings_field(
		default_factory=AIChatContextSettings,
		description="chat context settings",
	)
	tasks: AITaskSettings = settings_field(
		default_factory=AITaskSettings,
		description="background task model settings",
	)
	attachments: AIAttachmentSettings = settings_field(
		default_factory=AIAttachmentSettings,
		description="native attachment decay settings",
	)
	context_compaction: AIContextCompactionSettings = settings_field(
		default_factory=AIContextCompactionSettings,
		description="context compaction and summarization settings",
	)
	media: AIMediaSettings = settings_field(
		default_factory=AIMediaSettings,
		description="AI media generation settings",
	)


AssetSource = Literal["default", "cdn", "custom"]
OptionalAssetSource = Literal["default", "cdn", "custom", "disabled"]


class ManifestAssetSettings(BaseModel):
	"""source control for one optional generated manifest asset."""

	source: OptionalAssetSource = settings_field(
		default="default",
		public=True,
		description="asset source: default, cdn, custom, or disabled",
	)
	url: HttpUrl | None = settings_field(
		default=None,
		public=True,
		description="custom asset url override",
	)


class MediaAssetSettings(BaseModel):
	"""source control for one frontend media asset."""

	source: AssetSource = settings_field(
		default="default",
		public=True,
		description="asset source: default, cdn, or custom",
	)
	url: HttpUrl | None = settings_field(
		default=None,
		public=True,
		description="custom asset url override",
	)


class PwaManifestAssetsSettings(BaseModel):
	"""per-file asset source controls for the generated PWA manifest."""

	icon_1024_maskable: ManifestAssetSettings = settings_field(
		default_factory=ManifestAssetSettings,
		description="1024x1024 maskable app icon",
	)
	icon_512_any: ManifestAssetSettings = settings_field(
		default_factory=ManifestAssetSettings,
		description="512x512 any-purpose app icon",
	)
	shortcut_notes: ManifestAssetSettings = settings_field(
		default_factory=ManifestAssetSettings,
		description="notes shortcut icon",
	)
	shortcut_reminders: ManifestAssetSettings = settings_field(
		default_factory=ManifestAssetSettings,
		description="reminders shortcut icon",
	)
	shortcut_calendar: ManifestAssetSettings = settings_field(
		default_factory=ManifestAssetSettings,
		description="calendar shortcut icon",
	)
	shortcut_messages: ManifestAssetSettings = settings_field(
		default_factory=ManifestAssetSettings,
		description="messages shortcut icon",
	)
	shortcut_projects: ManifestAssetSettings = settings_field(
		default_factory=ManifestAssetSettings,
		description="projects shortcut icon",
	)
	shortcut_library: ManifestAssetSettings = settings_field(
		default_factory=ManifestAssetSettings,
		description="files shortcut icon",
	)
	shortcut_social: ManifestAssetSettings = settings_field(
		default_factory=ManifestAssetSettings,
		description="social shortcut icon",
	)
	shortcut_settings: ManifestAssetSettings = settings_field(
		default_factory=ManifestAssetSettings,
		description="settings shortcut icon",
	)
	screenshot_narrow_1: ManifestAssetSettings = settings_field(
		default_factory=ManifestAssetSettings,
		description="narrow screenshot 1",
	)
	screenshot_narrow_2: ManifestAssetSettings = settings_field(
		default_factory=ManifestAssetSettings,
		description="narrow screenshot 2",
	)
	screenshot_narrow_3: ManifestAssetSettings = settings_field(
		default_factory=ManifestAssetSettings,
		description="narrow screenshot 3",
	)
	screenshot_narrow_4: ManifestAssetSettings = settings_field(
		default_factory=ManifestAssetSettings,
		description="narrow screenshot 4",
	)
	screenshot_narrow_5: ManifestAssetSettings = settings_field(
		default_factory=ManifestAssetSettings,
		description="narrow screenshot 5",
	)
	screenshot_wide_1: ManifestAssetSettings = settings_field(
		default_factory=ManifestAssetSettings,
		description="wide screenshot 1",
	)
	screenshot_wide_2: ManifestAssetSettings = settings_field(
		default_factory=ManifestAssetSettings,
		description="wide screenshot 2",
	)
	screenshot_wide_3: ManifestAssetSettings = settings_field(
		default_factory=ManifestAssetSettings,
		description="wide screenshot 3",
	)
	screenshot_wide_4: ManifestAssetSettings = settings_field(
		default_factory=ManifestAssetSettings,
		description="wide screenshot 4",
	)
	screenshot_wide_5: ManifestAssetSettings = settings_field(
		default_factory=ManifestAssetSettings,
		description="wide screenshot 5",
	)
	screenshot_wide_6: ManifestAssetSettings = settings_field(
		default_factory=ManifestAssetSettings,
		description="wide screenshot 6",
	)
	screenshot_wide_7: ManifestAssetSettings = settings_field(
		default_factory=ManifestAssetSettings,
		description="wide screenshot 7",
	)
	screenshot_wide_8: ManifestAssetSettings = settings_field(
		default_factory=ManifestAssetSettings,
		description="wide screenshot 8",
	)


class BrandingSettings(BaseModel):
	site_name: str = settings_field(default="OS1", public=True, description="site name")
	app_version: str = settings_field(
		default="0.1.0",
		public=True,
		write_locked=True,
		description="backend version",
	)
	logo_url: HttpUrl | None = settings_field(
		default=None, public=True, description="logo url"
	)
	favicon_url: HttpUrl | None = settings_field(
		default=None, public=True, description="favicon url"
	)
	primary_color: str = settings_field(
		default="#6366f1", public=True, description="primary color hex"
	)
	support_email: str | None = settings_field(
		default=None,
		public=True,
		description="support email shown to users awaiting approval",
	)
	admin_email: str | None = settings_field(
		default=None,
		public=True,
		description="admin email for internal / escalation contact",
	)
	public_frontend_origin: HttpUrl | None = settings_field(
		default=None,
		public=True,
		description="public frontend origin",
	)
	public_cdn_origin: HttpUrl | None = settings_field(
		default=None,
		public=True,
		description="public cdn origin",
	)
	public_console_origin: HttpUrl | None = settings_field(
		default=None,
		public=True,
		description="public admin console origin",
	)
	pwa_manifest_url: HttpUrl | None = settings_field(
		default=None,
		public=True,
		description="external pwa manifest.json url",
	)
	analytics_key: str | None = settings_field(
		default=None,
		write_locked=True,
		description="analytics key (env-only)",
	)
	pwa_assets: PwaManifestAssetsSettings = settings_field(
		default_factory=PwaManifestAssetsSettings,
		description="PWA manifest asset source controls",
	)


class LimitsSettings(BaseModel):
	max_threads_per_user: int = settings_field(
		default=100, ge=1, description="max threads per user"
	)
	max_messages_per_thread: int = settings_field(
		default=1000, ge=1, description="max messages per thread"
	)
	max_chat_input_chars: int | None = settings_field(
		default=200_000,
		ge=1,
		public=True,
		description="max characters accepted in chat input. null disables the cap",
	)
	max_file_size_mb: int = settings_field(
		default=50, ge=1, description="max file size mb"
	)
	max_reminder_hierarchy_depth: int = settings_field(
		default=8,
		ge=1,
		description="maximum nesting depth for sub-reminders",
	)
	max_scheduled_items_window_days: int = settings_field(
		default=366,
		ge=1,
		description="maximum time window in days for scheduled items queries",
	)
	rate_limit_requests_per_minute: int = settings_field(
		default=1500, ge=1, description="rate limit/min"
	)


class MediaSettings(BaseModel):
	"""frontend media asset source controls.

	resolution order per asset is controlled by its source field:
	the asset url field is an explicit override, cdn uses
	branding.public_cdn_origin when configured, and default uses
	nokodo-hosted defaults.
	"""

	favicon: MediaAssetSettings = settings_field(
		default_factory=MediaAssetSettings,
		description="browser tab favicon",
	)
	apple_touch_icon: MediaAssetSettings = settings_field(
		default_factory=MediaAssetSettings,
		description="iOS home screen icon",
	)
	sidebar_logo: MediaAssetSettings = settings_field(
		default_factory=MediaAssetSettings,
		description="sidebar logo",
	)
	splash_logo: MediaAssetSettings = settings_field(
		default_factory=MediaAssetSettings,
		description="splash screen logo",
	)


class VectorSettings(BaseModel):
	"""vector database collection and search tuning."""

	collection_template: str = settings_field(
		default="nokodo-ai__{model}_bm25",
		description="collection name template. '{model}' is replaced with "
		"the slugified embedding model name at runtime",
	)
	sparse_vectors_enabled: bool = settings_field(
		default=True,
		description="enable BM25 sparse vectors for hybrid search",
	)
	fusion_algorithm: Literal["rrf", "dbsf"] = settings_field(
		default="rrf",
		description="score fusion algorithm: rrf (reciprocal rank fusion) or "
		"dbsf (distribution-based score fusion)",
	)
	normalize_scores: bool = settings_field(
		default=True,
		description="normalize fused scores to 0-1 range",
	)


class EmbeddingsSettings(BaseModel):
	"""embedding model configuration."""

	vector_size: int = settings_field(
		default=1536,
		ge=1,
		description="default vector dimension for the embedding model",
	)
	batch_size: int = settings_field(
		default=64,
		ge=1,
		le=4096,
		description="batch size for embedding generation during vectorization",
	)
	max_concurrency: int | None = settings_field(
		default=100,
		ge=1,
		description=(
			"max embedding batches sent concurrently during vectorization; "
			"null means unbounded (all batches at once)"
		),
	)


class RerankSettings(BaseModel):
	"""default reranking behavior."""

	default_strategy: str = settings_field(
		default="native",
		description="default reranking strategy: none, native, or external",
	)
	top_k: int = settings_field(
		default=10,
		ge=1,
		le=100,
		description="number of results to keep after reranking",
	)


class VectorDatabaseProvider(StrEnum):
	"""supported vector database providers."""

	QDRANT = "qdrant"
	CHROMA = "chroma"
	PINECONE = "pinecone"
	WEAVIATE = "weaviate"
	MILVUS = "milvus"
	PGVECTOR = "pgvector"
	REDIS = "redis"
	OPENSEARCH = "opensearch"


class QdrantVectorDatabaseSettings(BaseModel):
	"""qdrant provider settings."""

	url: str = settings_field(
		default="qdrant:6334",
		description="qdrant endpoint. host:port targets gRPC when use_grpc is enabled",
	)
	use_grpc: bool = settings_field(
		default=True,
		description="use qdrant gRPC transport when available",
	)
	api_key: str | None = settings_field(
		default=None,
		description="api key for qdrant",
	)


class ChromaVectorDatabaseSettings(BaseModel):
	"""chroma provider settings stub."""

	url: str | None = settings_field(default=None, description="chroma endpoint url")
	api_key: str | None = settings_field(
		default=None,
		description="api key for chroma",
	)


class PineconeVectorDatabaseSettings(BaseModel):
	"""pinecone provider settings stub."""

	url: str | None = settings_field(default=None, description="pinecone endpoint url")
	api_key: str | None = settings_field(
		default=None,
		description="api key for pinecone",
	)


class WeaviateVectorDatabaseSettings(BaseModel):
	"""weaviate provider settings stub."""

	url: str | None = settings_field(default=None, description="weaviate endpoint url")
	api_key: str | None = settings_field(
		default=None,
		description="api key for weaviate",
	)


class MilvusVectorDatabaseSettings(BaseModel):
	"""milvus provider settings stub."""

	url: str | None = settings_field(default=None, description="milvus endpoint url")
	token: str | None = settings_field(
		default=None,
		description="token for milvus",
	)


class PgvectorVectorDatabaseSettings(BaseModel):
	"""pgvector provider settings stub."""

	url: str | None = settings_field(
		default=None, description="pgvector connection url"
	)


class RedisVectorDatabaseSettings(BaseModel):
	"""redis provider settings stub."""

	url: str | None = settings_field(default=None, description="redis endpoint url")
	password: str | None = settings_field(
		default=None,
		description="password for redis",
	)


class OpensearchVectorDatabaseSettings(BaseModel):
	"""opensearch provider settings stub."""

	url: str | None = settings_field(
		default=None, description="opensearch endpoint url"
	)
	api_key: str | None = settings_field(
		default=None,
		description="api key for opensearch",
	)


class VectorDatabaseSettings(BaseModel):
	"""vector database connection settings."""

	provider: VectorDatabaseProvider = settings_field(
		default=VectorDatabaseProvider.QDRANT,
		description="vector database provider",
	)
	qdrant: QdrantVectorDatabaseSettings = settings_field(
		default_factory=QdrantVectorDatabaseSettings,
		description="qdrant provider settings",
	)
	chroma: ChromaVectorDatabaseSettings = settings_field(
		default_factory=ChromaVectorDatabaseSettings,
		description="chroma provider settings stub",
	)
	pinecone: PineconeVectorDatabaseSettings = settings_field(
		default_factory=PineconeVectorDatabaseSettings,
		description="pinecone provider settings stub",
	)
	weaviate: WeaviateVectorDatabaseSettings = settings_field(
		default_factory=WeaviateVectorDatabaseSettings,
		description="weaviate provider settings stub",
	)
	milvus: MilvusVectorDatabaseSettings = settings_field(
		default_factory=MilvusVectorDatabaseSettings,
		description="milvus provider settings stub",
	)
	pgvector: PgvectorVectorDatabaseSettings = settings_field(
		default_factory=PgvectorVectorDatabaseSettings,
		description="pgvector provider settings stub",
	)
	redis: RedisVectorDatabaseSettings = settings_field(
		default_factory=RedisVectorDatabaseSettings,
		description="redis provider settings stub",
	)
	opensearch: OpensearchVectorDatabaseSettings = settings_field(
		default_factory=OpensearchVectorDatabaseSettings,
		description="opensearch provider settings stub",
	)


class LocalStorageConfig(BaseModel):
	"""local filesystem storage configuration."""

	root_path: str = settings_field(
		default="data/uploads",
		description="root directory for local file storage",
	)


class S3StorageConfig(BaseModel):
	"""S3-compatible storage configuration.

	defaults target the dev MinIO container from the compose stack.
	for production, override via environment variables or DB settings.
	"""

	endpoint_url: str | None = settings_field(
		default="http://localhost:9000",
		description="S3-compatible endpoint (MinIO, R2, etc.). set to None for AWS S3.",
	)
	bucket: str = settings_field(
		default="nokodo-ai",
		description="S3 bucket name. must be globally unique per deployment.",
	)
	region: str = settings_field(default="us-east-1", description="AWS region")
	access_key_id: str | None = settings_field(
		default="minioadmin", description="S3 access key id"
	)
	secret_access_key: str | None = settings_field(
		default="minioadmin", description="S3 secret access key"
	)
	prefix: str = settings_field(default="", description="key prefix within the bucket")
	presigned_url_ttl: int = settings_field(
		default=3600, description="presigned URL expiration in seconds"
	)
	multipart_threshold: int = settings_field(
		default=100 * 1024 * 1024,
		description="bytes above which multipart upload kicks in",
	)
	multipart_chunk_size: int = settings_field(
		default=10 * 1024 * 1024,
		description="multipart upload chunk size in bytes",
	)
	max_retries: int = settings_field(default=3, description="max retry attempts")
	retry_mode: Literal["legacy", "standard", "adaptive"] = settings_field(
		default="adaptive", description="botocore retry mode"
	)


class StorageSettings(BaseModel):
	"""file storage backend configuration.

	set `backend` to choose which storage system is active.
	only the selected backend is instantiated at startup.
	"""

	backend: Literal["local", "s3"] = settings_field(
		default="local",
		description="active storage backend: 'local' or 's3'",
	)
	local: LocalStorageConfig = settings_field(default_factory=LocalStorageConfig)
	s3: S3StorageConfig = settings_field(default_factory=S3StorageConfig)


class AssetsSettings(BaseModel):
	default_embedding_model_id: str | None = settings_field(
		default=None,
		description="default embedding model id (Model.id)",
	)
	vector_database: VectorDatabaseSettings = settings_field(
		default_factory=VectorDatabaseSettings,
		description="vector database provider and connection settings",
	)
	vector: VectorSettings = settings_field(
		default_factory=VectorSettings,
		description="vector database collection and search tuning",
	)
	embeddings: EmbeddingsSettings = settings_field(
		default_factory=EmbeddingsSettings,
		description="embedding model configuration",
	)
	rerank: RerankSettings = settings_field(
		default_factory=RerankSettings,
		description="default reranking behavior",
	)
	storage: StorageSettings = settings_field(
		default_factory=StorageSettings,
		description="file storage backend configuration",
	)
	content_vectorization: AssetContentVectorizationSettings = settings_field(
		default_factory=AssetContentVectorizationSettings,
		description="asset content vectorization resource limits",
	)
	descriptions: AssetDescriptionSettings = settings_field(
		default_factory=AssetDescriptionSettings,
		description="asset description and summary limits",
	)


class OIDCSettings(BaseModel):
	"""openid connect provider configuration."""

	enabled: bool = settings_field(
		default=False,
		description="enable oidc authentication",
	)
	issuer_url: HttpUrl | None = settings_field(
		default=None,
		description="oidc issuer url",
	)
	client_id: str | None = settings_field(
		default=None,
		description="oidc client id",
	)
	client_secret: str | None = settings_field(
		default=None,
		description="oidc client secret",
	)
	redirect_uri: HttpUrl | None = settings_field(
		default=None,
		description="oidc redirect uri",
	)
	scopes: list[str] = settings_field(
		default_factory=lambda: ["openid", "profile", "email"],
		description="oidc scopes",
	)
	only: bool = settings_field(
		default=False,
		public=True,
		description="only allow login via oidc (disables password login)",
	)

	def is_configured(self) -> bool:
		"""check whether all required oidc fields are set."""
		return bool(
			self.issuer_url
			and self.client_id
			and self.client_secret
			and self.redirect_uri
		)

	@model_validator(mode="after")
	def validate_oidc_flags(self) -> OIDCSettings:
		if self.only and not self.enabled:
			raise ValueError("oidc.only requires oidc.enabled")
		if self.only and not self.is_configured():
			raise ValueError("oidc.only requires oidc provider configuration")
		if self.enabled and not self.is_configured():
			raise ValueError(
				"oidc.enabled requires issuer_url, client_id, client_secret, "
				"and redirect_uri"
			)
		return self


class SecuritySettings(BaseModel):
	secret_key: str = settings_field(
		default=DEFAULT_SECRET_KEY,
		write_locked=True,
		description="application secret key (env-only)",
	)

	@settings_computed_field(
		description="whether the application secret key is still a built-in default.",
	)
	@property
	def secret_key_uses_default(self) -> bool:
		return self.secret_key.strip() in UNSAFE_SECRET_KEYS

	previous_secret_keys: list[str] = settings_field(
		[],
		write_locked=True,
		description=(
			"previous secret keys for decryption fallback "
			"during key rotation (env-only). "
			"set as comma-separated string or JSON array."
		),
	)
	allow_signups: bool = settings_field(
		default=True,
		public=True,
		description="allow new user signups",
	)
	auto_signup_role_ids: list[str] | None = settings_field(
		default=None,
		description="role ids auto-applied to new signups",
	)
	jwt_algorithm: str = settings_field(
		default="HS256",
		write_locked=True,
		description="jwt algorithm",
	)
	access_token_expire_minutes: int = settings_field(
		default=30,
		ge=1,
		description="access token expire minutes",
	)
	refresh_token_expire_days: int = settings_field(
		default=90,
		ge=1,
		description="refresh token expire days",
	)
	auth_cookie_secure: bool = settings_field(
		default=True,
		description="set secure cookies",
	)
	session_timeout_minutes: int = settings_field(
		default=30,
		ge=5,
		description="session timeout",
	)
	require_email_verification: bool = settings_field(
		default=True,
		description="require email verification",
	)
	allowed_email_domains: list[str] = settings_field(
		default_factory=list,
		description="allowed domains",
	)
	oidc: OIDCSettings = settings_field(
		default_factory=OIDCSettings,
		description="openid connect provider settings",
	)
	enable_oauth: bool = settings_field(
		default=True,
		write_locked=True,
		description="enable oauth (env-only)",
	)
	cors_origins: list[str] = settings_field(
		default=[
			f"http://localhost:{DEFAULT_FRONTEND_PORT}",
			f"http://localhost:{DEFAULT_CONSOLE_PORT}",
		],
		write_locked=True,
		description="cors origins (env-only)",
	)
	cors_origins_regex: list[str] = settings_field(
		default=[r"^https?://.*\.local:888$", r"^https?://.*\.local:8383$"],
		write_locked=True,
		description="cors origins regex patterns (env-only). set as JSON array object.",
	)
	allowed_hosts: list[str] = settings_field(
		default=[
			"localhost",
			"0.0.0.0",
			"127.0.0.1",
			".local",
		],
		write_locked=True,
		description=(
			"allowed host patterns for Origin validation (env-only). "
			"supports '*', leading-dot domains like '.local', and exact hostnames"
		),
	)

	@field_validator(
		"cors_origins",
		"allowed_hosts",
		"previous_secret_keys",
		mode="before",
	)
	@classmethod
	def parse_comma_separated_strings(cls, v: str | list[str]) -> list[str]:
		if isinstance(v, str):
			return [item.strip() for item in v.split(",") if item.strip()]
		return v


class SearxngSettings(BaseModel):
	"""searxng-specific settings for web search."""

	instance_url: HttpUrl = settings_field(
		default=HttpUrl("http://searxng:8080"),
		description="base url for the searxng instance",
	)
	max_results: int = settings_field(
		default=20,
		description="max results to return from searxng",
		ge=1,
	)
	max_concurrent_requests: int = settings_field(
		default=5,
		description="max concurrent requests to searxng (queue excess)",
		ge=1,
	)
	timeout_seconds: int = settings_field(
		default=10,
		ge=1,
		description="timeout for searxng API calls in seconds",
	)


class TavilySettings(BaseModel):
	"""tavily-specific settings for web loading."""

	extract_depth: Literal["basic", "advanced"] = settings_field(
		default="advanced",
		description=("depth of content extraction for tavily web loader."),
	)
	api_key: str | None = settings_field(
		default=None,
		description="api key for tavily web loader",
	)
	max_concurrent_requests: int = settings_field(
		default=10,
		description="max concurrent requests to tavily (queue excess)",
		ge=1,
	)


class WebLoaderSettings(BaseModel):
	"""web loader configuration for fetching and processing web content."""

	engine: Literal["native", "tavily", "playwright"] = settings_field(
		default="native",
		description="web loader engine to use",
	)
	timeout_seconds: int = settings_field(
		default=10,
		ge=1,
		description="timeout for web loader fetch operations in seconds",
	)
	user_agent: str = settings_field(
		default="Mozilla/5.0 (compatible; NokodoAI/1.0; +https://nokodo.ai)",
		description="user agent string for web loader requests",
	)
	max_chars: int = settings_field(
		default=50_000,
		ge=100,
		description="maximum characters returned per fetched URL",
	)
	tavily: TavilySettings = settings_field(
		default_factory=TavilySettings,
		description="tavily-specific settings for web loading",
	)


SearchEngine = Literal["perplexity", "searxng", "bing", "google"]
MCPTransportSetting = Literal["streamable_http", "sse", "stdio"]
MCPUserServerOriginMode = Literal["deny", "allow"]


class SearchEngineSettings(BaseModel):
	"""search engine configuration for web search"""

	engine: SearchEngine = settings_field(
		default="perplexity",
		description="web search engine",
	)


PerplexityModel = Literal[
	"sonar",
	"sonar-pro",
	"sonar-reasoning",
	"sonar-reasoning-pro",
	"sonar-deep-research",
]

SearchContextUsage = Literal["low", "medium", "high"]

SearchRecencyFilter = Literal["month", "week", "day", "hour", "year"]

SearchAgent = Literal["native", "perplexity"]


_DEFAULT_AGENTIC_WEB_SEARCH_PROMPT: Final[str] = """
you are a focused web search agent.

rules:
- call web_search before answering.
- use search results as evidence, not as a final answer.
- synthesize the answer in your own words.
- include citation markers like [1] when making sourced claims.
- be concise, neutral, and clear when results disagree or are insufficient.
""".strip()


class PerplexitySettings(BaseModel):
	"""perplexity integration settings."""

	api_key: str | None = settings_field(
		default=None,
		description="api key for the perplexity integration",
	)
	model: PerplexityModel = settings_field(
		default="sonar",
		description="perplexity model to use for agentic search",
	)
	search_context_usage: SearchContextUsage = settings_field(
		default="medium",
		description=(
			"how much search context perplexity should use. "
			"low = faster/cheaper, high = more thorough"
		),
	)
	temperature: float = settings_field(
		default=0.2,
		ge=0.0,
		le=2.0,
		description="sampling temperature",
	)
	image_results_enabled: bool = settings_field(
		default=False,
		description="allow web search tools to request image URLs from perplexity",
	)
	max_concurrent_requests: int = settings_field(
		default=10,
		description="max concurrent requests to perplexity (queue excess)",
		ge=1,
	)


class AgenticWebSearchSettings(BaseModel):
	"""agentic web search configuration."""

	agent: SearchAgent = settings_field(
		default="native",
		description="agent provider to use for agentic web search",
	)
	model_id: str | None = settings_field(
		default=None,
		description="model id for the native agentic web search agent",
	)
	system_prompt: str = settings_field(
		default=_DEFAULT_AGENTIC_WEB_SEARCH_PROMPT,
		description="system prompt for the native agentic web search agent",
	)
	model_params: dict[str, object] = settings_field(
		default_factory=dict,
		description="chat model parameters for the native agentic web search agent",
	)
	max_iterations: int = settings_field(
		default=4,
		ge=1,
		le=20,
		description="maximum native agentic web search turns",
	)


class WebSearchSettings(BaseModel):
	"""web search provider configuration."""

	agentic: AgenticWebSearchSettings = settings_field(
		default_factory=AgenticWebSearchSettings,
		description="agentic web search configuration",
	)
	max_chars: int = settings_field(
		default=50_000,
		ge=100,
		description="maximum characters returned in web search result summaries",
	)
	blacklisted_domains: list[str] = settings_field(
		default_factory=list,
		description="domains to exclude from web search results (e.g. 'twitter.com')",
	)
	search_engines: SearchEngineSettings = settings_field(
		default_factory=SearchEngineSettings,
		description="configuration for the supported web search engines",
	)
	web_loaders: WebLoaderSettings = settings_field(
		default_factory=WebLoaderSettings,
		description="configuration for fetching and processing web content",
	)


class OpenWebUIDeployment(BaseModel):
	"""an admin-allowlisted Open WebUI deployment users can import from."""

	name: str = settings_field(
		min_length=1,
		max_length=128,
		description="human-friendly name shown to users",
	)
	description: str = settings_field(
		min_length=1,
		max_length=512,
		description="short description shown to users",
	)
	origin: HttpUrl = settings_field(
		description="base origin of the Open WebUI instance"
	)

	@model_validator(mode="before")
	@classmethod
	def _migrate_label(cls, value: object) -> object:
		if not isinstance(value, Mapping):
			return value
		value_map: dict[object, object] = {key: item for key, item in value.items()}
		if "name" not in value_map and isinstance(value_map.get("label"), str):
			value_map["name"] = value_map["label"]
		if "description" not in value_map:
			value_map["description"] = "Open WebUI import source"
		return value_map


class OpenWebUIIntegrationSettings(BaseModel):
	"""Open WebUI import integration."""

	enabled: bool = settings_field(default=True, description="enable Open WebUI import")
	deployments: list[OpenWebUIDeployment] = settings_field(
		default_factory=list,
		description="admin-allowlisted Open WebUI deployments users can import from",
	)
	fetch_concurrency: int = settings_field(
		default=24,
		ge=1,
		description="max chats fetched concurrently from Open WebUI during "
		"import. higher values speed up large imports but can overwhelm the "
		"Open WebUI host or trip its rate limits; 24-64 is a sane range.",
	)
	db_write_concurrency: int = settings_field(
		default=8,
		ge=1,
		description="max resources written to the database concurrently during "
		"import. each worker holds its own pooled connection, so keep this below "
		"DB_POOL_SIZE + DB_MAX_OVERFLOW or workers will block on connection "
		"checkout. 8 is comfortable for the default pool of 15.",
	)

	@field_validator("deployments")
	@classmethod
	def _unique_origins(
		cls, deployments: list[OpenWebUIDeployment]
	) -> list[OpenWebUIDeployment]:
		seen: set[str] = set()
		for deployment in deployments:
			origin = str(deployment.origin).rstrip("/").lower()
			if origin in seen:
				raise ValueError("Open WebUI deployment origins must be unique")
			seen.add(origin)
		return deployments


class MCPIntegrationSettings(BaseModel):
	"""MCP integration policy."""

	enabled: bool = settings_field(default=True, description="enable MCP integration")
	startup_discovery_enabled: bool = settings_field(
		default=False,
		description="discover enabled global MCP servers during backend startup",
	)
	list_change_listening_enabled: bool = settings_field(
		default=True,
		description="listen for MCP server list-change notifications",
	)
	list_change_debounce_seconds: float = settings_field(
		default=1.0,
		ge=0.1,
		le=30.0,
		description="seconds to debounce MCP list-change refetches",
	)
	list_change_reconnect_max_delay_seconds: float = settings_field(
		default=30.0,
		ge=1.0,
		le=300.0,
		description="maximum delay between MCP list-change listener reconnects",
	)
	allowed_transports: list[MCPTransportSetting] = settings_field(
		default_factory=lambda: ["streamable_http"],
		min_length=1,
		description="MCP transports admins may configure",
	)
	default_timeout_seconds: int = settings_field(
		default=30,
		ge=1,
		le=300,
		description="default MCP request timeout in seconds",
	)
	max_timeout_seconds: int = settings_field(
		default=60,
		ge=1,
		le=600,
		description="maximum MCP request timeout in seconds",
	)
	user_server_origin_mode: MCPUserServerOriginMode = settings_field(
		default="deny",
		description="how to apply user-managed MCP server origins",
	)
	user_server_origins: list[str] = settings_field(
		default_factory=list,
		description="origins used by the user-managed MCP server origin mode",
	)
	user_server_max_count: int = settings_field(
		default=5,
		ge=0,
		le=100,
		description="maximum user-owned MCP servers per user",
	)
	user_server_max_tools: int = settings_field(
		default=50,
		ge=0,
		le=500,
		description="maximum discovered tools per user-owned MCP server",
	)
	user_tool_definition_max_tokens: int = settings_field(
		default=8192,
		ge=256,
		le=128000,
		description="maximum estimated tokens for one user MCP tool definition",
	)

	@field_validator("allowed_transports")
	@classmethod
	def _dedupe_transports(
		cls, transports: list[MCPTransportSetting]
	) -> list[MCPTransportSetting]:
		seen: set[MCPTransportSetting] = set()
		unique: list[MCPTransportSetting] = []
		for transport in transports:
			if transport in seen:
				continue
			seen.add(transport)
			unique.append(transport)
		return unique

	@field_validator("user_server_origins")
	@classmethod
	def _unique_mcp_origins(cls, origins: list[str]) -> list[str]:
		seen: set[str] = set()
		unique: list[str] = []
		for origin in origins:
			normalized = origin.rstrip("/").lower()
			if not normalized or normalized in seen:
				continue
			seen.add(normalized)
			unique.append(normalized)
		return unique

	@model_validator(mode="after")
	def _validate_timeout_range(self) -> Self:
		if self.default_timeout_seconds > self.max_timeout_seconds:
			raise ValueError("default MCP timeout cannot exceed maximum MCP timeout")
		if self.user_server_origin_mode == "allow" and not self.user_server_origins:
			raise ValueError("MCP origin allow mode requires at least one origin")
		return self


class IntegrationsSettings(BaseModel):
	"""third-party integration configuration."""

	mcp: MCPIntegrationSettings = settings_field(
		default_factory=MCPIntegrationSettings,
		description="MCP integration",
	)
	open_webui: OpenWebUIIntegrationSettings = settings_field(
		default_factory=OpenWebUIIntegrationSettings,
		description="Open WebUI integration",
	)
	perplexity: PerplexitySettings = settings_field(
		default_factory=PerplexitySettings,
		description="perplexity integration",
	)
	searxng: SearxngSettings = settings_field(
		default_factory=SearxngSettings,
		description="searxng integration",
	)


class NotificationSettings(BaseModel):
	"""notification delivery tuning."""

	web_push_enabled: bool = settings_field(
		default=False,
		public=True,
		description=(
			"enable server-side Web Push delivery when VAPID keys are configured"
		),
	)
	vapid_public_key: str | None = settings_field(
		default=None,
		public=True,
		description="VAPID public key for browser push subscription",
	)
	vapid_private_key: str | None = settings_field(
		default=None,
		description="VAPID private key for Web Push delivery",
	)
	vapid_subject: str = settings_field(
		default="mailto:admin@localhost",
		write_locked=True,
		description="VAPID subject claim for Web Push delivery",
	)
	web_push_ttl_seconds: int = settings_field(
		default=86_400,
		ge=60,
		description="Web Push TTL in seconds",
	)
	notification_ttl_seconds: int | None = settings_field(
		default=None,
		ge=60,
		description=(
			"native notification TTL in seconds; null keeps notifications indefinitely"
		),
	)

	missed_grace_days: int = settings_field(
		default=7,
		ge=1,
		description="days to look back for missed notifications",
	)
	lookahead_days: int = settings_field(
		default=366,
		ge=1,
		description="days ahead to schedule notifications",
	)


class SoftDeleteSettings(BaseModel):
	"""per-resource soft-delete toggles.

	when enabled, deleting a resource sets its deleted_at timestamp
	instead of removing the row from the database.
	"""

	threads: bool = settings_field(default=True, description="soft-delete threads")
	notes: bool = settings_field(default=True, description="soft-delete notes")
	files: bool = settings_field(default=True, description="soft-delete files")


class CacheRedisSettings(BaseModel):
	"""Redis / Valkey cache and runtime topology."""

	url: str = settings_field(
		default="redis://127.0.0.1:6380/0",
		write_locked=True,
		description=(
			"Redis / Valkey URL used for cross-worker pub/sub and shared state."
		),
	)
	client_name: str = settings_field(
		default="nokodo_ai",
		write_locked=True,
		description="value sent to redis CLIENT SETNAME for attribution.",
	)


class CacheSettings(BaseModel):
	"""cache subsystem configuration."""

	redis: CacheRedisSettings = settings_field(
		default_factory=CacheRedisSettings,
		write_locked=True,
		description="Redis / Valkey cache and pub/sub settings",
	)
	scheduled_items_ttl_seconds: int = settings_field(
		default=30,
		ge=1,
		description="TTL for scheduled items cache entries",
	)
	resource_payload_ttl_seconds: int = settings_field(
		default=60 * 60 * 8,
		ge=1,
		description="TTL for resource payload cache entries",
	)
	prompt_template_ttl_seconds: int = settings_field(
		default=60 * 60 * 8,
		ge=1,
		description="TTL for prompt template cache entries",
	)
	accessible_users_ttl_seconds: int = settings_field(
		default=60 * 60 * 24,
		ge=1,
		description="TTL for accessible user recipient cache entries",
	)
	mcp_snapshot_ttl_seconds: int = settings_field(
		default=60 * 60 * 24,
		ge=1,
		description="TTL for MCP DB snapshot projection cache entries",
	)


class TaskiqSettings(BaseModel):
	"""TaskIQ execution and scheduling topology."""

	queue_name: str = settings_field(
		default="nokodo-ai:taskiq:queue",
		write_locked=True,
		description="TaskIQ queue name used by API, worker, and scheduler processes.",
	)
	result_ttl_seconds: int = settings_field(
		default=60 * 60 * 24,
		ge=1,
		write_locked=True,
		description="seconds to keep TaskIQ result backend entries.",
	)
	max_connections: int = settings_field(
		default=32,
		ge=1,
		write_locked=True,
		description="maximum Redis connections used by TaskIQ components.",
	)
	auto_workers_max: int | None = settings_field(
		default=None,
		ge=1,
		write_locked=True,
		description=(
			"optional maximum worker processes when TaskIQ is started with "
			"--workers auto."
		),
	)
	schedule_prefix: str = settings_field(
		default="nokodo-ai:taskiq:schedules",
		write_locked=True,
		description="Redis key prefix for dynamic TaskIQ schedules.",
	)


class ThreadMaintenanceBackfillSettings(BaseModel):
	"""knobs for the optional retroactive thread maintenance sweep.

	by default this is fully disabled. when enabled, a periodic background
	task scans inactive threads for missing metadata or stale branch
	summaries and dispatches maintenance tasks in bounded batches. each
	maintenance run spends model tokens, so administrators must opt in
	explicitly and set their own batch and lookback bounds.

	note that this is independent from the per-thread inactivity timer
	that resets on every run completion. that timer never enqueues
	retroactive work.
	"""

	enabled: bool = settings_field(
		default=False,
		description=(
			"enable the periodic retroactive thread maintenance sweep. "
			"when False, the schedule is removed and the task is a no-op."
		),
	)
	cron: str = settings_field(
		default="0 4 * * *",
		description=(
			"cron expression for the periodic sweep, evaluated in UTC. "
			"defaults to once per day at 04:00 UTC."
		),
	)
	batch_size: int = settings_field(
		default=10,
		ge=1,
		description=(
			"maximum number of threads dispatched per sweep run. "
			"each thread results in one maintenance task and one model spend."
		),
	)
	max_lookback_days: int = settings_field(
		default=30,
		ge=1,
		description=(
			"only consider threads whose last_activity_at is within this "
			"many days. older threads are ignored to bound model spend."
		),
	)
	min_inactivity_hours: int = settings_field(
		default=8,
		ge=1,
		description=(
			"threads must have been inactive at least this long before the "
			"backfill sweep considers them. should be >= the live "
			"inactivity timer to avoid racing with it."
		),
	)


class ThreadMaintenanceSettings(BaseModel):
	"""live thread maintenance scheduling and execution policy."""

	inactivity_hours: int = settings_field(
		default=8,
		ge=1,
		description=(
			"hours a thread must stay inactive before deferred metadata and "
			"summary maintenance is dispatched. mandatory missing metadata still "
			"runs immediately."
		),
	)
	queued_supersede_after_minutes: int = settings_field(
		default=5,
		ge=1,
		description=(
			"minutes a zero-progress queued thread maintenance task may stay "
			"idle before a new same-thread task supersedes it."
		),
	)
	active_supersede_after_minutes: int = settings_field(
		default=30,
		ge=1,
		description=(
			"minutes an active thread maintenance task may stop reporting "
			"progress before a new same-thread task supersedes it."
		),
	)
	runner_timeout_seconds: int = settings_field(
		default=30 * 60,
		ge=1,
		description="seconds before thread-related durable task runners time out.",
	)
	stale_task_cleanup_after_minutes: int = settings_field(
		default=45,
		ge=1,
		description=(
			"minutes of inactivity before startup cleanup fails stale active "
			"thread-related tasks."
		),
	)


class FileMaintenanceSettings(BaseModel):
	"""knobs for the optional retroactive file maintenance sweep.

	a periodic background task scans files for deferred upkeep and dispatches
	one unified `file.process` task per due file in bounded batches. bulk
	imports defer processing so a large import never fans out hundreds of
	embedding and chat model calls at once and trips provider rate limits. the
	sweep also reaps file tasks that died mid-run so their files stop being
	skipped by the active-task guard.
	"""

	enabled: bool = settings_field(
		default=False,
		description=(
			"enable the periodic file maintenance sweep. when False, the "
			"schedule is removed."
		),
	)
	cron: str = settings_field(
		default="0 */8 * * *",
		description=(
			"cron expression for the periodic sweep, evaluated in UTC. "
			"defaults to every 8 hours."
		),
	)
	batch_size: int = settings_field(
		default=8,
		ge=1,
		description=(
			"maximum number of files dispatched per sweep run. each file "
			"results in one task and one unit of provider spend; keep this "
			"modest so providers are never flooded."
		),
	)
	runner_timeout_seconds: int = settings_field(
		default=30 * 60,
		ge=1,
		description="seconds before a file processing task runner times out.",
	)
	stale_task_cleanup_after_minutes: int = settings_field(
		default=45,
		ge=1,
		description=(
			"minutes of inactivity before a file processing task is treated as "
			"stale and failed so its file can be redispatched."
		),
	)


class TasksSettings(BaseModel):
	"""task execution settings."""

	taskiq: TaskiqSettings = settings_field(
		default_factory=TaskiqSettings,
		write_locked=True,
		description="TaskIQ execution and scheduling settings",
	)
	thread_maintenance: ThreadMaintenanceSettings = settings_field(
		default_factory=ThreadMaintenanceSettings,
		description="live thread maintenance scheduling and execution settings",
	)
	maintenance_backfill: ThreadMaintenanceBackfillSettings = settings_field(
		default_factory=ThreadMaintenanceBackfillSettings,
		description=(
			"retroactive thread maintenance backfill settings. "
			"off by default; controls an optional periodic sweep that "
			"runs maintenance on stale threads in batches."
		),
	)
	file_maintenance: FileMaintenanceSettings = settings_field(
		default_factory=FileMaintenanceSettings,
		description=(
			"retroactive file maintenance settings. off by default; controls "
			"an optional periodic sweep that dispatches deferred processing "
			"(content vectorization and description) for imported files in "
			"paced batches so bulk imports never flood the providers."
		),
	)


# default permissions section


class DefaultPermissionsSettings(BaseModel):
	"""global default permissions applied when no role or
	explicit rule grants access."""

	resource_access: DefaultResourceAccess = settings_field(
		default_factory=DefaultResourceAccess,
		description="per-resource-type default access levels",
	)
	action_permissions: list[ActionPermission] = settings_field(
		default_factory=lambda: [
			ActionPermission.SETTINGS_READ,
			ActionPermission.THREADS_CREATE,
			ActionPermission.PROJECTS_CREATE,
			ActionPermission.NOTES_CREATE,
			ActionPermission.GROUPS_CREATE,
			ActionPermission.REMINDERS_CREATE,
			ActionPermission.CALENDAR_CREATE,
			ActionPermission.MEMORIES_CREATE,
			ActionPermission.TASKS_CREATE,
			ActionPermission.FILES_CREATE,
			ActionPermission.USER_FRIENDSHIPS_CREATE,
			ActionPermission.USER_BLOCKS_CREATE,
		],
		description="action permissions granted by default",
	)

	@field_validator("action_permissions", mode="before")
	@classmethod
	def _strip_unknown(cls, v: object) -> object:
		return strip_unknown_action_permissions(v)


# root settings


# fields that use comma-separated strings instead of JSON arrays
_CSV_FIELDS: frozenset[str] = frozenset(
	{"cors_origins", "allowed_hosts", "previous_secret_keys"}
)


class _LenientEnvSettingsSource(EnvSettingsSource):
	"""Fallback to raw string on JSON decode failure for known CSV list fields.

	Only applies to fields in _CSV_FIELDS, which use comma-separated env vars
	parsed by field validators. All other list fields still hard-fail on malformed
	JSON to preserve startup-time config error visibility.
	"""

	def decode_complex_value(
		self, field_name: str, field: FieldInfo, value: Any
	) -> Any:
		try:
			return json.loads(value)
		except json.JSONDecodeError, ValueError:
			if field_name not in _CSV_FIELDS:
				raise
			return value


class _LenientDotEnvSettingsSource(DotEnvSettingsSource):
	"""Same as _LenientEnvSettingsSource but for .env file values."""

	def decode_complex_value(
		self, field_name: str, field: FieldInfo, value: Any
	) -> Any:
		try:
			return json.loads(value)
		except json.JSONDecodeError, ValueError:
			if field_name not in _CSV_FIELDS:
				raise
			return value


class Settings(BaseSettings):
	model_config = SettingsConfigDict(
		case_sensitive=False,
		env_file=".env",
		env_prefix=ENV_PREFIX,
		env_nested_delimiter=ENV_NESTED_DELIMITER,
		validate_assignment=True,
		extra="ignore",
	)
	ui: UISettings = settings_field(default_factory=UISettings)
	ai: AISettings = settings_field(default_factory=AISettings)
	branding: BrandingSettings = settings_field(
		default_factory=BrandingSettings,
	)
	media: MediaSettings = settings_field(default_factory=MediaSettings)
	assets: AssetsSettings = settings_field(
		default_factory=AssetsSettings,
	)
	limits: LimitsSettings = settings_field(
		default_factory=LimitsSettings,
	)
	security: SecuritySettings = settings_field(
		default_factory=SecuritySettings,
	)
	notifications: NotificationSettings = settings_field(
		default_factory=NotificationSettings,
		description="notification delivery settings",
	)
	soft_delete: SoftDeleteSettings = settings_field(
		default_factory=SoftDeleteSettings,
	)
	web_search: WebSearchSettings = settings_field(
		default_factory=WebSearchSettings,
		description="web search provider settings",
	)
	code_interpreter: CodeInterpreterSettings = settings_field(
		default_factory=CodeInterpreterSettings,
		description="code interpreter sandbox settings",
	)
	default_permissions: DefaultPermissionsSettings = settings_field(
		default_factory=DefaultPermissionsSettings,
	)
	integrations: IntegrationsSettings = settings_field(
		default_factory=IntegrationsSettings,
		description="third-party integration settings",
	)
	cache: CacheSettings = settings_field(
		default_factory=CacheSettings,
		description="cache and Redis settings",
	)
	tasks: TasksSettings = settings_field(
		default_factory=TasksSettings,
		description="task execution settings",
	)

	@staticmethod
	@functools_cache
	def _build_public_exclude_state(
		schema: type[BaseModel],
	) -> tuple[dict[str, Any], bool]:
		"""build public exclude dict and report whether public leaves exist."""
		exclude: dict[str, Any] = {}
		has_public = False
		for field_name, field_info in schema.model_fields.items():
			annotation = field_info.annotation
			if isinstance(annotation, type) and issubclass(annotation, BaseModel):
				nested_exclude, nested_has_public = (
					Settings._build_public_exclude_state(annotation)
				)
				if nested_has_public:
					has_public = True
					if nested_exclude:
						exclude[field_name] = nested_exclude
				else:
					exclude[field_name] = True
				continue

			flags = get_field_flags(schema, field_name)
			if flags.get("public"):
				has_public = True
			else:
				exclude[field_name] = True
		for field_name in schema.model_computed_fields:
			flags = get_field_flags(schema, field_name)
			if not flags.get("public"):
				exclude[field_name] = True
				continue
			has_public = True
		return exclude, has_public

	@staticmethod
	def _build_public_exclude(schema: type[BaseModel]) -> dict[str, Any]:
		"""build model_dump exclude dict for explicit public leaf fields."""
		exclude, _has_public = Settings._build_public_exclude_state(schema)
		return exclude

	def _resolved_media_url(self, asset: MediaAssetSettings, key: str) -> str:
		spec = MEDIA_ASSETS[key]
		cdn = (
			str(self.branding.public_cdn_origin).rstrip("/")
			if self.branding.public_cdn_origin
			else None
		)
		resolved = resolve_asset_source(
			asset.source,
			asset.url,
			spec.default_url,
			cdn_asset_url(cdn, spec.cdn_path) if cdn else None,
		)
		return resolved or spec.default_url

	def _resolve_public_media(self, data: dict[str, Any]) -> None:
		media = data.get("media")
		if not isinstance(media, dict):
			return
		media["favicon"] = {
			**media.get("favicon", {}),
			"url": self._resolved_media_url(self.media.favicon, "favicon"),
		}
		media["apple_touch_icon"] = {
			**media.get("apple_touch_icon", {}),
			"url": self._resolved_media_url(
				self.media.apple_touch_icon,
				"apple_touch_icon",
			),
		}
		media["sidebar_logo"] = {
			**media.get("sidebar_logo", {}),
			"url": self._resolved_media_url(self.media.sidebar_logo, "sidebar_logo"),
		}
		media["splash_logo"] = {
			**media.get("splash_logo", {}),
			"url": self._resolved_media_url(self.media.splash_logo, "splash_logo"),
		}

	def custom_dump(self, exclude_private: bool = False) -> dict[str, Any]:
		"""model_dump with custom excludes."""
		exclude = {}
		if exclude_private:
			exclude.update(self._build_public_exclude(schema=type(self)))

		data = self.model_dump(exclude=exclude or None)
		if exclude_private:
			self._resolve_public_media(data)
		return data

	def validate_runtime_security(self) -> None:
		"""fail production startup when the signing/encryption key is unsafe."""
		from api.boot_settings import boot_settings

		if boot_settings.TESTING or boot_settings.ENV != "production":
			return

		secret_key = self.security.secret_key.strip()
		if len(secret_key.encode("utf-8")) < MINIMUM_SECRET_KEY_BYTES:
			_settings_logger.critical("production secret key is too short")
			raise RuntimeError(
				"NOKODO__SECURITY__SECRET_KEY must be at least 14 bytes in production"
			)
		if secret_key in UNSAFE_SECRET_KEYS:
			_settings_logger.critical("production secret key is still a default value")
			raise RuntimeError(
				"NOKODO__SECURITY__SECRET_KEY must be changed from the "
				"default in production"
			)

	def reload(self) -> Self:
		"""reload settings from all sources."""
		new = Settings()
		vars(self).update(vars(new))
		self.__pydantic_fields_set__ = set(new.__pydantic_fields_set__)
		return self

	@classmethod
	def settings_customise_sources(
		cls,
		settings_cls: type[BaseSettings],
		init_settings: PydanticBaseSettingsSource,
		env_settings: PydanticBaseSettingsSource,
		dotenv_settings: PydanticBaseSettingsSource,
		file_secret_settings: PydanticBaseSettingsSource,
	) -> tuple[PydanticBaseSettingsSource, ...]:
		from api.settings.database import DbSettingsSource

		return (
			init_settings,
			DbSettingsSource(settings_cls),
			_LenientEnvSettingsSource(settings_cls),
			_LenientDotEnvSettingsSource(settings_cls),
			file_secret_settings,
		)


settings: Settings = Settings()


# public helpers


def check_writable(
	schema: type[BaseModel],
	fields: dict[str, Any],
	prefix: str,
) -> None:
	"""recursively validate that no write_locked fields are being changed.

	raises ValueError for unknown or write_locked fields.
	"""
	for field_name, value in fields.items():
		if field_name not in schema.model_fields:
			raise ValueError(f"{prefix}: unknown field '{field_name}'")
		if get_field_flags(schema, field_name).get("write_locked", False):
			raise ValueError(f"{prefix}: field '{field_name}' is not writable")
		# recurse into nested BaseModel sub-sections
		if isinstance(value, dict):
			field_info = schema.model_fields[field_name]
			annotation = field_info.annotation
			if isinstance(annotation, type) and issubclass(annotation, BaseModel):
				check_writable(annotation, value, f"{prefix}.{field_name}")
