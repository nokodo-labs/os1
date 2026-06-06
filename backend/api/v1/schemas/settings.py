"""settings API schemas.

reads return the full Settings schema.

updates accept a patch schema where all fields are optional and only writable
fields are included.
"""

from __future__ import annotations

from typing import Literal, Self
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from api.permissions import (
	ActionPermission,
	DefaultResourceAccess,
)
from api.schemas.common import MISSING, MissingType
from api.schemas.preferences import BackgroundType
from api.settings import (
	CodeInterpreterEngine,
	MCPTransportSetting,
	MCPUserServerOriginMode,
	PerplexityModel,
	SearchAgent,
	SearchContextUsage,
	SearchEngine,
	Settings,
)


class UISettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	default_theme: str | MissingType = Field(
		default=MISSING,
		description="'light', 'dark', or 'system'",
	)
	default_background: BackgroundType | MissingType = Field(
		default=MISSING,
		description="default background for the app",
	)
	auth_pages_background: BackgroundType | MissingType = Field(
		default=MISSING,
		description="background for auth pages (login, signup)",
	)
	sidebar_collapsed: bool | MissingType = Field(
		default=MISSING, description="collapse sidebar"
	)


class ManifestAssetSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	source: Literal["default", "cdn", "custom", "disabled"] | MissingType = Field(
		default=MISSING,
		description="asset source: default, cdn, custom, or disabled",
	)
	url: str | None | MissingType = Field(
		default=MISSING,
		description="custom asset url override",
	)


class MediaAssetSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	source: Literal["default", "cdn", "custom"] | MissingType = Field(
		default=MISSING,
		description="asset source: default, cdn, or custom",
	)
	url: str | None | MissingType = Field(
		default=MISSING,
		description="custom asset url override",
	)


class MediaSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	favicon: MediaAssetSettingsPatch | MissingType = MISSING
	apple_touch_icon: MediaAssetSettingsPatch | MissingType = MISSING
	sidebar_logo: MediaAssetSettingsPatch | MissingType = MISSING
	splash_logo: MediaAssetSettingsPatch | MissingType = MISSING


class PwaManifestAssetsSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	icon_1024_maskable: ManifestAssetSettingsPatch | MissingType = MISSING
	icon_512_any: ManifestAssetSettingsPatch | MissingType = MISSING
	shortcut_notes: ManifestAssetSettingsPatch | MissingType = MISSING
	shortcut_reminders: ManifestAssetSettingsPatch | MissingType = MISSING
	shortcut_calendar: ManifestAssetSettingsPatch | MissingType = MISSING
	shortcut_messages: ManifestAssetSettingsPatch | MissingType = MISSING
	shortcut_projects: ManifestAssetSettingsPatch | MissingType = MISSING
	shortcut_library: ManifestAssetSettingsPatch | MissingType = MISSING
	shortcut_social: ManifestAssetSettingsPatch | MissingType = MISSING
	shortcut_settings: ManifestAssetSettingsPatch | MissingType = MISSING
	screenshot_narrow_1: ManifestAssetSettingsPatch | MissingType = MISSING
	screenshot_narrow_2: ManifestAssetSettingsPatch | MissingType = MISSING
	screenshot_narrow_3: ManifestAssetSettingsPatch | MissingType = MISSING
	screenshot_narrow_4: ManifestAssetSettingsPatch | MissingType = MISSING
	screenshot_narrow_5: ManifestAssetSettingsPatch | MissingType = MISSING
	screenshot_wide_1: ManifestAssetSettingsPatch | MissingType = MISSING
	screenshot_wide_2: ManifestAssetSettingsPatch | MissingType = MISSING
	screenshot_wide_3: ManifestAssetSettingsPatch | MissingType = MISSING
	screenshot_wide_4: ManifestAssetSettingsPatch | MissingType = MISSING
	screenshot_wide_5: ManifestAssetSettingsPatch | MissingType = MISSING
	screenshot_wide_6: ManifestAssetSettingsPatch | MissingType = MISSING
	screenshot_wide_7: ManifestAssetSettingsPatch | MissingType = MISSING
	screenshot_wide_8: ManifestAssetSettingsPatch | MissingType = MISSING


class QdrantVectorDatabaseSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	url: str | MissingType = Field(default=MISSING, description="qdrant endpoint url")
	use_grpc: bool | MissingType = Field(
		default=MISSING,
		description="use qdrant gRPC transport when available",
	)
	api_key: str | None | MissingType = Field(
		default=MISSING, description="api key for qdrant"
	)


class ChromaVectorDatabaseSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	url: str | None | MissingType = Field(
		default=MISSING, description="chroma endpoint url"
	)
	api_key: str | None | MissingType = Field(
		default=MISSING,
		description="api key for chroma",
	)


class PineconeVectorDatabaseSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	url: str | None | MissingType = Field(
		default=MISSING, description="pinecone endpoint url"
	)
	api_key: str | None | MissingType = Field(
		default=MISSING,
		description="api key for pinecone",
	)


class WeaviateVectorDatabaseSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	url: str | None | MissingType = Field(
		default=MISSING, description="weaviate endpoint url"
	)
	api_key: str | None | MissingType = Field(
		default=MISSING,
		description="api key for weaviate",
	)


class MilvusVectorDatabaseSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	url: str | None | MissingType = Field(
		default=MISSING, description="milvus endpoint url"
	)
	token: str | None | MissingType = Field(
		default=MISSING, description="token for milvus"
	)


class PgvectorVectorDatabaseSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	url: str | None | MissingType = Field(
		default=MISSING, description="pgvector connection url"
	)


class RedisVectorDatabaseSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	url: str | None | MissingType = Field(
		default=MISSING, description="redis endpoint url"
	)
	password: str | None | MissingType = Field(
		default=MISSING, description="password for redis"
	)


class OpensearchVectorDatabaseSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	url: str | None | MissingType = Field(
		default=MISSING, description="opensearch endpoint url"
	)
	api_key: str | None | MissingType = Field(
		default=MISSING,
		description="api key for opensearch",
	)


class VectorDatabaseSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	provider: (
		Literal[
			"qdrant",
			"chroma",
			"pinecone",
			"weaviate",
			"milvus",
			"pgvector",
			"redis",
			"opensearch",
		]
		| MissingType
	) = Field(
		default=MISSING,
		description="vector database provider",
	)
	qdrant: QdrantVectorDatabaseSettingsPatch | MissingType = MISSING
	chroma: ChromaVectorDatabaseSettingsPatch | MissingType = MISSING
	pinecone: PineconeVectorDatabaseSettingsPatch | MissingType = MISSING
	weaviate: WeaviateVectorDatabaseSettingsPatch | MissingType = MISSING
	milvus: MilvusVectorDatabaseSettingsPatch | MissingType = MISSING
	pgvector: PgvectorVectorDatabaseSettingsPatch | MissingType = MISSING
	redis: RedisVectorDatabaseSettingsPatch | MissingType = MISSING
	opensearch: OpensearchVectorDatabaseSettingsPatch | MissingType = MISSING


class VectorSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	collection_template: str | MissingType = Field(
		default=MISSING,
		description="collection name template with '{model}' placeholder",
	)
	sparse_vectors_enabled: bool | MissingType = Field(
		default=MISSING,
		description="enable sparse vectors",
	)
	fusion_algorithm: Literal["rrf", "dbsf"] | MissingType = Field(
		default=MISSING,
		description="fusion algorithm",
	)
	normalize_scores: bool | MissingType = Field(
		default=MISSING,
		description="normalize fused scores",
	)


class EmbeddingsSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	vector_size: int | MissingType = Field(
		default=MISSING,
		ge=1,
		description="default embedding vector size",
	)
	batch_size: int | MissingType = Field(
		default=MISSING,
		ge=1,
		le=4096,
		description="embedding batch size",
	)
	max_concurrency: int | None | MissingType = Field(
		default=MISSING,
		ge=1,
		description="max concurrent embedding batches; null means unbounded",
	)


class RerankSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	default_strategy: Literal["none", "native", "external"] | MissingType = Field(
		default=MISSING,
		description="default reranking strategy",
	)
	top_k: int | MissingType = Field(
		default=MISSING,
		ge=1,
		le=100,
		description="rerank top-k",
	)


class LocalStorageConfigPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	root_path: str | MissingType = Field(
		default=MISSING,
		description="root directory for local file storage",
	)


class S3StorageConfigPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	endpoint_url: str | None | MissingType = Field(
		default=MISSING,
		description="S3-compatible endpoint url (None for AWS S3)",
	)
	bucket: str | MissingType = Field(default=MISSING, description="S3 bucket name")
	region: str | MissingType = Field(default=MISSING, description="AWS region")
	access_key_id: str | None | MissingType = Field(
		default=MISSING, description="S3 access key id"
	)
	secret_access_key: str | None | MissingType = Field(
		default=MISSING, description="S3 secret access key"
	)
	prefix: str | MissingType = Field(
		default=MISSING, description="key prefix within the bucket"
	)
	presigned_url_ttl: int | MissingType = Field(
		default=MISSING, ge=1, description="presigned URL expiration in seconds"
	)
	multipart_threshold: int | MissingType = Field(
		default=MISSING,
		ge=1,
		description="bytes above which multipart upload kicks in",
	)
	multipart_chunk_size: int | MissingType = Field(
		default=MISSING,
		ge=1,
		description="multipart upload chunk size in bytes",
	)
	max_retries: int | MissingType = Field(
		default=MISSING,
		ge=0,
		description="max retry attempts",
	)
	retry_mode: Literal["legacy", "standard", "adaptive"] | MissingType = Field(
		default=MISSING,
		description="botocore retry mode",
	)


class StorageSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	backend: Literal["local", "s3"] | MissingType = Field(
		default=MISSING,
		description="active storage backend: 'local' or 's3'",
	)
	local: LocalStorageConfigPatch | MissingType = MISSING
	s3: S3StorageConfigPatch | MissingType = MISSING


class AssetsSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	default_embedding_model_id: str | None | MissingType = Field(
		default=MISSING,
		description="default embedding model id (Model.id)",
	)
	vector_database: VectorDatabaseSettingsPatch | MissingType = MISSING
	vector: VectorSettingsPatch | MissingType = MISSING
	embeddings: EmbeddingsSettingsPatch | MissingType = MISSING
	rerank: RerankSettingsPatch | MissingType = MISSING
	storage: StorageSettingsPatch | MissingType = MISSING
	content_vectorization: AssetContentVectorizationSettingsPatch | MissingType = (
		MISSING
	)
	descriptions: AssetDescriptionSettingsPatch | MissingType = MISSING


class BrandingSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	site_name: str | MissingType = Field(default=MISSING, description="site name")
	logo_url: str | None | MissingType = Field(default=MISSING, description="logo url")
	favicon_url: str | None | MissingType = Field(
		default=MISSING, description="favicon url"
	)
	primary_color: str | MissingType = Field(
		default=MISSING, description="primary color hex"
	)
	support_email: str | None | MissingType = Field(
		default=MISSING, description="support email"
	)
	admin_email: str | None | MissingType = Field(
		default=MISSING, description="admin email"
	)
	public_frontend_origin: str | None | MissingType = Field(
		default=MISSING,
		description="public frontend origin",
	)
	public_cdn_origin: str | None | MissingType = Field(
		default=MISSING,
		description="public cdn origin",
	)
	public_console_origin: str | None | MissingType = Field(
		default=MISSING,
		description="public console origin",
	)
	pwa_manifest_url: str | None | MissingType = Field(
		default=MISSING,
		description="external pwa manifest.json url",
	)
	pwa_assets: PwaManifestAssetsSettingsPatch | MissingType = MISSING


class LimitsSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	max_threads_per_user: int | MissingType = Field(
		default=MISSING,
		ge=1,
		description="max threads per user",
	)
	max_messages_per_thread: int | MissingType = Field(
		default=MISSING,
		ge=1,
		description="max messages per thread",
	)
	max_chat_input_chars: int | None | MissingType = Field(
		default=MISSING,
		ge=1,
		description="max characters accepted in chat input. null disables the cap",
	)
	max_file_size_mb: int | MissingType = Field(
		default=MISSING,
		ge=1,
		description="max file size mb",
	)
	max_reminder_hierarchy_depth: int | MissingType = Field(
		default=MISSING,
		ge=1,
		description="maximum nesting depth for sub-reminders",
	)
	max_scheduled_items_window_days: int | MissingType = Field(
		default=MISSING,
		ge=1,
		description="maximum time window in days for scheduled items queries",
	)
	rate_limit_requests_per_minute: int | MissingType = Field(
		default=MISSING,
		ge=1,
		description="rate limit/min",
	)


class OIDCSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	enabled: bool | MissingType = Field(
		default=MISSING,
		description="enable oidc authentication",
	)
	issuer_url: str | None | MissingType = Field(
		default=MISSING,
		description="oidc issuer url",
	)
	client_id: str | None | MissingType = Field(
		default=MISSING,
		description="oidc client id",
	)
	client_secret: str | None | MissingType = Field(
		default=MISSING,
		description="oidc client secret",
	)
	redirect_uri: str | None | MissingType = Field(
		default=MISSING,
		description="oidc redirect uri",
	)
	scopes: list[str] | MissingType = Field(
		default=MISSING,
		description="oidc scopes",
	)
	only: bool | MissingType = Field(
		default=MISSING,
		description="only allow login via oidc",
	)


class SecuritySettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	allow_signups: bool | MissingType = Field(
		default=MISSING,
		description="allow new user signups",
	)
	auto_signup_role_ids: list[str] | None | MissingType = Field(
		default=MISSING,
		description="role ids auto-applied to new signups",
	)
	access_token_expire_minutes: int | MissingType = Field(
		default=MISSING,
		ge=1,
		description="access token expire minutes",
	)
	refresh_token_expire_days: int | MissingType = Field(
		default=MISSING,
		ge=1,
		description="refresh token expire days",
	)
	auth_cookie_secure: bool | MissingType = Field(
		default=MISSING,
		description="set secure cookies",
	)
	session_timeout_minutes: int | MissingType = Field(
		default=MISSING,
		ge=5,
		description="session timeout",
	)
	require_email_verification: bool | MissingType = Field(
		default=MISSING,
		description="require email verification",
	)
	allowed_email_domains: list[str] | MissingType = Field(
		default=MISSING,
		description="allowed domains",
	)
	oidc: OIDCSettingsPatch | MissingType = MISSING


class AIMemorySettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	enable_memory: bool | MissingType = Field(
		default=MISSING, description="enable memory"
	)
	similarity_threshold: float | MissingType = Field(
		default=MISSING,
		ge=0.0,
		le=1.0,
		description="similarity minimum threshold for memory retrieval",
	)
	top_k: int | MissingType = Field(
		default=MISSING,
		ge=1,
		description="number of relevant memories to retrieve",
	)


class AIChatContextSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	enabled: bool | MissingType = Field(
		default=MISSING,
		description="enable cross-chat context enrichment",
	)
	mode: str | MissingType = Field(
		default=MISSING,
		description="how chats are selected for Agent context enrichment",
	)
	top_k: int | MissingType = Field(
		default=MISSING,
		ge=1,
		description="number of chats to use for context enrichment",
	)
	similarity_threshold: float | MissingType = Field(
		default=MISSING,
		ge=0.0,
		le=1.0,
		description="similarity minimum threshold for chat context retrieval",
	)


class AITaskSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	default_model_id: str | None | MissingType = Field(
		default=MISSING,
		description="fallback model id for all background tasks",
	)
	thread_metadata_model_id: str | None | MissingType = Field(
		default=MISSING,
		description="model for thread metadata generation (title, tags)",
	)
	thread_maintenance_model_id: str | None | MissingType = Field(
		default=MISSING,
		description="model for inactive thread metadata and summary maintenance",
	)
	input_autocomplete_model_id: str | None | MissingType = Field(
		default=MISSING,
		description="model for input autocomplete suggestions",
	)
	summarization_model_id: str | None | MissingType = Field(
		default=MISSING,
		description="model for thread context summarization",
	)
	memory_post_processing_model_id: str | None | MissingType = Field(
		default=MISSING,
		description="model for memory post-processing (dedup, update, delete)",
	)
	web_search_model_id: str | None | MissingType = Field(
		default=MISSING,
		description="model for native agentic web search",
	)
	asset_description_model_id: str | None | MissingType = Field(
		default=MISSING,
		description="model for asset summaries and non-text descriptions",
	)
	asset_text_extraction_model_id: str | None | MissingType = Field(
		default=MISSING,
		description="model for asset file, document, and media text extraction",
	)
	maintenance_max_chars_per_message: int | None | MissingType = Field(
		default=MISSING,
		ge=100,
		description="max characters per message in thread maintenance transcripts",
	)


class AIAttachmentSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	image_decay_turns: int | MissingType = Field(
		default=MISSING,
		ge=1,
		description="turns before image attachments decay to reference",
	)
	audio_decay_turns: int | MissingType = Field(
		default=MISSING,
		ge=1,
		description="turns before audio attachments decay to reference",
	)
	video_decay_turns: int | MissingType = Field(
		default=MISSING,
		ge=1,
		description="turns before video attachments decay to reference",
	)
	reveal_decay_turns: int | MissingType = Field(
		default=MISSING,
		ge=1,
		description="turns before a revealed attachment decays again",
	)


class AIContextCompactionSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	enabled: bool | MissingType = Field(
		default=MISSING,
		description=(
			"enable token-aware context compaction before chat generation. when "
			"enabled, the system preserves all messages that fit, compacts older "
			"tool output and summarized spans when needed, and can schedule "
			"background summaries for future runs"
		),
	)
	trigger_ratio: float | MissingType = Field(
		default=MISSING,
		ge=0.1,
		le=0.95,
		description=(
			"prompt pressure ratio that triggers background summarization while "
			"the full raw conversation still fits. lower values create summaries "
			"earlier and reduce future latency; higher values defer work until the "
			"thread is closer to the model budget"
		),
	)
	recovery_target_ratio: float | MissingType = Field(
		default=MISSING,
		ge=0.05,
		le=0.90,
		description=(
			"target prompt pressure after a summarization recovery pass. must be "
			"lower than trigger_ratio so compaction has hysteresis and does not "
			"immediately re-trigger after creating a summary"
		),
	)
	target_usage_cap_tokens: int | None | MissingType = Field(
		default=MISSING,
		ge=1,
		description=(
			"optional maximum context budget used for compaction before response "
			"reserve and prompt overhead are subtracted. set this below a model's "
			"advertised window to leave extra provider safety margin or to force "
			"smaller prompts during testing"
		),
	)
	summary_batch_min_tokens: int | MissingType = Field(
		default=MISSING,
		ge=1,
		description=(
			"minimum raw token span to include in a single summary job. prevents "
			"tiny summaries whose marker and metadata would cost more than the "
			"messages they replace"
		),
	)
	summary_batch_max_tokens: int | MissingType = Field(
		default=MISSING,
		ge=1,
		description=(
			"maximum raw token span to send to one summary job. caps summary "
			"prompt size so very long threads are summarized in bounded batches "
			"instead of one large provider request"
		),
	)
	prompt_overhead_tokens: int | MissingType = Field(
		default=MISSING,
		ge=0,
		description=(
			"tokens reserved for provider framing, system wrappers, schema/tool "
			"instructions, and other prompt bytes that are not represented by "
			"stored chat messages. increasing this makes compaction more cautious"
		),
	)
	blocking_summarization_enabled: bool | MissingType = Field(
		default=MISSING,
		description=(
			"allow a last-resort inline summary during the user request when tool "
			"compaction and ready summaries cannot fit the prompt. disabling this "
			"avoids extra latency but may force older messages to be pruned sooner"
		),
	)
	blocking_summarization_timeout_seconds: float | MissingType = Field(
		default=MISSING,
		ge=1.0,
		le=120.0,
		description=(
			"maximum time to wait for an inline last-resort summary before giving "
			"up and trying the next compaction tier. this bounds user-visible "
			"latency when a provider is slow or rejects the summary request"
		),
	)
	tool_result_max_share: float | MissingType = Field(
		default=MISSING,
		ge=0.05,
		le=0.75,
		description=(
			"maximum fraction of the available prompt budget that one tool result "
			"may consume before it is compacted. lower values keep large search, "
			"file, or code outputs from crowding out conversational context"
		),
	)
	tool_result_hard_cap: int | MissingType = Field(
		default=MISSING,
		ge=1000,
		description=(
			"absolute character ceiling for a single tool result before token "
			"estimation. this protects the compaction pipeline from extremely "
			"large raw outputs even when the token budget is configured generously"
		),
	)
	tool_results_combined_max_share: float | MissingType = Field(
		default=MISSING,
		ge=0.10,
		le=0.95,
		description=(
			"maximum fraction of the available prompt budget that all tool "
			"results combined may consume. when the combined total exceeds this, "
			"older tool results are compacted first so tool-heavy runs do not "
			"displace the rest of the conversation"
		),
	)
	response_headroom: int | MissingType = Field(
		default=MISSING,
		ge=256,
		description=(
			"tokens reserved for the assistant response after prompt compaction. "
			"larger values reduce prompt capacity but lower the chance that a "
			"provider stops because there is too little room left to answer"
		),
	)
	summarization_max_chars_per_message: int | None | MissingType = Field(
		default=MISSING,
		ge=1,
		description=(
			"maximum characters copied from each raw message into a summary "
			"transcript. this limits single-message outliers before they reach "
			"the summarization model; null keeps full message text"
		),
	)


class ImageGenerationSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	enabled: bool | MissingType = Field(
		default=MISSING,
		description="enable image generation capabilities",
	)
	model: str | None | MissingType = Field(
		default=MISSING,
		description="model identifier for image generation",
	)
	default_size: str | MissingType = Field(
		default=MISSING,
		description="default image size in WIDTHxHEIGHT format",
	)
	default_steps: int | None | MissingType = Field(
		default=MISSING,
		ge=1,
		description="default number of generation steps",
	)
	default_n: int | MissingType = Field(
		default=MISSING,
		ge=1,
		le=10,
		description="default number of images per prompt",
	)
	max_n: int | MissingType = Field(
		default=MISSING,
		ge=1,
		le=10,
		description="maximum number of images per request",
	)


class VideoGenerationSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	enabled: bool | MissingType = Field(
		default=MISSING,
		description="enable video generation capabilities",
	)
	model: str | None | MissingType = Field(
		default=MISSING,
		description="model identifier for video generation",
	)


class AudioGenerationSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	enabled: bool | MissingType = Field(
		default=MISSING,
		description="enable audio generation capabilities",
	)
	model: str | None | MissingType = Field(
		default=MISSING,
		description="model identifier for audio generation",
	)


class AIMediaSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	images: ImageGenerationSettingsPatch | MissingType = MISSING
	videos: VideoGenerationSettingsPatch | MissingType = MISSING
	audio: AudioGenerationSettingsPatch | MissingType = MISSING


class E2bSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	api_key: str | None | MissingType = Field(
		default=MISSING,
		description="E2B API key",
	)
	template: str | MissingType = Field(
		default=MISSING,
		description="E2B sandbox template",
	)
	available_packages: list[str] | MissingType = Field(
		default=MISSING,
		description="pre-installed Python packages available in the sandbox",
	)


class CodeInterpreterSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	enabled: bool | MissingType = Field(
		default=MISSING,
		description="enable code interpreter capabilities",
	)
	engine: CodeInterpreterEngine | MissingType = Field(
		default=MISSING,
		description="sandbox engine",
	)
	e2b: E2bSettingsPatch | MissingType = MISSING
	timeout: int | MissingType = Field(
		default=MISSING,
		ge=5,
		le=300,
		description="execution timeout in seconds",
	)
	max_file_download_mb: int | MissingType = Field(
		default=MISSING,
		ge=1,
		description="max file size downloadable from sandbox in MB",
	)
	max_output_chars: int | MissingType = Field(
		default=MISSING,
		ge=1000,
		description="max output characters returned from code interpreter",
	)
	truncation_lines: int | MissingType = Field(
		default=MISSING,
		ge=5,
		description="lines kept at head and tail when truncating output",
	)


class AssetContentVectorizationSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	loader: Literal["auto", "plain", "markitdown", "chatmodel"] | MissingType = Field(
		default=MISSING,
		description="asset content text loader",
	)
	chunking_algorithm: Literal["auto", "recursive", "markdown"] | MissingType = Field(
		default=MISSING,
		description="asset content chunking algorithm",
	)
	max_bytes: int | None | MissingType = Field(
		default=MISSING,
		ge=1,
		description="maximum bytes read from an asset; null means unlimited",
	)
	target_tokens: int | MissingType = Field(
		default=MISSING,
		ge=50,
		description="target token count per asset content chunk",
	)
	overlap_tokens: int | MissingType = Field(
		default=MISSING,
		ge=0,
		description="token overlap between adjacent asset content chunks",
	)
	max_chunks: int | None | MissingType = Field(
		default=MISSING,
		ge=1,
		description="maximum content chunks per asset; null means unlimited",
	)


class AssetDescriptionSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	max_input_chars: int | None | MissingType = Field(
		default=MISSING,
		ge=100,
		description=(
			"maximum extracted text characters sent to the description model; "
			"null means unlimited"
		),
	)
	max_chars: int | None | MissingType = Field(
		default=MISSING,
		ge=50,
		description="maximum stored asset description characters; null means unlimited",
	)


class AISettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	default_agent_ids: list[str] | MissingType = Field(
		default=MISSING,
		description="ordered list of default agent ids (tried in order)",
	)
	retrieval_turns: int | MissingType = Field(
		default=MISSING,
		ge=1,
		description="number of recent conversation turns for retrieval queries",
	)
	retrieval_pre_build: bool | MissingType = Field(
		default=MISSING,
		description="pre-build retrieval query before filter loop",
	)
	memory: AIMemorySettingsPatch | MissingType = MISSING
	chat_context: AIChatContextSettingsPatch | MissingType = MISSING
	tasks: AITaskSettingsPatch | MissingType = MISSING
	attachments: AIAttachmentSettingsPatch | MissingType = MISSING
	context_compaction: AIContextCompactionSettingsPatch | MissingType = MISSING
	media: AIMediaSettingsPatch | MissingType = MISSING


class DefaultPermissionsSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	resource_access: DefaultResourceAccess | MissingType = Field(
		default=MISSING,
		description="per-resource-type default access levels",
	)
	action_permissions: list[ActionPermission] | MissingType = Field(
		default=MISSING,
		description="action permissions granted by default",
	)


class NotificationSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	web_push_enabled: bool | MissingType = Field(
		default=MISSING,
		description="enable server-side Web Push delivery when configured",
	)
	vapid_public_key: str | None | MissingType = Field(
		default=MISSING,
		description="VAPID public key for browser push subscription",
	)
	vapid_private_key: str | None | MissingType = Field(
		default=MISSING,
		description="VAPID private key for Web Push delivery",
	)
	web_push_ttl_seconds: int | MissingType = Field(
		default=MISSING,
		ge=60,
		description="Web Push TTL in seconds",
	)
	notification_ttl_seconds: int | None | MissingType = Field(
		default=MISSING,
		ge=60,
		description=(
			"native notification TTL in seconds; null keeps notifications indefinitely"
		),
	)
	missed_grace_days: int | MissingType = Field(
		default=MISSING,
		ge=1,
		description="days to look back for missed notifications",
	)
	lookahead_days: int | MissingType = Field(
		default=MISSING,
		ge=1,
		description="days ahead to schedule notifications",
	)


class SoftDeleteSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	threads: bool | MissingType = Field(
		default=MISSING, description="soft-delete threads"
	)
	notes: bool | MissingType = Field(default=MISSING, description="soft-delete notes")
	files: bool | MissingType = Field(default=MISSING, description="soft-delete files")


class SearxngSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	instance_url: str | MissingType = Field(
		default=MISSING,
		description="base url for the searxng instance",
	)
	max_results: int | MissingType = Field(
		default=MISSING,
		ge=1,
		description="max results to return from searxng",
	)
	max_concurrent_requests: int | MissingType = Field(
		default=MISSING,
		ge=1,
		description="max concurrent requests to searxng",
	)
	timeout_seconds: int | MissingType = Field(
		default=MISSING,
		ge=1,
		description="timeout for searxng API calls in seconds",
	)


class TavilySettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	extract_depth: Literal["basic", "advanced"] | MissingType = Field(
		default=MISSING,
		description="depth of content extraction for tavily web loader",
	)
	api_key: str | None | MissingType = Field(
		default=MISSING,
		description="api key for tavily web loader",
	)
	max_concurrent_requests: int | MissingType = Field(
		default=MISSING,
		ge=1,
		description="max concurrent requests to tavily",
	)


class WebLoaderSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	engine: Literal["native", "tavily", "playwright"] | MissingType = Field(
		default=MISSING,
		description="web loader engine to use",
	)
	timeout_seconds: int | MissingType = Field(
		default=MISSING,
		ge=1,
		description="timeout for web loader fetch operations",
	)
	user_agent: str | MissingType = Field(
		default=MISSING,
		description="user agent string for web loader requests",
	)
	max_chars: int | MissingType = Field(
		default=MISSING,
		ge=100,
		description="maximum characters returned per fetched URL",
	)
	tavily: TavilySettingsPatch | MissingType = MISSING


class SearchEngineSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	engine: SearchEngine | MissingType = Field(
		default=MISSING,
		description="web search engine",
	)


class PerplexitySettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	api_key: str | None | MissingType = Field(
		default=MISSING,
		description="api key for perplexity web search",
	)
	model: PerplexityModel | MissingType = Field(
		default=MISSING,
		description="perplexity model to use for agentic search",
	)
	search_context_usage: SearchContextUsage | MissingType = Field(
		default=MISSING,
		description="how much search context perplexity should use",
	)
	temperature: float | MissingType = Field(
		default=MISSING,
		ge=0.0,
		le=2.0,
		description="sampling temperature (lower = more factual)",
	)
	image_results_enabled: bool | MissingType = Field(
		default=MISSING,
		description="allow web search tools to request image URLs from perplexity",
	)
	max_concurrent_requests: int | MissingType = Field(
		default=MISSING,
		ge=1,
		description="max concurrent requests to perplexity",
	)


class AgenticWebSearchSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	agent: SearchAgent | MissingType = Field(
		default=MISSING,
		description="agent provider to use for agentic web search",
	)
	model_id: str | None | MissingType = Field(
		default=MISSING,
		description="model id for the native agentic web search agent",
	)
	system_prompt: str | MissingType = Field(
		default=MISSING,
		description="system prompt for the native agentic web search agent",
	)
	model_params: dict[str, object] | MissingType = Field(
		default=MISSING,
		description="chat model parameters for the native agentic web search agent",
	)
	max_iterations: int | MissingType = Field(
		default=MISSING,
		ge=1,
		le=20,
		description="maximum native agentic web search turns",
	)


class WebSearchSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	agentic: AgenticWebSearchSettingsPatch | MissingType = Field(
		default=MISSING,
		description="agentic web search configuration",
	)
	max_chars: int | MissingType = Field(
		default=MISSING,
		ge=100,
		description="maximum characters returned in web search result summaries",
	)
	blacklisted_domains: list[str] | MissingType = Field(
		default=MISSING,
		description="domains to exclude from web search results",
	)
	search_engines: SearchEngineSettingsPatch | MissingType = MISSING
	web_loaders: WebLoaderSettingsPatch | MissingType = MISSING


class OpenWebUIDeploymentPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	name: str = Field(min_length=1, max_length=128)
	description: str = Field(min_length=1, max_length=512)
	origin: str = Field(min_length=1, description="Open WebUI base origin url")

	@field_validator("origin")
	@classmethod
	def _validate_origin(cls, value: str) -> str:
		parsed = urlparse(value)
		if parsed.scheme not in {"http", "https"} or not parsed.netloc:
			raise ValueError("origin must be an http(s) url")
		return value.rstrip("/")


class OpenWebUIIntegrationSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	enabled: bool | MissingType = MISSING
	deployments: list[OpenWebUIDeploymentPatch] | MissingType = MISSING
	fetch_concurrency: int | MissingType = Field(
		default=MISSING,
		ge=1,
		description="max chats fetched concurrently from Open WebUI during "
		"import. higher values speed up large imports but can overwhelm the "
		"Open WebUI host or trip its rate limits; 24-64 is a sane range.",
	)
	db_write_concurrency: int | MissingType = Field(
		default=MISSING,
		ge=1,
		description="max resources written to the database concurrently during "
		"import. each worker holds its own pooled connection, so keep this below "
		"DB_POOL_SIZE + DB_MAX_OVERFLOW or workers will block on connection "
		"checkout. 8 is comfortable for the default pool of 15.",
	)

	@field_validator("deployments")
	@classmethod
	def _unique_origins(
		cls, deployments: list[OpenWebUIDeploymentPatch]
	) -> list[OpenWebUIDeploymentPatch]:
		seen: set[str] = set()
		for deployment in deployments:
			origin = deployment.origin.rstrip("/").lower()
			if origin in seen:
				raise ValueError("Open WebUI deployment origins must be unique")
			seen.add(origin)
		return deployments


class MCPIntegrationSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	enabled: bool | MissingType = MISSING
	startup_discovery_enabled: bool | MissingType = MISSING
	list_change_listening_enabled: bool | MissingType = MISSING
	list_change_debounce_seconds: float | MissingType = Field(
		default=MISSING,
		ge=0.1,
		le=30.0,
		description="seconds to debounce MCP list-change refetches",
	)
	list_change_reconnect_max_delay_seconds: float | MissingType = Field(
		default=MISSING,
		ge=1.0,
		le=300.0,
		description="maximum delay between MCP list-change listener reconnects",
	)
	allowed_transports: list[MCPTransportSetting] | MissingType = Field(
		default=MISSING,
		min_length=1,
	)
	default_timeout_seconds: int | MissingType = Field(
		default=MISSING,
		ge=1,
		le=300,
		description="default MCP request timeout in seconds",
	)
	max_timeout_seconds: int | MissingType = Field(
		default=MISSING,
		ge=1,
		le=600,
		description="maximum MCP request timeout in seconds",
	)
	user_server_origin_mode: MCPUserServerOriginMode | MissingType = MISSING
	user_server_origins: list[str] | MissingType = MISSING
	user_server_max_count: int | MissingType = Field(
		default=MISSING,
		ge=0,
		le=100,
		description="maximum user-owned MCP servers per user",
	)
	user_server_max_tools: int | MissingType = Field(
		default=MISSING,
		ge=0,
		le=500,
		description="maximum discovered tools per user-owned MCP server",
	)
	user_tool_definition_max_tokens: int | MissingType = Field(
		default=MISSING,
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
	def _validate_user_server_origins(self) -> Self:
		if self.user_server_origin_mode == "allow" and self.user_server_origins == []:
			raise ValueError("MCP origin allow mode requires at least one origin")
		return self


class IntegrationsSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	mcp: MCPIntegrationSettingsPatch | MissingType = MISSING
	open_webui: OpenWebUIIntegrationSettingsPatch | MissingType = MISSING
	perplexity: PerplexitySettingsPatch | MissingType = MISSING
	searxng: SearxngSettingsPatch | MissingType = MISSING


class CacheRedisSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")


class CacheSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	redis: CacheRedisSettingsPatch | MissingType = MISSING
	scheduled_items_ttl_seconds: int | MissingType = Field(
		default=MISSING,
		ge=1,
		description="TTL for scheduled items cache entries",
	)
	resource_payload_ttl_seconds: int | MissingType = Field(
		default=MISSING,
		ge=1,
		description="TTL for resource payload cache entries",
	)
	accessible_users_ttl_seconds: int | MissingType = Field(
		default=MISSING,
		ge=1,
		description="TTL for accessible user recipient cache entries",
	)


class TaskiqSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")


class ThreadMaintenanceSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	inactivity_hours: int | MissingType = Field(
		default=MISSING,
		ge=1,
		description="hours before deferred thread maintenance runs",
	)
	queued_supersede_after_minutes: int | MissingType = Field(
		default=MISSING,
		ge=1,
		description="minutes before stale queued maintenance is superseded",
	)
	active_supersede_after_minutes: int | MissingType = Field(
		default=MISSING,
		ge=1,
		description="minutes before stale active maintenance is superseded",
	)
	runner_timeout_seconds: int | MissingType = Field(
		default=MISSING,
		ge=1,
		description="seconds before thread-related durable task runners time out",
	)
	stale_task_cleanup_after_minutes: int | MissingType = Field(
		default=MISSING,
		ge=1,
		description="minutes before stale thread-related tasks are cleaned up",
	)


class ThreadMaintenanceBackfillSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	enabled: bool | MissingType = Field(
		default=MISSING,
		description="enable the periodic retroactive thread maintenance sweep",
	)
	cron: str | MissingType = Field(
		default=MISSING,
		description="cron expression for the periodic sweep, evaluated in UTC",
	)
	batch_size: int | MissingType = Field(
		default=MISSING,
		ge=1,
		description="maximum number of threads dispatched per sweep run",
	)
	max_lookback_days: int | MissingType = Field(
		default=MISSING,
		ge=1,
		description="maximum last-activity lookback window in days",
	)
	min_inactivity_hours: int | MissingType = Field(
		default=MISSING,
		ge=1,
		description="minimum inactivity before a thread is considered",
	)


class TasksSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	taskiq: TaskiqSettingsPatch | MissingType = MISSING
	thread_maintenance: ThreadMaintenanceSettingsPatch | MissingType = MISSING
	maintenance_backfill: ThreadMaintenanceBackfillSettingsPatch | MissingType = MISSING


class SettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	ui: UISettingsPatch | MissingType = MISSING
	ai: AISettingsPatch | MissingType = MISSING
	branding: BrandingSettingsPatch | MissingType = MISSING
	media: MediaSettingsPatch | MissingType = MISSING
	assets: AssetsSettingsPatch | MissingType = MISSING
	limits: LimitsSettingsPatch | MissingType = MISSING
	security: SecuritySettingsPatch | MissingType = MISSING
	notifications: NotificationSettingsPatch | MissingType = MISSING
	soft_delete: SoftDeleteSettingsPatch | MissingType = MISSING
	web_search: WebSearchSettingsPatch | MissingType = MISSING
	code_interpreter: CodeInterpreterSettingsPatch | MissingType = MISSING
	default_permissions: DefaultPermissionsSettingsPatch | MissingType = MISSING
	integrations: IntegrationsSettingsPatch | MissingType = MISSING
	cache: CacheSettingsPatch | MissingType = MISSING
	tasks: TasksSettingsPatch | MissingType = MISSING


class SettingsVersions(BaseModel):
	model_config = ConfigDict(extra="forbid")

	ui: int = 0
	ai: int = 0
	branding: int = 0
	media: int = 0
	assets: int = 0
	limits: int = 0
	security: int = 0
	notifications: int = 0
	soft_delete: int = 0
	web_search: int = 0
	code_interpreter: int = 0
	default_permissions: int = 0
	integrations: int = 0
	cache: int = 0
	tasks: int = 0


class SettingsUpdateRequest(BaseModel):
	model_config = ConfigDict(extra="forbid")

	data: SettingsPatch
	expected_versions: SettingsVersions | None = None


class SettingsResponse(BaseModel):
	model_config = ConfigDict(extra="forbid")

	versions: SettingsVersions
	data: Settings


class VapidKeypairResponse(BaseModel):
	model_config = ConfigDict(extra="forbid")

	public_key: str
	private_key: str
