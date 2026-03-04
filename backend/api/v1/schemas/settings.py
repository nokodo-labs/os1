"""settings API schemas.

reads return the full Settings schema.

updates accept a patch schema where all fields are optional and only writable
fields are included.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from api.permissions import (
	ActionPermission,
	DefaultResourceAccess,
)
from api.schemas.preferences import BackgroundType
from api.settings import Settings


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


class VectorDatabaseApiKeysPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	qdrant_api_key: str | None = Field(default=None, description="api key for qdrant")
	pinecone_api_key: str | None = Field(
		default=None,
		description="api key for pinecone",
	)
	weaviate_api_key: str | None = Field(
		default=None,
		description="api key for weaviate",
	)
	milvus_token: str | None = Field(default=None, description="token for milvus")
	redis_password: str | None = Field(default=None, description="password for redis")
	opensearch_api_key: str | None = Field(
		default=None,
		description="api key for opensearch",
	)


class VectorDatabaseSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	provider: (
		Literal[
			"qdrant",
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
	url: str | None = Field(default=None, description="vector database endpoint url")
	api_keys: VectorDatabaseApiKeysPatch | None = None


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
	prefetch_limit: int | None = Field(
		default=None,
		ge=1,
		le=10000,
		description="prefetch candidate limit",
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
	messages_to_consider: int | None = Field(
		default=None,
		ge=1,
		description="number of recent messages to consider",
	)


class AIChatContextSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	mode: str | None = Field(
		default=None,
		description="how chats are selected for Agent context enrichment",
	)
	top_k: int | None = Field(
		default=None,
		ge=1,
		description="number of chats to use for context enrichment",
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
	input_autocomplete_model_id: str | None = Field(
		default=None,
		description="model for input autocomplete suggestions",
	)
	summarization_model_id: str | None = Field(
		default=None,
		description="model for thread context summarization",
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


class AISettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	default_agent_ids: list[str] | None = Field(
		default=None, description="ordered list of default agent ids (tried in order)"
	)
	memory: AIMemorySettingsPatch | None = None
	chat_context: AIChatContextSettingsPatch | None = None
	tasks: AITaskSettingsPatch | None = None
	attachments: AIAttachmentSettingsPatch | None = None
	windowing: AIWindowingSettingsPatch | None = None


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


class SoftDeleteSettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	threads: bool | None = Field(default=None, description="soft-delete threads")
	notes: bool | None = Field(default=None, description="soft-delete notes")
	files: bool | None = Field(default=None, description="soft-delete files")


class SettingsPatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	ui: UISettingsPatch | None = None
	ai: AISettingsPatch | None = None
	branding: BrandingSettingsPatch | None = None
	media: MediaSettingsPatch | None = None
	assets: AssetsSettingsPatch | None = None
	limits: LimitsSettingsPatch | None = None
	security: SecuritySettingsPatch | None = None
	soft_delete: SoftDeleteSettingsPatch | None = None
	default_permissions: DefaultPermissionsSettingsPatch | None = None


class SettingsVersions(BaseModel):
	model_config = ConfigDict(extra="forbid")

	ui: int = 0
	ai: int = 0
	branding: int = 0
	media: int = 0
	assets: int = 0
	limits: int = 0
	security: int = 0
	soft_delete: int = 0
	default_permissions: int = 0


class SettingsUpdateRequest(BaseModel):
	model_config = ConfigDict(extra="forbid")

	data: SettingsPatch
	expected_versions: SettingsVersions | None = None


class SettingsResponse(BaseModel):
	model_config = ConfigDict(extra="forbid")

	versions: SettingsVersions
	data: Settings
