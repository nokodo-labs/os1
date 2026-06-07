import type { Schemas } from '$lib/api'

export type Agent = Schemas['Agent']
export type DefaultPermissionsSettings = Schemas['DefaultPermissionsSettings']
export type DefaultPermissionsSettingsPatch = Schemas['DefaultPermissionsSettingsPatch']
export type Model = Schemas['Model']
export type Provider = Schemas['Provider']
export type SettingsResponse = Schemas['SettingsResponse']
export type SettingsUpdateRequest = Schemas['SettingsUpdateRequest']
export type SettingsPatch = SettingsUpdateRequest['data']
export type NotificationSettingsPatch = NonNullable<SettingsPatch['notifications']>
export type BrandingSettingsPatch = NonNullable<SettingsPatch['branding']>
export type PwaManifestAssetsPatch = NonNullable<BrandingSettingsPatch['pwa_assets']>
export type AISettingsPatch = NonNullable<SettingsPatch['ai']>
export type AIMediaSettingsPatch = NonNullable<AISettingsPatch['media']>
export type ImageGenerationSettingsPatch = NonNullable<AIMediaSettingsPatch['images']>
export type WebSearchSettingsPatch = NonNullable<SettingsPatch['web_search']>
export type AgenticWebSearchSettingsPatch = NonNullable<WebSearchSettingsPatch['agentic']>
export type WebLoaderSettingsPatch = NonNullable<WebSearchSettingsPatch['web_loaders']>
export type TavilySettingsPatch = NonNullable<WebLoaderSettingsPatch['tavily']>
export type IntegrationsSettingsPatch = NonNullable<SettingsPatch['integrations']>
export type SearxngSettingsPatch = NonNullable<IntegrationsSettingsPatch['searxng']>
export type PerplexitySettingsPatch = NonNullable<IntegrationsSettingsPatch['perplexity']>
export type CacheSettingsPatch = NonNullable<SettingsPatch['cache']>
export type CodeInterpreterSettingsPatch = NonNullable<SettingsPatch['code_interpreter']>
export type E2bSettingsPatch = NonNullable<CodeInterpreterSettingsPatch['e2b']>
export type AssetsSettingsPatch = NonNullable<SettingsPatch['assets']>
export type VectorDatabaseSettingsPatch = NonNullable<AssetsSettingsPatch['vector_database']>
export type QdrantVectorDatabaseSettingsPatch = NonNullable<VectorDatabaseSettingsPatch['qdrant']>
export type ChromaVectorDatabaseSettingsPatch = NonNullable<VectorDatabaseSettingsPatch['chroma']>
export type PineconeVectorDatabaseSettingsPatch = NonNullable<
	VectorDatabaseSettingsPatch['pinecone']
>
export type WeaviateVectorDatabaseSettingsPatch = NonNullable<
	VectorDatabaseSettingsPatch['weaviate']
>
export type MilvusVectorDatabaseSettingsPatch = NonNullable<VectorDatabaseSettingsPatch['milvus']>
export type RedisVectorDatabaseSettingsPatch = NonNullable<VectorDatabaseSettingsPatch['redis']>
export type OpensearchVectorDatabaseSettingsPatch = NonNullable<
	VectorDatabaseSettingsPatch['opensearch']
>
export type VectorSettingsPatch = NonNullable<AssetsSettingsPatch['vector']>
export type VectorFusionAlgorithm = NonNullable<VectorSettingsPatch['fusion_algorithm']>
export type EmbeddingsSettingsPatch = NonNullable<AssetsSettingsPatch['embeddings']>
export type RerankSettingsPatch = NonNullable<AssetsSettingsPatch['rerank']>
export type RerankDefaultStrategy = NonNullable<RerankSettingsPatch['default_strategy']>
export type StorageSettingsPatch = NonNullable<AssetsSettingsPatch['storage']>
export type S3StorageConfigPatch = NonNullable<StorageSettingsPatch['s3']>

export type ThemeMode = 'light' | 'dark' | 'system'
export type StorageBackend = 'local' | 's3'
export type MediaAssetSource = 'default' | 'cdn' | 'custom'
export type OptionalAssetSource = MediaAssetSource | 'disabled'
export type ChatContextMode = 'recent' | 'relevant' | 'pinned'
export type VectorDatabaseProvider =
	| 'qdrant'
	| 'chroma'
	| 'pinecone'
	| 'weaviate'
	| 'milvus'
	| 'pgvector'
	| 'redis'
	| 'opensearch'
export type CodeInterpreterEngine = 'native' | 'e2b'
export type SearchAgent = 'native' | 'perplexity'
export type SearchEngine = 'perplexity' | 'searxng' | 'bing' | 'google'
export type WebLoaderEngine = 'native' | 'tavily' | 'playwright'
export type PerplexityModel =
	| 'sonar'
	| 'sonar-pro'
	| 'sonar-reasoning'
	| 'sonar-reasoning-pro'
	| 'sonar-deep-research'
export type SearchContextUsage = 'low' | 'medium' | 'high'

export type MediaAssetDraft = {
	source: MediaAssetSource
	url: string
}

export type PwaAssetDraft = {
	source: OptionalAssetSource
	url: string
}

export type PwaManifestAssetsDraft = {
	icon_1024_maskable: PwaAssetDraft
	icon_512_any: PwaAssetDraft
	shortcut_notes: PwaAssetDraft
	shortcut_reminders: PwaAssetDraft
	shortcut_calendar: PwaAssetDraft
	shortcut_messages: PwaAssetDraft
	shortcut_projects: PwaAssetDraft
	shortcut_library: PwaAssetDraft
	shortcut_social: PwaAssetDraft
	shortcut_settings: PwaAssetDraft
	screenshot_narrow_1: PwaAssetDraft
	screenshot_narrow_2: PwaAssetDraft
	screenshot_narrow_3: PwaAssetDraft
	screenshot_narrow_4: PwaAssetDraft
	screenshot_narrow_5: PwaAssetDraft
	screenshot_wide_1: PwaAssetDraft
	screenshot_wide_2: PwaAssetDraft
	screenshot_wide_3: PwaAssetDraft
	screenshot_wide_4: PwaAssetDraft
	screenshot_wide_5: PwaAssetDraft
	screenshot_wide_6: PwaAssetDraft
	screenshot_wide_7: PwaAssetDraft
	screenshot_wide_8: PwaAssetDraft
}

export type AssetResponse = {
	source?: string | null
	url?: string | null
}
