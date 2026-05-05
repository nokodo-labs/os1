"""settings API schemas.

reads return the full Settings schema.

updates accept a patch schema where all fields are optional and only writable
fields are included.
"""

from __future__ import annotations

from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator

from api.permissions import (
	ActionPermission,
	DefaultResourceAccess,
)
from api.schemas.preferences import BackgroundType
from api.settings import (
	CodeInterpreterEngine,
	PerplexityModel,
	SearchAgent,
	SearchContextUsage,
	SearchEngine,
	Settings,
)


class UISettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	default_theme: str | None = Field(
		default=None,
		description="'light', 'dark', or 'system'",
	)
	default_background: BackgroundType | None = Field(
		default=None,
		description="default background for the app",
	)
	auth_pages_background: BackgroundType | None = Field(
		default=None,
		description="background for auth pages (login, signup)",
	)
	sidebar_collapsed: bool | None = Field(default=None, description="collapse sidebar")


class MediaSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	base_url: str | None = Field(
		default=None,
		description="base url for all media assets",
	)
	favicon_url: str | None = Field(
		default=None,
		description="favicon url override",
	)
	apple_touch_icon_url: str | None = Field(
		default=None,
		description="apple touch icon url override",
	)
	sidebar_logo_url: str | None = Field(
		default=None,
		description="sidebar banner logo url override",
	)
	splash_logo_url: str | None = Field(
		default=None,
		description="splash screen logo url override",
	)


class QdrantVectorDatabaseSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	url: str | None = Field(default=None, description="qdrant endpoint url")
	use_grpc: bool | None = Field(
		default=None,
		description="use qdrant gRPC transport when available",
	)
	api_key: str | None = Field(default=None, description="api key for qdrant")


class ChromaVectorDatabaseSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	url: str | None = Field(default=None, description="chroma endpoint url")
	api_key: str | None = Field(
		default=None,
		description="api key for chroma",
	)


class PineconeVectorDatabaseSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	url: str | None = Field(default=None, description="pinecone endpoint url")
	api_key: str | None = Field(
		default=None,
		description="api key for pinecone",
	)


class WeaviateVectorDatabaseSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	url: str | None = Field(default=None, description="weaviate endpoint url")
	api_key: str | None = Field(
		default=None,
		description="api key for weaviate",
	)


class MilvusVectorDatabaseSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	url: str | None = Field(default=None, description="milvus endpoint url")
	token: str | None = Field(default=None, description="token for milvus")


class PgvectorVectorDatabaseSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	url: str | None = Field(default=None, description="pgvector connection url")


class RedisVectorDatabaseSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	url: str | None = Field(default=None, description="redis endpoint url")
	password: str | None = Field(default=None, description="password for redis")


class OpensearchVectorDatabaseSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	url: str | None = Field(default=None, description="opensearch endpoint url")
	api_key: str | None = Field(
		default=None,
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
		| None
	) = Field(
		default=None,
		description="vector database provider",
	)
	qdrant: QdrantVectorDatabaseSettingsPatch | None = None
	chroma: ChromaVectorDatabaseSettingsPatch | None = None
	pinecone: PineconeVectorDatabaseSettingsPatch | None = None
	weaviate: WeaviateVectorDatabaseSettingsPatch | None = None
	milvus: MilvusVectorDatabaseSettingsPatch | None = None
	pgvector: PgvectorVectorDatabaseSettingsPatch | None = None
	redis: RedisVectorDatabaseSettingsPatch | None = None
	opensearch: OpensearchVectorDatabaseSettingsPatch | None = None


class VectorSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	collection_template: str | None = Field(
		default=None,
		description="collection name template with '{model}' placeholder",
	)
	sparse_vectors_enabled: bool | None = Field(
		default=None,
		description="enable sparse vectors",
	)
	fusion_algorithm: Literal["rrf", "dbsf"] | None = Field(
		default=None,
		description="fusion algorithm",
	)
	normalize_scores: bool | None = Field(
		default=None,
		description="normalize fused scores",
	)


class EmbeddingsSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	vector_size: int | None = Field(
		default=None,
		ge=1,
		description="default embedding vector size",
	)
	batch_size: int | None = Field(
		default=None,
		ge=1,
		le=4096,
		description="embedding batch size",
	)


class RerankSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	default_strategy: Literal["none", "native", "external"] | None = Field(
		default=None,
		description="default reranking strategy",
	)
	top_k: int | None = Field(
		default=None,
		ge=1,
		le=100,
		description="rerank top-k",
	)


class LocalStorageConfigPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	root_path: str | None = Field(
		default=None,
		description="root directory for local file storage",
	)


class S3StorageConfigPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	endpoint_url: str | None = Field(
		default=None,
		description="S3-compatible endpoint url (None for AWS S3)",
	)
	bucket: str | None = Field(default=None, description="S3 bucket name")
	region: str | None = Field(default=None, description="AWS region")
	access_key_id: str | None = Field(default=None, description="S3 access key id")
	secret_access_key: str | None = Field(
		default=None, description="S3 secret access key"
	)
	prefix: str | None = Field(default=None, description="key prefix within the bucket")
	presigned_url_ttl: int | None = Field(
		default=None, ge=1, description="presigned URL expiration in seconds"
	)
	multipart_threshold: int | None = Field(
		default=None,
		ge=1,
		description="bytes above which multipart upload kicks in",
	)
	multipart_chunk_size: int | None = Field(
		default=None,
		ge=1,
		description="multipart upload chunk size in bytes",
	)
	max_retries: int | None = Field(
		default=None,
		ge=0,
		description="max retry attempts",
	)
	retry_mode: Literal["legacy", "standard", "adaptive"] | None = Field(
		default=None,
		description="botocore retry mode",
	)


class StorageSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	backend: Literal["local", "s3"] | None = Field(
		default=None,
		description="active storage backend: 'local' or 's3'",
	)
	local: LocalStorageConfigPatch | None = None
	s3: S3StorageConfigPatch | None = None


class AssetsSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	default_embedding_model_id: str | None = Field(
		default=None,
		description="default embedding model id (Model.id)",
	)
	vector_database: VectorDatabaseSettingsPatch | None = None
	vector: VectorSettingsPatch | None = None
	embeddings: EmbeddingsSettingsPatch | None = None
	rerank: RerankSettingsPatch | None = None
	storage: StorageSettingsPatch | None = None


class BrandingSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	site_name: str | None = Field(default=None, description="site name")
	logo_url: str | None = Field(default=None, description="logo url")
	favicon_url: str | None = Field(default=None, description="favicon url")
	primary_color: str | None = Field(default=None, description="primary color hex")
	support_email: str | None = Field(default=None, description="support email")
	admin_email: str | None = Field(default=None, description="admin email")
	public_frontend_origin: str | None = Field(
		default=None,
		description="public frontend origin",
	)
	public_cdn_origin: str | None = Field(
		default=None,
		description="public cdn origin",
	)
	public_console_origin: str | None = Field(
		default=None,
		description="public console origin",
	)
	pwa_manifest_url: str | None = Field(
		default=None,
		description="external pwa manifest.json url",
	)


class LimitsSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	max_threads_per_user: int | None = Field(
		default=None,
		ge=1,
		description="max threads per user",
	)
	max_messages_per_thread: int | None = Field(
		default=None,
		ge=1,
		description="max messages per thread",
	)
	max_file_size_mb: int | None = Field(
		default=None,
		ge=1,
		description="max file size mb",
	)
	max_reminder_hierarchy_depth: int | None = Field(
		default=None,
		ge=1,
		description="maximum nesting depth for sub-reminders",
	)
	max_scheduled_items_window_days: int | None = Field(
		default=None,
		ge=1,
		description="maximum time window in days for scheduled items queries",
	)
	rate_limit_requests_per_minute: int | None = Field(
		default=None,
		ge=1,
		description="rate limit/min",
	)


class OIDCSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	enabled: bool | None = Field(
		default=None,
		description="enable oidc authentication",
	)
	issuer_url: str | None = Field(
		default=None,
		description="oidc issuer url",
	)
	client_id: str | None = Field(
		default=None,
		description="oidc client id",
	)
	client_secret: str | None = Field(
		default=None,
		description="oidc client secret",
	)
	redirect_uri: str | None = Field(
		default=None,
		description="oidc redirect uri",
	)
	scopes: list[str] | None = Field(
		default=None,
		description="oidc scopes",
	)
	only: bool | None = Field(
		default=None,
		description="only allow login via oidc",
	)


class SecuritySettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	allow_signups: bool | None = Field(
		default=None,
		description="allow new user signups",
	)
	auto_signup_role_ids: list[str] | None = Field(
		default=None,
		description="role ids auto-applied to new signups",
	)
	access_token_expire_minutes: int | None = Field(
		default=None,
		ge=1,
		description="access token expire minutes",
	)
	refresh_token_expire_days: int | None = Field(
		default=None,
		ge=1,
		description="refresh token expire days",
	)
	auth_cookie_secure: bool | None = Field(
		default=None,
		description="set secure cookies",
	)
	session_timeout_minutes: int | None = Field(
		default=None,
		ge=5,
		description="session timeout",
	)
	require_email_verification: bool | None = Field(
		default=None,
		description="require email verification",
	)
	allowed_email_domains: list[str] | None = Field(
		default=None,
		description="allowed domains",
	)
	oidc: OIDCSettingsPatch | None = None


class AIMemorySettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	enable_memory: bool | None = Field(default=None, description="enable memory")
	similarity_threshold: float | None = Field(
		default=None,
		ge=0.0,
		le=1.0,
		description="similarity minimum threshold for memory retrieval",
	)
	top_k: int | None = Field(
		default=None,
		ge=1,
		description="number of relevant memories to retrieve",
	)


class AIChatContextSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	enabled: bool | None = Field(
		default=None,
		description="enable cross-chat context enrichment",
	)
	mode: str | None = Field(
		default=None,
		description="how chats are selected for Agent context enrichment",
	)
	top_k: int | None = Field(
		default=None,
		ge=1,
		description="number of chats to use for context enrichment",
	)
	similarity_threshold: float | None = Field(
		default=None,
		ge=0.0,
		le=1.0,
		description="similarity minimum threshold for chat context retrieval",
	)


class AITaskSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	default_model_id: str | None = Field(
		default=None,
		description="fallback model id for all background tasks",
	)
	thread_metadata_model_id: str | None = Field(
		default=None,
		description="model for thread metadata generation (title, tags)",
	)
	thread_maintenance_model_id: str | None = Field(
		default=None,
		description="model for inactive thread metadata and summary maintenance",
	)
	input_autocomplete_model_id: str | None = Field(
		default=None,
		description="model for input autocomplete suggestions",
	)
	summarization_model_id: str | None = Field(
		default=None,
		description="model for thread context summarization",
	)
	memory_post_processing_model_id: str | None = Field(
		default=None,
		description="model for memory post-processing (dedup, update, delete)",
	)
	web_search_model_id: str | None = Field(
		default=None,
		description="model for native agentic web search",
	)
	maintenance_max_chars_per_message: int | None = Field(
		default=None,
		ge=100,
		description="max characters per message in thread maintenance transcripts",
	)


class AIAttachmentSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	image_decay_turns: int | None = Field(
		default=None,
		ge=1,
		description="turns before image attachments decay to reference",
	)
	audio_decay_turns: int | None = Field(
		default=None,
		ge=1,
		description="turns before audio attachments decay to reference",
	)
	video_decay_turns: int | None = Field(
		default=None,
		ge=1,
		description="turns before video attachments decay to reference",
	)
	reveal_decay_turns: int | None = Field(
		default=None,
		ge=1,
		description="turns before a revealed attachment decays again",
	)


class AIWindowingSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	enabled: bool | None = Field(
		default=None,
		description="enable context window management and summarization",
	)
	max_messages: int | None = Field(
		default=None,
		ge=1,
		description="secondary message count guard",
	)
	trigger_ratio: float | None = Field(
		default=None,
		ge=0.1,
		le=0.95,
		description="fraction of token budget to trigger background summarization",
	)
	hard_ratio: float | None = Field(
		default=None,
		ge=0.5,
		le=1.0,
		description="fraction of token budget for hard truncation",
	)
	summary_batch_size: int | None = Field(
		default=None,
		ge=1,
		description="number of oldest unsummarized messages per summary batch",
	)
	max_summaries_before_condense: int | None = Field(
		default=None,
		ge=2,
		description="condense summaries when this many accumulate",
	)
	tool_result_max_share: float | None = Field(
		default=None,
		ge=0.05,
		le=0.75,
		description="max fraction of budget for a single tool result",
	)
	tool_result_hard_cap: int | None = Field(
		default=None,
		ge=1000,
		description="absolute character ceiling per tool result",
	)
	tool_results_combined_max_share: float | None = Field(
		default=None,
		ge=0.10,
		le=0.95,
		description="max fraction of budget for ALL tool results combined (Layer 2)",
	)
	response_headroom: int | None = Field(
		default=None,
		ge=256,
		description="tokens reserved for the model's response",
	)
	summarization_max_chars_per_message: int | None = Field(
		default=None,
		ge=100,
		description="max characters per message in summarization transcripts",
	)


class ImageGenerationSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	enabled: bool | None = Field(
		default=None,
		description="enable image generation capabilities",
	)
	model: str | None = Field(
		default=None,
		description="model identifier for image generation",
	)
	default_size: str | None = Field(
		default=None,
		description="default image size in WIDTHxHEIGHT format",
	)
	default_steps: int | None = Field(
		default=None,
		ge=1,
		description="default number of generation steps",
	)
	default_n: int | None = Field(
		default=None,
		ge=1,
		le=10,
		description="default number of images per prompt",
	)
	max_n: int | None = Field(
		default=None,
		ge=1,
		le=10,
		description="maximum number of images per request",
	)


class VideoGenerationSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	enabled: bool | None = Field(
		default=None,
		description="enable video generation capabilities",
	)
	model: str | None = Field(
		default=None,
		description="model identifier for video generation",
	)


class AudioGenerationSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	enabled: bool | None = Field(
		default=None,
		description="enable audio generation capabilities",
	)
	model: str | None = Field(
		default=None,
		description="model identifier for audio generation",
	)


class AIMediaSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	images: ImageGenerationSettingsPatch | None = None
	videos: VideoGenerationSettingsPatch | None = None
	audio: AudioGenerationSettingsPatch | None = None


class E2bSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	api_key: str | None = Field(
		default=None,
		description="E2B API key",
	)
	template: str | None = Field(
		default=None,
		description="E2B sandbox template",
	)
	available_packages: list[str] | None = Field(
		default=None,
		description="pre-installed Python packages available in the sandbox",
	)


class CodeInterpreterSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	enabled: bool | None = Field(
		default=None,
		description="enable code interpreter capabilities",
	)
	engine: CodeInterpreterEngine | None = Field(
		default=None,
		description="sandbox engine",
	)
	e2b: E2bSettingsPatch | None = None
	timeout: int | None = Field(
		default=None,
		ge=5,
		le=300,
		description="execution timeout in seconds",
	)
	max_file_download_mb: int | None = Field(
		default=None,
		ge=1,
		description="max file size downloadable from sandbox in MB",
	)
	max_output_chars: int | None = Field(
		default=None,
		ge=1000,
		description="max output characters returned from code interpreter",
	)
	truncation_lines: int | None = Field(
		default=None,
		ge=5,
		description="lines kept at head and tail when truncating output",
	)


class AISettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	default_agent_ids: list[str] | None = Field(
		default=None, description="ordered list of default agent ids (tried in order)"
	)
	retrieval_turns: int | None = Field(
		default=None,
		ge=1,
		description="number of recent conversation turns for retrieval queries",
	)
	retrieval_pre_build: bool | None = Field(
		default=None,
		description="pre-build retrieval query before filter loop",
	)
	memory: AIMemorySettingsPatch | None = None
	chat_context: AIChatContextSettingsPatch | None = None
	tasks: AITaskSettingsPatch | None = None
	attachments: AIAttachmentSettingsPatch | None = None
	windowing: AIWindowingSettingsPatch | None = None
	media: AIMediaSettingsPatch | None = None


class DefaultPermissionsSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	resource_access: DefaultResourceAccess | None = Field(
		default=None,
		description="per-resource-type default access levels",
	)
	action_permissions: list[ActionPermission] | None = Field(
		default=None,
		description="action permissions granted by default",
	)


class NotificationSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	missed_grace_days: int | None = Field(
		default=None,
		ge=1,
		description="days to look back for missed notifications",
	)
	lookahead_days: int | None = Field(
		default=None,
		ge=1,
		description="days ahead to schedule notifications",
	)


class SoftDeleteSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	threads: bool | None = Field(default=None, description="soft-delete threads")
	notes: bool | None = Field(default=None, description="soft-delete notes")
	files: bool | None = Field(default=None, description="soft-delete files")


class SearxngSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	instance_url: str | None = Field(
		default=None,
		description="base url for the searxng instance",
	)
	max_results: int | None = Field(
		default=None,
		ge=1,
		description="max results to return from searxng",
	)
	max_concurrent_requests: int | None = Field(
		default=None,
		ge=1,
		description="max concurrent requests to searxng",
	)
	timeout_seconds: int | None = Field(
		default=None,
		ge=1,
		description="timeout for searxng API calls in seconds",
	)


class TavilySettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	extract_depth: Literal["basic", "advanced"] | None = Field(
		default=None,
		description="depth of content extraction for tavily web loader",
	)
	api_key: str | None = Field(
		default=None,
		description="api key for tavily web loader",
	)
	max_concurrent_requests: int | None = Field(
		default=None,
		ge=1,
		description="max concurrent requests to tavily",
	)


class WebLoaderSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	engine: Literal["native", "tavily", "playwright"] | None = Field(
		default=None,
		description="web loader engine to use",
	)
	timeout_seconds: int | None = Field(
		default=None,
		ge=1,
		description="timeout for web loader fetch operations",
	)
	user_agent: str | None = Field(
		default=None,
		description="user agent string for web loader requests",
	)
	max_chars: int | None = Field(
		default=None,
		ge=100,
		description="maximum characters returned per fetched URL",
	)
	tavily: TavilySettingsPatch | None = None


class SearchEngineSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	engine: SearchEngine | None = Field(
		default=None,
		description="web search engine",
	)


class PerplexitySettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	api_key: str | None = Field(
		default=None,
		description="api key for perplexity web search",
	)
	model: PerplexityModel | None = Field(
		default=None,
		description="perplexity model to use for agentic search",
	)
	search_context_usage: SearchContextUsage | None = Field(
		default=None,
		description="how much search context perplexity should use",
	)
	temperature: float | None = Field(
		default=None,
		ge=0.0,
		le=2.0,
		description="sampling temperature (lower = more factual)",
	)
	image_results_enabled: bool | None = Field(
		default=None,
		description="allow web search tools to request image URLs from perplexity",
	)
	max_concurrent_requests: int | None = Field(
		default=None,
		ge=1,
		description="max concurrent requests to perplexity",
	)


class AgenticWebSearchSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	agent: SearchAgent | None = Field(
		default=None,
		description="agent provider to use for agentic web search",
	)
	model_id: str | None = Field(
		default=None,
		description="model id for the native agentic web search agent",
	)
	system_prompt: str | None = Field(
		default=None,
		description="system prompt for the native agentic web search agent",
	)
	model_params: dict[str, object] | None = Field(
		default=None,
		description="chat model parameters for the native agentic web search agent",
	)
	max_iterations: int | None = Field(
		default=None,
		ge=1,
		le=20,
		description="maximum native agentic web search turns",
	)


class WebSearchSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	agentic: AgenticWebSearchSettingsPatch | None = Field(
		default=None,
		description="agentic web search configuration",
	)
	max_chars: int | None = Field(
		default=None,
		ge=100,
		description="maximum characters returned in web search result summaries",
	)
	blacklisted_domains: list[str] | None = Field(
		default=None,
		description="domains to exclude from web search results",
	)
	search_engines: SearchEngineSettingsPatch | None = None
	web_loaders: WebLoaderSettingsPatch | None = None


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

	enabled: bool | None = None
	deployments: list[OpenWebUIDeploymentPatch] | None = None

	@field_validator("deployments")
	@classmethod
	def _unique_origins(
		cls, deployments: list[OpenWebUIDeploymentPatch] | None
	) -> list[OpenWebUIDeploymentPatch] | None:
		if deployments is None:
			return None
		seen: set[str] = set()
		for deployment in deployments:
			origin = deployment.origin.rstrip("/").lower()
			if origin in seen:
				raise ValueError("Open WebUI deployment origins must be unique")
			seen.add(origin)
		return deployments


class IntegrationsSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	open_webui: OpenWebUIIntegrationSettingsPatch | None = None
	perplexity: PerplexitySettingsPatch | None = None
	searxng: SearxngSettingsPatch | None = None


class CacheRedisSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")


class CacheSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	redis: CacheRedisSettingsPatch | None = None
	scheduled_items_ttl_seconds: int | None = Field(
		default=None,
		ge=1,
		description="TTL for scheduled items cache entries",
	)
	resource_payload_ttl_seconds: int | None = Field(
		default=None,
		ge=1,
		description="TTL for resource payload cache entries",
	)


class TaskiqSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")


class TasksSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	taskiq: TaskiqSettingsPatch | None = None


class SettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	ui: UISettingsPatch | None = None
	ai: AISettingsPatch | None = None
	branding: BrandingSettingsPatch | None = None
	media: MediaSettingsPatch | None = None
	assets: AssetsSettingsPatch | None = None
	limits: LimitsSettingsPatch | None = None
	security: SecuritySettingsPatch | None = None
	notifications: NotificationSettingsPatch | None = None
	soft_delete: SoftDeleteSettingsPatch | None = None
	web_search: WebSearchSettingsPatch | None = None
	code_interpreter: CodeInterpreterSettingsPatch | None = None
	default_permissions: DefaultPermissionsSettingsPatch | None = None
	integrations: IntegrationsSettingsPatch | None = None
	cache: CacheSettingsPatch | None = None
	tasks: TasksSettingsPatch | None = None


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
