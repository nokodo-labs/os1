<script lang="ts">
	import { api, unwrap, type BackgroundType, type Schemas } from '$lib/api'
	import { asNumberOrNull, asNumberOrUndefined } from '$lib/utils/settingsNumbers'

	type Agent = Schemas['Agent']
	type DefaultPermissionsSettings = Schemas['DefaultPermissionsSettings']
	type DefaultPermissionsSettingsPatch = Schemas['DefaultPermissionsSettingsPatch']
	type Model = Schemas['Model']
	type Provider = Schemas['Provider']
	type SettingsResponse = Schemas['SettingsResponse']
	type SettingsUpdateRequest = Schemas['SettingsUpdateRequest']
	type SettingsPatch = SettingsUpdateRequest['data']
	type NotificationSettingsPatch = NonNullable<SettingsPatch['notifications']>
	type BrandingSettingsPatch = NonNullable<SettingsPatch['branding']>
	type PwaManifestAssetsPatch = NonNullable<BrandingSettingsPatch['pwa_assets']>
	type AISettingsPatch = NonNullable<SettingsPatch['ai']>
	type AIMediaSettingsPatch = NonNullable<AISettingsPatch['media']>
	type ImageGenerationSettingsPatch = NonNullable<AIMediaSettingsPatch['images']>
	type WebSearchSettingsPatch = NonNullable<SettingsPatch['web_search']>
	type AgenticWebSearchSettingsPatch = NonNullable<WebSearchSettingsPatch['agentic']>
	type WebLoaderSettingsPatch = NonNullable<WebSearchSettingsPatch['web_loaders']>
	type TavilySettingsPatch = NonNullable<WebLoaderSettingsPatch['tavily']>
	type IntegrationsSettingsPatch = NonNullable<SettingsPatch['integrations']>
	type SearxngSettingsPatch = NonNullable<IntegrationsSettingsPatch['searxng']>
	type PerplexitySettingsPatch = NonNullable<IntegrationsSettingsPatch['perplexity']>
	type CacheSettingsPatch = NonNullable<SettingsPatch['cache']>
	type CodeInterpreterSettingsPatch = NonNullable<SettingsPatch['code_interpreter']>
	type E2bSettingsPatch = NonNullable<CodeInterpreterSettingsPatch['e2b']>
	type AssetsSettingsPatch = NonNullable<SettingsPatch['assets']>
	type VectorDatabaseSettingsPatch = NonNullable<AssetsSettingsPatch['vector_database']>
	type QdrantVectorDatabaseSettingsPatch = NonNullable<VectorDatabaseSettingsPatch['qdrant']>
	type ChromaVectorDatabaseSettingsPatch = NonNullable<VectorDatabaseSettingsPatch['chroma']>
	type PineconeVectorDatabaseSettingsPatch = NonNullable<VectorDatabaseSettingsPatch['pinecone']>
	type WeaviateVectorDatabaseSettingsPatch = NonNullable<VectorDatabaseSettingsPatch['weaviate']>
	type MilvusVectorDatabaseSettingsPatch = NonNullable<VectorDatabaseSettingsPatch['milvus']>
	type RedisVectorDatabaseSettingsPatch = NonNullable<VectorDatabaseSettingsPatch['redis']>
	type OpensearchVectorDatabaseSettingsPatch = NonNullable<
		VectorDatabaseSettingsPatch['opensearch']
	>
	type VectorSettingsPatch = NonNullable<AssetsSettingsPatch['vector']>
	type VectorFusionAlgorithm = NonNullable<VectorSettingsPatch['fusion_algorithm']>
	type EmbeddingsSettingsPatch = NonNullable<AssetsSettingsPatch['embeddings']>
	type RerankSettingsPatch = NonNullable<AssetsSettingsPatch['rerank']>
	type RerankDefaultStrategy = NonNullable<RerankSettingsPatch['default_strategy']>
	type StorageSettingsPatch = NonNullable<AssetsSettingsPatch['storage']>
	type S3StorageConfigPatch = NonNullable<StorageSettingsPatch['s3']>

	import NokodoLoader from '$lib/components/NokodoLoader.svelte'
	import SettingsAI from '$lib/components/settings/SettingsAI.svelte'
	import SettingsAssets from '$lib/components/settings/SettingsAssets.svelte'
	import SettingsBranding from '$lib/components/settings/SettingsBranding.svelte'
	import SettingsCodeInterpreter from '$lib/components/settings/SettingsCodeInterpreter.svelte'
	import SettingsDefaultPermissions from '$lib/components/settings/SettingsDefaultPermissions.svelte'
	import SettingsIntegrations from '$lib/components/settings/SettingsIntegrations.svelte'
	import SettingsLimits from '$lib/components/settings/SettingsLimits.svelte'
	import SettingsMedia from '$lib/components/settings/SettingsMedia.svelte'
	import SettingsNotifications from '$lib/components/settings/SettingsNotifications.svelte'
	import SettingsSecurity from '$lib/components/settings/SettingsSecurity.svelte'
	import SettingsSoftDelete from '$lib/components/settings/SettingsSoftDelete.svelte'
	import SettingsTasks from '$lib/components/settings/SettingsTasks.svelte'
	import SettingsUI from '$lib/components/settings/SettingsUI.svelte'
	import SettingsWebSearch from '$lib/components/settings/SettingsWebSearch.svelte'
	import { Button } from '$lib/components/ui/button'
	import {
		Bell,
		Brain,
		CodeXml,
		Database,
		Gauge,
		Globe,
		Image as ImageIcon,
		ListChecks,
		Paintbrush,
		Palette,
		Plug,
		RefreshCw,
		RotateCcw,
		Save,
		Search,
		Shield,
		Trash2,
		Users,
	} from '@lucide/svelte'
	import type { Component } from 'svelte'
	import { onMount } from 'svelte'

	type ThemeMode = 'light' | 'dark' | 'system'
	type StorageBackend = 'local' | 's3'
	type MediaAssetSource = 'default' | 'cdn' | 'custom'
	type OptionalAssetSource = MediaAssetSource | 'disabled'

	type MediaAssetDraft = {
		source: MediaAssetSource
		url: string
	}

	type PwaAssetDraft = {
		source: OptionalAssetSource
		url: string
	}

	type PwaManifestAssetsDraft = {
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

	type AssetResponse = {
		source?: string | null
		url?: string | null
	}

	function pwaAsset(): PwaAssetDraft {
		return { source: 'default', url: '' }
	}

	function defaultPwaAssets(): PwaManifestAssetsDraft {
		return {
			icon_1024_maskable: pwaAsset(),
			icon_512_any: pwaAsset(),
			shortcut_notes: pwaAsset(),
			shortcut_reminders: pwaAsset(),
			shortcut_calendar: pwaAsset(),
			shortcut_messages: pwaAsset(),
			shortcut_projects: pwaAsset(),
			shortcut_library: pwaAsset(),
			shortcut_social: pwaAsset(),
			shortcut_settings: pwaAsset(),
			screenshot_narrow_1: pwaAsset(),
			screenshot_narrow_2: pwaAsset(),
			screenshot_narrow_3: pwaAsset(),
			screenshot_narrow_4: pwaAsset(),
			screenshot_narrow_5: pwaAsset(),
			screenshot_wide_1: pwaAsset(),
			screenshot_wide_2: pwaAsset(),
			screenshot_wide_3: pwaAsset(),
			screenshot_wide_4: pwaAsset(),
			screenshot_wide_5: pwaAsset(),
			screenshot_wide_6: pwaAsset(),
			screenshot_wide_7: pwaAsset(),
			screenshot_wide_8: pwaAsset(),
		}
	}

	function toMediaAsset(value: AssetResponse | undefined): MediaAssetDraft {
		if (value?.url) return { source: 'custom', url: value.url }
		const source =
			value?.source === 'cdn' || value?.source === 'custom' ? value.source : 'default'
		return { source, url: '' }
	}

	function toPwaAsset(value: AssetResponse | undefined): PwaAssetDraft {
		const source =
			value?.source === 'cdn' || value?.source === 'custom' || value?.source === 'disabled'
				? value.source
				: 'default'
		if (source !== 'disabled' && value?.url) return { source: 'custom', url: value.url }
		return { source, url: '' }
	}

	function clonePwaAssets(value: PwaManifestAssetsDraft): PwaManifestAssetsDraft {
		return {
			icon_1024_maskable: { ...value.icon_1024_maskable },
			icon_512_any: { ...value.icon_512_any },
			shortcut_notes: { ...value.shortcut_notes },
			shortcut_reminders: { ...value.shortcut_reminders },
			shortcut_calendar: { ...value.shortcut_calendar },
			shortcut_messages: { ...value.shortcut_messages },
			shortcut_projects: { ...value.shortcut_projects },
			shortcut_library: { ...value.shortcut_library },
			shortcut_social: { ...value.shortcut_social },
			shortcut_settings: { ...value.shortcut_settings },
			screenshot_narrow_1: { ...value.screenshot_narrow_1 },
			screenshot_narrow_2: { ...value.screenshot_narrow_2 },
			screenshot_narrow_3: { ...value.screenshot_narrow_3 },
			screenshot_narrow_4: { ...value.screenshot_narrow_4 },
			screenshot_narrow_5: { ...value.screenshot_narrow_5 },
			screenshot_wide_1: { ...value.screenshot_wide_1 },
			screenshot_wide_2: { ...value.screenshot_wide_2 },
			screenshot_wide_3: { ...value.screenshot_wide_3 },
			screenshot_wide_4: { ...value.screenshot_wide_4 },
			screenshot_wide_5: { ...value.screenshot_wide_5 },
			screenshot_wide_6: { ...value.screenshot_wide_6 },
			screenshot_wide_7: { ...value.screenshot_wide_7 },
			screenshot_wide_8: { ...value.screenshot_wide_8 },
		}
	}

	function pwaAssetsKey(value: PwaManifestAssetsDraft): string {
		return JSON.stringify(value)
	}

	function pwaAssetsFromResponse(
		value: Partial<Record<keyof PwaManifestAssetsDraft, AssetResponse>> | null | undefined
	): PwaManifestAssetsDraft {
		return {
			icon_1024_maskable: toPwaAsset(value?.icon_1024_maskable),
			icon_512_any: toPwaAsset(value?.icon_512_any),
			shortcut_notes: toPwaAsset(value?.shortcut_notes),
			shortcut_reminders: toPwaAsset(value?.shortcut_reminders),
			shortcut_calendar: toPwaAsset(value?.shortcut_calendar),
			shortcut_messages: toPwaAsset(value?.shortcut_messages),
			shortcut_projects: toPwaAsset(value?.shortcut_projects),
			shortcut_library: toPwaAsset(value?.shortcut_library),
			shortcut_social: toPwaAsset(value?.shortcut_social),
			shortcut_settings: toPwaAsset(value?.shortcut_settings),
			screenshot_narrow_1: toPwaAsset(value?.screenshot_narrow_1),
			screenshot_narrow_2: toPwaAsset(value?.screenshot_narrow_2),
			screenshot_narrow_3: toPwaAsset(value?.screenshot_narrow_3),
			screenshot_narrow_4: toPwaAsset(value?.screenshot_narrow_4),
			screenshot_narrow_5: toPwaAsset(value?.screenshot_narrow_5),
			screenshot_wide_1: toPwaAsset(value?.screenshot_wide_1),
			screenshot_wide_2: toPwaAsset(value?.screenshot_wide_2),
			screenshot_wide_3: toPwaAsset(value?.screenshot_wide_3),
			screenshot_wide_4: toPwaAsset(value?.screenshot_wide_4),
			screenshot_wide_5: toPwaAsset(value?.screenshot_wide_5),
			screenshot_wide_6: toPwaAsset(value?.screenshot_wide_6),
			screenshot_wide_7: toPwaAsset(value?.screenshot_wide_7),
			screenshot_wide_8: toPwaAsset(value?.screenshot_wide_8),
		}
	}

	function pwaAssetToPatch(value: PwaAssetDraft) {
		return { source: value.source, url: value.source === 'custom' ? value.url || null : null }
	}

	function pwaAssetsToPatch(value: PwaManifestAssetsDraft): PwaManifestAssetsPatch {
		return {
			icon_1024_maskable: pwaAssetToPatch(value.icon_1024_maskable),
			icon_512_any: pwaAssetToPatch(value.icon_512_any),
			shortcut_notes: pwaAssetToPatch(value.shortcut_notes),
			shortcut_reminders: pwaAssetToPatch(value.shortcut_reminders),
			shortcut_calendar: pwaAssetToPatch(value.shortcut_calendar),
			shortcut_messages: pwaAssetToPatch(value.shortcut_messages),
			shortcut_projects: pwaAssetToPatch(value.shortcut_projects),
			shortcut_library: pwaAssetToPatch(value.shortcut_library),
			shortcut_social: pwaAssetToPatch(value.shortcut_social),
			shortcut_settings: pwaAssetToPatch(value.shortcut_settings),
			screenshot_narrow_1: pwaAssetToPatch(value.screenshot_narrow_1),
			screenshot_narrow_2: pwaAssetToPatch(value.screenshot_narrow_2),
			screenshot_narrow_3: pwaAssetToPatch(value.screenshot_narrow_3),
			screenshot_narrow_4: pwaAssetToPatch(value.screenshot_narrow_4),
			screenshot_narrow_5: pwaAssetToPatch(value.screenshot_narrow_5),
			screenshot_wide_1: pwaAssetToPatch(value.screenshot_wide_1),
			screenshot_wide_2: pwaAssetToPatch(value.screenshot_wide_2),
			screenshot_wide_3: pwaAssetToPatch(value.screenshot_wide_3),
			screenshot_wide_4: pwaAssetToPatch(value.screenshot_wide_4),
			screenshot_wide_5: pwaAssetToPatch(value.screenshot_wide_5),
			screenshot_wide_6: pwaAssetToPatch(value.screenshot_wide_6),
			screenshot_wide_7: pwaAssetToPatch(value.screenshot_wide_7),
			screenshot_wide_8: pwaAssetToPatch(value.screenshot_wide_8),
		}
	}

	let isFetching = $state(true)
	let isSaving = $state(false)
	let error = $state<string | null>(null)
	let saveError = $state<string | null>(null)
	let saveSuccess = $state<string | null>(null)

	type SettingsSectionId =
		| 'section-ui'
		| 'section-ai'
		| 'section-branding'
		| 'section-media'
		| 'section-assets'
		| 'section-limits'
		| 'section-soft-delete'
		| 'section-web-search'
		| 'section-code-interpreter'
		| 'section-tasks'
		| 'section-notifications'
		| 'section-security'
		| 'section-permissions'
		| 'section-integrations'

	let activeSection = $state<SettingsSectionId>('section-ui')
	let settingsSearch = $state('')

	type SettingsSection = {
		id: SettingsSectionId
		label: string
		keywords: string
		icon: Component
		color: string
		activeBg: string
	}

	const sections: SettingsSection[] = [
		{
			id: 'section-ui',
			label: 'UI',
			keywords:
				'theme color scheme light dark system background sidebar collapsed animated galaxy veil silk fog clouds grainient iridescence auth pages',
			icon: Palette,
			color: 'text-violet-400',
			activeBg: 'bg-violet-500/10',
		},
		{
			id: 'section-ai',
			label: 'AI',
			keywords:
				'agents default memory retrieval consolidation similarity threshold top-k chat context recent relevant pinned past chats context window mode turns pre-build embed filters task models thread metadata titles tags autocomplete summarization memory post-processing deduplication attachment decay image audio video iterations context compaction token-aware truncation model limits max messages trigger ratio token budget summary batch size headroom tool result media generation image model steps video audio',
			icon: Brain,
			color: 'text-indigo-400',
			activeBg: 'bg-indigo-500/10',
		},
		{
			id: 'section-branding',
			label: 'branding',
			keywords:
				'site name display name browser tab emails app version primary color accent color hex analytics key support email admin email logo url sidebar favicon url public frontend origin oidc cdn origin console origin pwa manifest',
			icon: Paintbrush,
			color: 'text-fuchsia-400',
			activeBg: 'bg-fuchsia-500/10',
		},
		{
			id: 'section-media',
			label: 'media',
			keywords:
				'base url favicon apple touch icon ios home screen cdn url overrides frontend media assets',
			icon: ImageIcon,
			color: 'text-rose-400',
			activeBg: 'bg-rose-500/10',
		},
		{
			id: 'section-assets',
			label: 'assets',
			keywords:
				'default embedding model vector database provider qdrant chroma pinecone weaviate milvus pgvector redis opensearch endpoint grpc api key collection name template sparse vectors bm25 normalize scores fusion algorithm reciprocal rank distribution vector size dimensions batch size rerank strategy native external top-k storage backend local s3 root path bucket region access key secret key presigned url ttl multipart threshold chunk size max retries retry mode',
			icon: Database,
			color: 'text-cyan-400',
			activeBg: 'bg-cyan-500/10',
		},
		{
			id: 'section-limits',
			label: 'limits',
			keywords:
				'max threads per user cap messages per thread file size upload rate limit requests per minute authenticated',
			icon: Gauge,
			color: 'text-amber-400',
			activeBg: 'bg-amber-500/10',
		},
		{
			id: 'section-soft-delete',
			label: 'soft delete',
			keywords:
				'deleting marks deleted permanently removing database threads notes files retention restore cleanup',
			icon: Trash2,
			color: 'text-red-400',
			activeBg: 'bg-red-500/10',
		},
		{
			id: 'section-web-search',
			label: 'web search',
			keywords:
				'web search agentic agent native perplexity sonar model prompt params iterations search engine blacklisted domains exclude searxng bing google instance url max results max chars concurrent requests timeout web loader tavily playwright user agent extract depth api key temperature image results',
			icon: Globe,
			color: 'text-emerald-400',
			activeBg: 'bg-emerald-500/10',
		},
		{
			id: 'section-code-interpreter',
			label: 'code interpreter',
			keywords:
				'sandbox engine code execution enabled e2b api key template pre-installed packages python numpy pandas matplotlib timeout',
			icon: CodeXml,
			color: 'text-sky-400',
			activeBg: 'bg-sky-500/10',
		},
		{
			id: 'section-tasks',
			label: 'tasks',
			keywords:
				'taskiq background task scheduling thread maintenance backfill cron batch lookback inactivity sweep metadata summaries timeout replacement cleanup',
			icon: ListChecks,
			color: 'text-lime-400',
			activeBg: 'bg-lime-500/10',
		},
		{
			id: 'section-notifications',
			label: 'notifications',
			keywords:
				'notifications web push VAPID keys public key private key browser push ttl missed grace lookahead scheduling delivery',
			icon: Bell,
			color: 'text-yellow-400',
			activeBg: 'bg-yellow-500/10',
		},
		{
			id: 'section-security',
			label: 'security',
			keywords:
				'authentication session secret key jwt algorithm oauth cors origins access token expire refresh token session timeout idle allowed email domains register signup admins users manage auto-apply roles cookie secure require email verification oidc openid connect sso issuer client id client secret redirect uri scopes disable password login',
			icon: Shield,
			color: 'text-orange-400',
			activeBg: 'bg-orange-500/10',
		},
		{
			id: 'section-permissions',
			label: 'permissions',
			keywords:
				'default permissions global defaults role explicit rule resource access thread project file note group reminder list action',
			icon: Users,
			color: 'text-teal-400',
			activeBg: 'bg-teal-500/10',
		},
		{
			id: 'section-integrations',
			label: 'integrations',
			keywords:
				'Open WebUI import deployments jwt chats memories enable allowed deployment name description origin url external services connections MCP servers tools discovery startup user limits allowed denied origins timeout',
			icon: Plug,
			color: 'text-purple-400',
			activeBg: 'bg-purple-500/10',
		},
	]

	const filteredSections = $derived.by(() => {
		const query = settingsSearch.trim().toLowerCase()
		if (!query) return sections
		return sections.filter((section) =>
			`${section.label} ${section.keywords}`.toLowerCase().includes(query)
		)
	})

	$effect(() => {
		if (filteredSections.length === 0) return
		if (filteredSections.some((section) => section.id === activeSection)) return
		activeSection = filteredSections[0].id
	})

	let response = $state<SettingsResponse | null>(null)

	let isFetchingAgents = $state(false)
	let agentsError = $state<string | null>(null)
	let agents = $state<Agent[]>([])

	let isFetchingModels = $state(false)
	let modelsError = $state<string | null>(null)
	let models = $state<Model[]>([])

	let providers = $state<Provider[]>([])

	// Read-only (env-only/write-locked) display values
	let brandingAppVersion = $state<string>('')
	let brandingAnalyticsKeyConfigured = $state<boolean>(false)
	let securitySecretKeyConfigured = $state<boolean>(false)
	let securitySecretKeyUsesDefault = $state<boolean>(false)
	let securityJwtAlgorithm = $state<string>('')
	let securityEnableOauth = $state<boolean>(false)
	let securityCorsOrigins = $state<string>('')

	// Editable form state (only fields supported by Settings*Patch models)
	let uiDefaultTheme = $state<ThemeMode>('system')
	let uiDefaultBackground = $state<BackgroundType | null>(null)
	let uiAuthPagesBackground = $state<BackgroundType | null>(null)
	let uiSidebarCollapsed = $state(false)

	type ChatContextMode = 'recent' | 'relevant' | 'pinned'
	type VectorDatabaseProvider =
		| 'qdrant'
		| 'chroma'
		| 'pinecone'
		| 'weaviate'
		| 'milvus'
		| 'pgvector'
		| 'redis'
		| 'opensearch'
	type CodeInterpreterEngine = 'native' | 'e2b'
	type SearchAgent = 'native' | 'perplexity'
	type SearchEngine = 'perplexity' | 'searxng' | 'bing' | 'google'
	type WebLoaderEngine = 'native' | 'tavily' | 'playwright'
	type PerplexityModel =
		| 'sonar'
		| 'sonar-pro'
		| 'sonar-reasoning'
		| 'sonar-reasoning-pro'
		| 'sonar-deep-research'
	type SearchContextUsage = 'low' | 'medium' | 'high'

	let aiDefaultAgentIds = $state<string[]>([])

	let aiMemoryEnable = $state(false)
	let aiMemorySimilarityThreshold = $state<string>('')
	let aiMemoryTopK = $state<string>('')

	let aiChatContextEnabled = $state(true)
	let aiChatContextMode = $state<ChatContextMode>('recent')
	let aiChatContextTopK = $state<string>('')
	let aiChatContextSimilarityThreshold = $state<string>('')
	let aiRetrievalTurns = $state<string>('')
	let aiRetrievalPreBuild = $state(true)

	let aiTaskDefaultModelId = $state<string>('')
	let aiTaskThreadMetadataModelId = $state<string>('')
	let aiTaskThreadMaintenanceModelId = $state<string>('')
	let aiTaskInputAutocompleteModelId = $state<string>('')
	let aiTaskSummarizationModelId = $state<string>('')
	let aiTaskMemoryPostProcessingModelId = $state<string>('')
	let aiTaskWebSearchModelId = $state<string>('')
	let aiTaskMaintenanceMaxCharsPerMessage = $state<string>('')

	// AI media
	let aiMediaImagesEnabled = $state(true)
	let aiMediaImagesModel = $state<string>('')
	let aiMediaImagesDefaultSize = $state<string>('')
	let aiMediaImagesDefaultSteps = $state<string>('')
	let aiMediaImagesDefaultN = $state<string>('')
	let aiMediaImagesMaxN = $state<string>('')
	let aiMediaVideosEnabled = $state(false)
	let aiMediaAudioEnabled = $state(false)

	// attachment decay
	let aiAttachmentImageDecayIterations = $state<string>('')
	let aiAttachmentAudioDecayIterations = $state<string>('')
	let aiAttachmentVideoDecayIterations = $state<string>('')

	// context compaction
	let aiContextCompactionEnabled = $state(true)
	let aiContextCompactionTriggerRatio = $state<string>('')
	let aiContextCompactionRecoveryTargetRatio = $state<string>('')
	let aiContextCompactionTargetUsageCapTokens = $state<string>('')
	let aiContextCompactionSummaryBatchMinTokens = $state<string>('')
	let aiContextCompactionSummaryBatchMaxTokens = $state<string>('')
	let aiContextCompactionPromptOverheadTokens = $state<string>('')
	let aiContextCompactionBlockingSummarizationEnabled = $state(true)
	let aiContextCompactionBlockingSummarizationTimeoutSeconds = $state<string>('')
	let aiContextCompactionToolResultMaxShare = $state<string>('')
	let aiContextCompactionToolResultHardCap = $state<string>('')
	let aiContextCompactionToolResultsCombinedMaxShare = $state<string>('')
	let aiContextCompactionResponseHeadroom = $state<string>('')
	let aiContextCompactionSummarizationMaxCharsPerMessage = $state<string>('')

	let brandingSiteName = $state('')
	let brandingLogoUrl = $state('')
	let brandingFaviconUrl = $state('')
	let brandingPrimaryColor = $state('')
	let brandingPublicFrontendOrigin = $state('')
	let brandingPublicCdnOrigin = $state('')
	let brandingPwaManifestUrl = $state('')

	let limitsMaxThreadsPerUser = $state<string>('')
	let limitsMaxMessagesPerThread = $state<string>('')
	let limitsMaxChatInputChars = $state<string>('')
	let limitsMaxFileSizeMb = $state<string>('')
	let limitsRateLimitRequestsPerMinute = $state<string>('')
	let cacheAccessibleUsersTtlSeconds = $state<string>('')

	let securityAccessTokenExpireMinutes = $state<string>('')
	let securityRefreshTokenExpireDays = $state<string>('')
	let securityAuthCookieSecure = $state(false)
	let securitySessionTimeoutMinutes = $state<string>('')
	let securityRequireEmailVerification = $state(false)
	let securityAllowedEmailDomains = $state('')
	let securityAllowSignups = $state(true)
	let securityAutoSignupRoleIds = $state<string[]>([])
	let securityOidcEnabled = $state(false)
	let securityOidcIssuerUrl = $state('')
	let securityOidcClientId = $state('')
	let securityOidcClientSecret = $state('')
	let securityOidcRedirectUri = $state('')
	let securityOidcScopes = $state('')
	let securityOidcOnly = $state(false)

	// assets: vector, embeddings, rerank
	let assetsDefaultEmbeddingModelId = $state('')
	let assetsVectorDatabaseProvider = $state<VectorDatabaseProvider>('qdrant')
	let assetsVectorDatabaseUrl = $state('')
	let assetsVectorDatabaseQdrantUseGrpc = $state(true)
	let assetsVectorDatabaseQdrantApiKey = $state('')
	let assetsVectorDatabaseChromaApiKey = $state('')
	let assetsVectorDatabasePineconeApiKey = $state('')
	let assetsVectorDatabaseWeaviateApiKey = $state('')
	let assetsVectorDatabaseMilvusToken = $state('')
	let assetsVectorDatabaseRedisPassword = $state('')
	let assetsVectorDatabaseOpensearchApiKey = $state('')
	let assetsVectorCollectionTemplate = $state('')
	let assetsVectorSparseEnabled = $state(true)
	let assetsVectorFusionAlgorithm = $state<VectorFusionAlgorithm>('rrf')
	let assetsVectorNormalizeScores = $state(true)
	let assetsEmbeddingsVectorSize = $state<string>('')
	let assetsEmbeddingsBatchSize = $state<string>('')
	let assetsRerankDefaultStrategy = $state<RerankDefaultStrategy>('native')
	let assetsRerankTopK = $state<string>('')

	// assets: storage
	let assetsStorageBackend = $state<StorageBackend>('local')
	let assetsStorageLocalRootPath = $state('')
	let assetsStorageS3EndpointUrl = $state('')
	let assetsStorageS3Bucket = $state('')
	let assetsStorageS3Region = $state('')
	let assetsStorageS3AccessKeyId = $state('')
	let assetsStorageS3SecretAccessKey = $state('')
	let assetsStorageS3Prefix = $state('')
	let assetsStorageS3PresignedUrlTtl = $state<string>('')
	let assetsStorageS3MultipartThreshold = $state<string>('')
	let assetsStorageS3MultipartChunkSize = $state<string>('')
	let assetsStorageS3MaxRetries = $state<string>('')
	let assetsStorageS3RetryMode = $state<'legacy' | 'standard' | 'adaptive'>('adaptive')

	// branding extras
	let brandingPublicConsoleOrigin = $state('')
	let brandingSupportEmail = $state('')
	let brandingAdminEmail = $state('')
	let brandingPwaAssets = $state<PwaManifestAssetsDraft>(defaultPwaAssets())

	// media
	let mediaFaviconSource = $state<MediaAssetSource>('default')
	let mediaFaviconUrl = $state('')
	let mediaAppleTouchIconSource = $state<MediaAssetSource>('default')
	let mediaAppleTouchIconUrl = $state('')

	// soft delete
	let softDeleteThreads = $state(true)
	let softDeleteNotes = $state(true)
	let softDeleteFiles = $state(true)

	// notifications
	let notificationsWebPushEnabled = $state(false)
	let notificationsWebPushTtlSeconds = $state<string>('')
	let notificationsNotificationTtlSeconds = $state<string>('')
	let notificationsMissedGraceDays = $state<string>('')
	let notificationsLookaheadDays = $state<string>('')
	let notificationsVapidPublicKey = $state('')
	let notificationsVapidPrivateKey = $state('')
	let isGeneratingVapidKeys = $state(false)
	let vapidGenerationError = $state<string | null>(null)

	// web search
	let webSearchMaxChars = $state<string>('')
	let webSearchAgenticAgent = $state<SearchAgent>('native')
	let webSearchAgenticModelId = $state<string>('')
	let webSearchAgenticSystemPrompt = $state<string>('')
	let webSearchAgenticModelParams = $state<string>('{}')
	let webSearchAgenticMaxIterations = $state<string>('')
	let webSearchBlacklistedDomains = $state<string>('')
	let webSearchEngineEngine = $state<SearchEngine>('perplexity')
	let webSearchSearxngInstanceUrl = $state<string>('')
	let webSearchSearxngMaxResults = $state<string>('')
	let webSearchSearxngMaxConcurrentRequests = $state<string>('')
	let webSearchSearxngTimeoutSeconds = $state<string>('')
	let webSearchWebLoaderEngine = $state<WebLoaderEngine>('native')
	let webSearchWebLoaderTimeoutSeconds = $state<string>('')
	let webSearchWebLoaderUserAgent = $state<string>('')
	let webSearchWebLoaderMaxChars = $state<string>('')
	let webSearchTavilyExtractDepth = $state<'basic' | 'advanced'>('advanced')
	let webSearchTavilyApiKey = $state<string>('')
	let webSearchTavilyMaxConcurrentRequests = $state<string>('')
	let webSearchPerplexityApiKey = $state<string>('')
	let webSearchPerplexityModel = $state<PerplexityModel>('sonar')
	let webSearchPerplexitySearchContextUsage = $state<SearchContextUsage>('medium')
	let webSearchPerplexityTemperature = $state<string>('')
	let webSearchPerplexityImageResultsEnabled = $state(false)
	let webSearchPerplexityMaxConcurrentRequests = $state<string>('')

	// code interpreter
	let codeInterpreterEnabled = $state(true)
	let codeInterpreterEngine = $state<CodeInterpreterEngine>('e2b')
	let codeInterpreterE2bApiKey = $state<string>('')
	let codeInterpreterE2bTemplate = $state<string>('')
	let codeInterpreterE2bAvailablePackages = $state<string>('')
	let codeInterpreterTimeout = $state<string>('')

	// task scheduling
	let taskiqQueueName = $state('')
	let taskiqResultTtlSeconds = $state<string>('')
	let taskiqMaxConnections = $state<string>('')
	let taskiqAutoWorkersMax = $state<string>('')
	let taskiqSchedulePrefix = $state('')
	let taskMaintenanceInactivityHours = $state<string>('')
	let taskMaintenanceQueuedSupersedeAfterMinutes = $state<string>('')
	let taskMaintenanceActiveSupersedeAfterMinutes = $state<string>('')
	let taskMaintenanceRunnerTimeoutSeconds = $state<string>('')
	let taskMaintenanceStaleTaskCleanupAfterMinutes = $state<string>('')
	let taskMaintenanceBackfillEnabled = $state(false)
	let taskMaintenanceBackfillCron = $state('')
	let taskMaintenanceBackfillBatchSize = $state<string>('')
	let taskMaintenanceBackfillMaxLookbackDays = $state<string>('')
	let taskMaintenanceBackfillMinInactivityHours = $state<string>('')

	let defaultPermissions = $state<DefaultPermissionsSettings>({
		resource_access: {
			thread: null,
			project: null,
			file: null,
			calendar: null,
			note: null,
			group: null,
			reminder_list: null,
		},
		action_permissions: [],
	})

	// Original snapshots for change detection
	let original = $state({
		uiDefaultTheme: 'system' as ThemeMode,
		uiDefaultBackground: null as BackgroundType | null,
		uiAuthPagesBackground: null as BackgroundType | null,
		uiSidebarCollapsed: false,
		aiDefaultAgentIds: [] as string[],
		aiMemoryEnable: false,
		aiMemorySimilarityThreshold: '',
		aiMemoryTopK: '',
		aiChatContextEnabled: true,
		aiChatContextMode: 'recent' as ChatContextMode,
		aiChatContextTopK: '',
		aiChatContextSimilarityThreshold: '',
		aiRetrievalTurns: '',
		aiRetrievalPreBuild: true,
		aiTaskDefaultModelId: '',
		aiTaskThreadMetadataModelId: '',
		aiTaskThreadMaintenanceModelId: '',
		aiTaskInputAutocompleteModelId: '',
		aiTaskSummarizationModelId: '',
		aiTaskMemoryPostProcessingModelId: '',
		aiTaskWebSearchModelId: '',
		aiTaskMaintenanceMaxCharsPerMessage: '',
		aiMediaImagesEnabled: true,
		aiMediaImagesModel: '',
		aiMediaImagesDefaultSize: '',
		aiMediaImagesDefaultSteps: '',
		aiMediaImagesDefaultN: '',
		aiMediaImagesMaxN: '',
		aiMediaVideosEnabled: false,
		aiMediaAudioEnabled: false,
		aiAttachmentImageDecayIterations: '',
		aiAttachmentAudioDecayIterations: '',
		aiAttachmentVideoDecayIterations: '',
		aiContextCompactionEnabled: true,
		aiContextCompactionTriggerRatio: '',
		aiContextCompactionRecoveryTargetRatio: '',
		aiContextCompactionTargetUsageCapTokens: '',
		aiContextCompactionSummaryBatchMinTokens: '',
		aiContextCompactionSummaryBatchMaxTokens: '',
		aiContextCompactionPromptOverheadTokens: '',
		aiContextCompactionBlockingSummarizationEnabled: true,
		aiContextCompactionBlockingSummarizationTimeoutSeconds: '',
		aiContextCompactionToolResultMaxShare: '',
		aiContextCompactionToolResultHardCap: '',
		aiContextCompactionToolResultsCombinedMaxShare: '',
		aiContextCompactionResponseHeadroom: '',
		aiContextCompactionSummarizationMaxCharsPerMessage: '',
		brandingSiteName: '',
		brandingLogoUrl: '',
		brandingFaviconUrl: '',
		brandingPrimaryColor: '',
		brandingPublicFrontendOrigin: '',
		brandingPublicCdnOrigin: '',
		brandingPublicConsoleOrigin: '',
		brandingPwaManifestUrl: '',
		brandingPwaAssets: defaultPwaAssets() as PwaManifestAssetsDraft,
		limitsMaxThreadsPerUser: '',
		limitsMaxMessagesPerThread: '',
		limitsMaxChatInputChars: '',
		limitsMaxFileSizeMb: '',
		limitsRateLimitRequestsPerMinute: '',
		cacheAccessibleUsersTtlSeconds: '',
		securityAccessTokenExpireMinutes: '',
		securityRefreshTokenExpireDays: '',
		securityAuthCookieSecure: false,
		securitySessionTimeoutMinutes: '',
		securityRequireEmailVerification: false,
		securityAllowedEmailDomains: '',
		securityAllowSignups: true,
		securityAutoSignupRoleIds: [] as string[],
		securityOidcEnabled: false,
		securityOidcIssuerUrl: '',
		securityOidcClientId: '',
		securityOidcClientSecret: '',
		securityOidcRedirectUri: '',
		securityOidcScopes: '',
		securityOidcOnly: false,
		assetsDefaultEmbeddingModelId: '',
		assetsVectorDatabaseProvider: 'qdrant' as VectorDatabaseProvider,
		assetsVectorDatabaseUrl: '',
		assetsVectorDatabaseQdrantUseGrpc: true,
		assetsVectorDatabaseQdrantApiKey: '',
		assetsVectorDatabaseChromaApiKey: '',
		assetsVectorDatabasePineconeApiKey: '',
		assetsVectorDatabaseWeaviateApiKey: '',
		assetsVectorDatabaseMilvusToken: '',
		assetsVectorDatabaseRedisPassword: '',
		assetsVectorDatabaseOpensearchApiKey: '',
		assetsVectorCollectionTemplate: '',
		assetsVectorSparseEnabled: true,
		assetsVectorFusionAlgorithm: 'rrf' as VectorFusionAlgorithm,
		assetsVectorNormalizeScores: true,
		assetsEmbeddingsVectorSize: '',
		assetsEmbeddingsBatchSize: '',
		assetsRerankDefaultStrategy: 'native' as RerankDefaultStrategy,
		assetsRerankTopK: '',
		assetsStorageBackend: 'local' as StorageBackend,
		assetsStorageLocalRootPath: '',
		assetsStorageS3EndpointUrl: '',
		assetsStorageS3Bucket: '',
		assetsStorageS3Region: '',
		assetsStorageS3AccessKeyId: '',
		assetsStorageS3SecretAccessKey: '',
		assetsStorageS3Prefix: '',
		assetsStorageS3PresignedUrlTtl: '',
		assetsStorageS3MultipartThreshold: '',
		assetsStorageS3MultipartChunkSize: '',
		assetsStorageS3MaxRetries: '',
		assetsStorageS3RetryMode: 'adaptive' as 'legacy' | 'standard' | 'adaptive',
		brandingSupportEmail: '',
		brandingAdminEmail: '',
		mediaFaviconSource: 'default' as MediaAssetSource,
		mediaFaviconUrl: '',
		mediaAppleTouchIconSource: 'default' as MediaAssetSource,
		mediaAppleTouchIconUrl: '',
		softDeleteThreads: true,
		softDeleteNotes: true,
		softDeleteFiles: true,
		notificationsWebPushEnabled: false,
		notificationsWebPushTtlSeconds: '',
		notificationsNotificationTtlSeconds: '',
		notificationsMissedGraceDays: '',
		notificationsLookaheadDays: '',
		notificationsVapidPublicKey: '',
		notificationsVapidPrivateKey: '',
		webSearchMaxChars: '',
		webSearchAgenticAgent: 'native' as SearchAgent,
		webSearchAgenticModelId: '',
		webSearchAgenticSystemPrompt: '',
		webSearchAgenticModelParams: '{}',
		webSearchAgenticMaxIterations: '',
		webSearchBlacklistedDomains: '',
		webSearchEngineEngine: 'perplexity' as SearchEngine,
		webSearchSearxngInstanceUrl: '',
		webSearchSearxngMaxResults: '',
		webSearchSearxngMaxConcurrentRequests: '',
		webSearchSearxngTimeoutSeconds: '',
		webSearchWebLoaderEngine: 'native' as WebLoaderEngine,
		webSearchWebLoaderTimeoutSeconds: '',
		webSearchWebLoaderUserAgent: '',
		webSearchWebLoaderMaxChars: '',
		webSearchTavilyExtractDepth: 'advanced' as 'basic' | 'advanced',
		webSearchTavilyApiKey: '',
		webSearchTavilyMaxConcurrentRequests: '',
		webSearchPerplexityApiKey: '',
		webSearchPerplexityModel: 'sonar' as PerplexityModel,
		webSearchPerplexitySearchContextUsage: 'medium' as SearchContextUsage,
		webSearchPerplexityTemperature: '',
		webSearchPerplexityImageResultsEnabled: false,
		webSearchPerplexityMaxConcurrentRequests: '',
		codeInterpreterEnabled: true,
		codeInterpreterEngine: 'e2b' as CodeInterpreterEngine,
		codeInterpreterE2bApiKey: '',
		codeInterpreterE2bTemplate: '',
		codeInterpreterE2bAvailablePackages: '',
		codeInterpreterTimeout: '',
		taskiqQueueName: '',
		taskiqResultTtlSeconds: '',
		taskiqMaxConnections: '',
		taskiqAutoWorkersMax: '',
		taskiqSchedulePrefix: '',
		taskMaintenanceInactivityHours: '',
		taskMaintenanceQueuedSupersedeAfterMinutes: '',
		taskMaintenanceActiveSupersedeAfterMinutes: '',
		taskMaintenanceRunnerTimeoutSeconds: '',
		taskMaintenanceStaleTaskCleanupAfterMinutes: '',
		taskMaintenanceBackfillEnabled: false,
		taskMaintenanceBackfillCron: '',
		taskMaintenanceBackfillBatchSize: '',
		taskMaintenanceBackfillMaxLookbackDays: '',
		taskMaintenanceBackfillMinInactivityHours: '',
		defaultPermissions: {
			resource_access: {
				thread: null,
				project: null,
				file: null,
				calendar: null,
				note: null,
				group: null,
				reminder_list: null,
			},
			action_permissions: [],
		} as DefaultPermissionsSettings,
		defaultPermissionsKey: '',
	})

	const hasChanges = $derived(
		uiDefaultTheme !== original.uiDefaultTheme ||
			uiDefaultBackground !== original.uiDefaultBackground ||
			uiAuthPagesBackground !== original.uiAuthPagesBackground ||
			uiSidebarCollapsed !== original.uiSidebarCollapsed ||
			JSON.stringify(aiDefaultAgentIds) !== JSON.stringify(original.aiDefaultAgentIds) ||
			aiMemoryEnable !== original.aiMemoryEnable ||
			aiMemorySimilarityThreshold !== original.aiMemorySimilarityThreshold ||
			aiMemoryTopK !== original.aiMemoryTopK ||
			aiChatContextEnabled !== original.aiChatContextEnabled ||
			aiChatContextMode !== original.aiChatContextMode ||
			aiChatContextTopK !== original.aiChatContextTopK ||
			aiChatContextSimilarityThreshold !== original.aiChatContextSimilarityThreshold ||
			aiRetrievalTurns !== original.aiRetrievalTurns ||
			aiRetrievalPreBuild !== original.aiRetrievalPreBuild ||
			aiTaskDefaultModelId !== original.aiTaskDefaultModelId ||
			aiTaskThreadMetadataModelId !== original.aiTaskThreadMetadataModelId ||
			aiTaskThreadMaintenanceModelId !== original.aiTaskThreadMaintenanceModelId ||
			aiTaskInputAutocompleteModelId !== original.aiTaskInputAutocompleteModelId ||
			aiTaskSummarizationModelId !== original.aiTaskSummarizationModelId ||
			aiTaskMemoryPostProcessingModelId !== original.aiTaskMemoryPostProcessingModelId ||
			aiTaskWebSearchModelId !== original.aiTaskWebSearchModelId ||
			aiTaskMaintenanceMaxCharsPerMessage !== original.aiTaskMaintenanceMaxCharsPerMessage ||
			aiAttachmentImageDecayIterations !== original.aiAttachmentImageDecayIterations ||
			aiAttachmentAudioDecayIterations !== original.aiAttachmentAudioDecayIterations ||
			aiAttachmentVideoDecayIterations !== original.aiAttachmentVideoDecayIterations ||
			aiContextCompactionEnabled !== original.aiContextCompactionEnabled ||
			aiContextCompactionTriggerRatio !== original.aiContextCompactionTriggerRatio ||
			aiContextCompactionRecoveryTargetRatio !==
				original.aiContextCompactionRecoveryTargetRatio ||
			aiContextCompactionTargetUsageCapTokens !==
				original.aiContextCompactionTargetUsageCapTokens ||
			aiContextCompactionSummaryBatchMinTokens !==
				original.aiContextCompactionSummaryBatchMinTokens ||
			aiContextCompactionSummaryBatchMaxTokens !==
				original.aiContextCompactionSummaryBatchMaxTokens ||
			aiContextCompactionPromptOverheadTokens !==
				original.aiContextCompactionPromptOverheadTokens ||
			aiContextCompactionBlockingSummarizationEnabled !==
				original.aiContextCompactionBlockingSummarizationEnabled ||
			aiContextCompactionBlockingSummarizationTimeoutSeconds !==
				original.aiContextCompactionBlockingSummarizationTimeoutSeconds ||
			aiContextCompactionToolResultMaxShare !==
				original.aiContextCompactionToolResultMaxShare ||
			aiContextCompactionToolResultHardCap !==
				original.aiContextCompactionToolResultHardCap ||
			aiContextCompactionToolResultsCombinedMaxShare !==
				original.aiContextCompactionToolResultsCombinedMaxShare ||
			aiContextCompactionResponseHeadroom !== original.aiContextCompactionResponseHeadroom ||
			aiContextCompactionSummarizationMaxCharsPerMessage !==
				original.aiContextCompactionSummarizationMaxCharsPerMessage ||
			brandingSiteName !== original.brandingSiteName ||
			brandingLogoUrl !== original.brandingLogoUrl ||
			brandingFaviconUrl !== original.brandingFaviconUrl ||
			brandingPrimaryColor !== original.brandingPrimaryColor ||
			brandingPublicFrontendOrigin !== original.brandingPublicFrontendOrigin ||
			brandingPublicCdnOrigin !== original.brandingPublicCdnOrigin ||
			brandingPublicConsoleOrigin !== original.brandingPublicConsoleOrigin ||
			brandingPwaManifestUrl !== original.brandingPwaManifestUrl ||
			pwaAssetsKey(brandingPwaAssets) !== pwaAssetsKey(original.brandingPwaAssets) ||
			brandingSupportEmail !== original.brandingSupportEmail ||
			brandingAdminEmail !== original.brandingAdminEmail ||
			limitsMaxThreadsPerUser !== original.limitsMaxThreadsPerUser ||
			limitsMaxMessagesPerThread !== original.limitsMaxMessagesPerThread ||
			limitsMaxChatInputChars !== original.limitsMaxChatInputChars ||
			limitsMaxFileSizeMb !== original.limitsMaxFileSizeMb ||
			limitsRateLimitRequestsPerMinute !== original.limitsRateLimitRequestsPerMinute ||
			cacheAccessibleUsersTtlSeconds !== original.cacheAccessibleUsersTtlSeconds ||
			securityAccessTokenExpireMinutes !== original.securityAccessTokenExpireMinutes ||
			securityRefreshTokenExpireDays !== original.securityRefreshTokenExpireDays ||
			securityAuthCookieSecure !== original.securityAuthCookieSecure ||
			securitySessionTimeoutMinutes !== original.securitySessionTimeoutMinutes ||
			securityRequireEmailVerification !== original.securityRequireEmailVerification ||
			securityAllowedEmailDomains !== original.securityAllowedEmailDomains ||
			securityAllowSignups !== original.securityAllowSignups ||
			!arrayEquals(securityAutoSignupRoleIds, original.securityAutoSignupRoleIds) ||
			securityOidcEnabled !== original.securityOidcEnabled ||
			securityOidcIssuerUrl !== original.securityOidcIssuerUrl ||
			securityOidcClientId !== original.securityOidcClientId ||
			securityOidcClientSecret !== original.securityOidcClientSecret ||
			securityOidcRedirectUri !== original.securityOidcRedirectUri ||
			securityOidcScopes !== original.securityOidcScopes ||
			securityOidcOnly !== original.securityOidcOnly ||
			assetsDefaultEmbeddingModelId !== original.assetsDefaultEmbeddingModelId ||
			assetsVectorDatabaseProvider !== original.assetsVectorDatabaseProvider ||
			assetsVectorDatabaseUrl !== original.assetsVectorDatabaseUrl ||
			assetsVectorDatabaseQdrantUseGrpc !== original.assetsVectorDatabaseQdrantUseGrpc ||
			assetsVectorDatabaseQdrantApiKey !== original.assetsVectorDatabaseQdrantApiKey ||
			assetsVectorDatabaseChromaApiKey !== original.assetsVectorDatabaseChromaApiKey ||
			assetsVectorDatabasePineconeApiKey !== original.assetsVectorDatabasePineconeApiKey ||
			assetsVectorDatabaseWeaviateApiKey !== original.assetsVectorDatabaseWeaviateApiKey ||
			assetsVectorDatabaseMilvusToken !== original.assetsVectorDatabaseMilvusToken ||
			assetsVectorDatabaseRedisPassword !== original.assetsVectorDatabaseRedisPassword ||
			assetsVectorDatabaseOpensearchApiKey !==
				original.assetsVectorDatabaseOpensearchApiKey ||
			assetsVectorCollectionTemplate !== original.assetsVectorCollectionTemplate ||
			assetsVectorSparseEnabled !== original.assetsVectorSparseEnabled ||
			assetsVectorFusionAlgorithm !== original.assetsVectorFusionAlgorithm ||
			assetsVectorNormalizeScores !== original.assetsVectorNormalizeScores ||
			assetsEmbeddingsVectorSize !== original.assetsEmbeddingsVectorSize ||
			assetsEmbeddingsBatchSize !== original.assetsEmbeddingsBatchSize ||
			assetsRerankDefaultStrategy !== original.assetsRerankDefaultStrategy ||
			assetsRerankTopK !== original.assetsRerankTopK ||
			assetsStorageBackend !== original.assetsStorageBackend ||
			assetsStorageLocalRootPath !== original.assetsStorageLocalRootPath ||
			assetsStorageS3EndpointUrl !== original.assetsStorageS3EndpointUrl ||
			assetsStorageS3Bucket !== original.assetsStorageS3Bucket ||
			assetsStorageS3Region !== original.assetsStorageS3Region ||
			assetsStorageS3AccessKeyId !== original.assetsStorageS3AccessKeyId ||
			assetsStorageS3SecretAccessKey !== original.assetsStorageS3SecretAccessKey ||
			assetsStorageS3Prefix !== original.assetsStorageS3Prefix ||
			assetsStorageS3PresignedUrlTtl !== original.assetsStorageS3PresignedUrlTtl ||
			assetsStorageS3MultipartThreshold !== original.assetsStorageS3MultipartThreshold ||
			assetsStorageS3MultipartChunkSize !== original.assetsStorageS3MultipartChunkSize ||
			assetsStorageS3MaxRetries !== original.assetsStorageS3MaxRetries ||
			assetsStorageS3RetryMode !== original.assetsStorageS3RetryMode ||
			mediaFaviconSource !== original.mediaFaviconSource ||
			mediaFaviconUrl !== original.mediaFaviconUrl ||
			mediaAppleTouchIconSource !== original.mediaAppleTouchIconSource ||
			mediaAppleTouchIconUrl !== original.mediaAppleTouchIconUrl ||
			softDeleteThreads !== original.softDeleteThreads ||
			softDeleteNotes !== original.softDeleteNotes ||
			softDeleteFiles !== original.softDeleteFiles ||
			notificationsWebPushEnabled !== original.notificationsWebPushEnabled ||
			notificationsWebPushTtlSeconds !== original.notificationsWebPushTtlSeconds ||
			notificationsNotificationTtlSeconds !== original.notificationsNotificationTtlSeconds ||
			notificationsMissedGraceDays !== original.notificationsMissedGraceDays ||
			notificationsLookaheadDays !== original.notificationsLookaheadDays ||
			notificationsVapidPublicKey !== original.notificationsVapidPublicKey ||
			notificationsVapidPrivateKey !== original.notificationsVapidPrivateKey ||
			aiMediaImagesEnabled !== original.aiMediaImagesEnabled ||
			aiMediaImagesModel !== original.aiMediaImagesModel ||
			aiMediaImagesDefaultSize !== original.aiMediaImagesDefaultSize ||
			aiMediaImagesDefaultSteps !== original.aiMediaImagesDefaultSteps ||
			aiMediaImagesDefaultN !== original.aiMediaImagesDefaultN ||
			aiMediaImagesMaxN !== original.aiMediaImagesMaxN ||
			aiMediaVideosEnabled !== original.aiMediaVideosEnabled ||
			aiMediaAudioEnabled !== original.aiMediaAudioEnabled ||
			webSearchMaxChars !== original.webSearchMaxChars ||
			webSearchAgenticAgent !== original.webSearchAgenticAgent ||
			webSearchAgenticModelId !== original.webSearchAgenticModelId ||
			webSearchAgenticSystemPrompt !== original.webSearchAgenticSystemPrompt ||
			webSearchAgenticModelParams !== original.webSearchAgenticModelParams ||
			webSearchAgenticMaxIterations !== original.webSearchAgenticMaxIterations ||
			webSearchBlacklistedDomains !== original.webSearchBlacklistedDomains ||
			webSearchEngineEngine !== original.webSearchEngineEngine ||
			webSearchSearxngInstanceUrl !== original.webSearchSearxngInstanceUrl ||
			webSearchSearxngMaxResults !== original.webSearchSearxngMaxResults ||
			webSearchSearxngMaxConcurrentRequests !==
				original.webSearchSearxngMaxConcurrentRequests ||
			webSearchSearxngTimeoutSeconds !== original.webSearchSearxngTimeoutSeconds ||
			webSearchWebLoaderEngine !== original.webSearchWebLoaderEngine ||
			webSearchWebLoaderTimeoutSeconds !== original.webSearchWebLoaderTimeoutSeconds ||
			webSearchWebLoaderUserAgent !== original.webSearchWebLoaderUserAgent ||
			webSearchWebLoaderMaxChars !== original.webSearchWebLoaderMaxChars ||
			webSearchTavilyExtractDepth !== original.webSearchTavilyExtractDepth ||
			webSearchTavilyApiKey !== original.webSearchTavilyApiKey ||
			webSearchTavilyMaxConcurrentRequests !==
				original.webSearchTavilyMaxConcurrentRequests ||
			webSearchPerplexityApiKey !== original.webSearchPerplexityApiKey ||
			webSearchPerplexityModel !== original.webSearchPerplexityModel ||
			webSearchPerplexitySearchContextUsage !==
				original.webSearchPerplexitySearchContextUsage ||
			webSearchPerplexityTemperature !== original.webSearchPerplexityTemperature ||
			webSearchPerplexityImageResultsEnabled !==
				original.webSearchPerplexityImageResultsEnabled ||
			webSearchPerplexityMaxConcurrentRequests !==
				original.webSearchPerplexityMaxConcurrentRequests ||
			codeInterpreterEnabled !== original.codeInterpreterEnabled ||
			codeInterpreterEngine !== original.codeInterpreterEngine ||
			codeInterpreterE2bApiKey !== original.codeInterpreterE2bApiKey ||
			codeInterpreterE2bTemplate !== original.codeInterpreterE2bTemplate ||
			codeInterpreterE2bAvailablePackages !== original.codeInterpreterE2bAvailablePackages ||
			codeInterpreterTimeout !== original.codeInterpreterTimeout ||
			taskMaintenanceInactivityHours !== original.taskMaintenanceInactivityHours ||
			taskMaintenanceQueuedSupersedeAfterMinutes !==
				original.taskMaintenanceQueuedSupersedeAfterMinutes ||
			taskMaintenanceActiveSupersedeAfterMinutes !==
				original.taskMaintenanceActiveSupersedeAfterMinutes ||
			taskMaintenanceRunnerTimeoutSeconds !== original.taskMaintenanceRunnerTimeoutSeconds ||
			taskMaintenanceStaleTaskCleanupAfterMinutes !==
				original.taskMaintenanceStaleTaskCleanupAfterMinutes ||
			taskMaintenanceBackfillEnabled !== original.taskMaintenanceBackfillEnabled ||
			taskMaintenanceBackfillCron !== original.taskMaintenanceBackfillCron ||
			taskMaintenanceBackfillBatchSize !== original.taskMaintenanceBackfillBatchSize ||
			taskMaintenanceBackfillMaxLookbackDays !==
				original.taskMaintenanceBackfillMaxLookbackDays ||
			taskMaintenanceBackfillMinInactivityHours !==
				original.taskMaintenanceBackfillMinInactivityHours ||
			defaultPermissionsKey(defaultPermissions) !== original.defaultPermissionsKey
	)

	function arrayEquals(a: string[], b: string[]): boolean {
		return a.length === b.length && a.every((v, i) => v === b[i])
	}

	function toStringOrEmpty(v: unknown): string {
		if (v === null || v === undefined) return ''
		return String(v)
	}

	function toBool(v: unknown): boolean {
		return Boolean(v)
	}

	function formatJsonObject(value: unknown): string {
		if (value === null || typeof value !== 'object' || Array.isArray(value)) return '{}'
		return JSON.stringify(value, null, 2)
	}

	function parseJsonObject(value: string): Record<string, unknown> {
		const trimmed = value.trim()
		if (!trimmed) return {}
		const parsed: unknown = JSON.parse(trimmed)
		if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
			throw new Error('expected JSON object')
		}
		return Object.fromEntries(Object.entries(parsed))
	}

	function parseCommaList(value: string): string[] {
		return value
			.split(',')
			.map((s) => s.trim())
			.filter(Boolean)
	}

	function toRerankDefaultStrategy(value: string | undefined): RerankDefaultStrategy {
		if (value === 'none' || value === 'external' || value === 'native') return value
		return 'native'
	}

	function normalizeDefaultPermissions(
		input: DefaultPermissionsSettings
	): DefaultPermissionsSettings {
		return {
			resource_access: {
				thread: input.resource_access?.thread ?? null,
				project: input.resource_access?.project ?? null,
				file: input.resource_access?.file ?? null,
				calendar: input.resource_access?.calendar ?? null,
				note: input.resource_access?.note ?? null,
				group: input.resource_access?.group ?? null,
				reminder_list: input.resource_access?.reminder_list ?? null,
			},
			action_permissions: [...(input.action_permissions ?? [])].sort(),
		}
	}

	function defaultPermissionsKey(value: DefaultPermissionsSettings): string {
		return JSON.stringify(normalizeDefaultPermissions(value))
	}

	function setFromResponse(r: SettingsResponse) {
		response = r
		saveSuccess = null
		saveError = null

		const ui = r.data.ui
		uiDefaultTheme = (ui?.default_theme as ThemeMode) ?? 'system'
		uiDefaultBackground = ui?.default_background ?? null
		uiAuthPagesBackground = ui?.auth_pages_background ?? null
		uiSidebarCollapsed = ui?.sidebar_collapsed ?? false

		const ai = r.data.ai
		aiDefaultAgentIds = ai?.default_agent_ids ?? []

		const memory = ai?.memory
		aiMemoryEnable = memory?.enable_memory ?? false
		aiMemorySimilarityThreshold = toStringOrEmpty(memory?.similarity_threshold)
		aiMemoryTopK = toStringOrEmpty(memory?.top_k)

		const chatContext = ai?.chat_context
		aiChatContextEnabled = chatContext?.enabled ?? true
		aiChatContextMode = (chatContext?.mode ?? 'recent') as ChatContextMode
		aiChatContextTopK = toStringOrEmpty(chatContext?.top_k)
		aiChatContextSimilarityThreshold = toStringOrEmpty(chatContext?.similarity_threshold)
		aiRetrievalTurns = toStringOrEmpty(ai?.retrieval_turns)
		aiRetrievalPreBuild = ai?.retrieval_pre_build ?? true

		const tasks = ai?.tasks
		aiTaskDefaultModelId = tasks?.default_model_id ?? ''
		aiTaskThreadMetadataModelId = tasks?.thread_metadata_model_id ?? ''
		aiTaskThreadMaintenanceModelId = tasks?.thread_maintenance_model_id ?? ''
		aiTaskInputAutocompleteModelId = tasks?.input_autocomplete_model_id ?? ''
		aiTaskSummarizationModelId = tasks?.summarization_model_id ?? ''
		aiTaskMemoryPostProcessingModelId = tasks?.memory_post_processing_model_id ?? ''
		aiTaskWebSearchModelId = tasks?.web_search_model_id ?? ''

		aiTaskMaintenanceMaxCharsPerMessage = toStringOrEmpty(
			tasks?.maintenance_max_chars_per_message
		)

		const attachments = ai?.attachments
		aiAttachmentImageDecayIterations = toStringOrEmpty(attachments?.image_decay_iterations)
		aiAttachmentAudioDecayIterations = toStringOrEmpty(attachments?.audio_decay_iterations)
		aiAttachmentVideoDecayIterations = toStringOrEmpty(attachments?.video_decay_iterations)

		const contextCompaction = ai?.context_compaction
		aiContextCompactionEnabled = contextCompaction?.enabled ?? true
		aiContextCompactionTriggerRatio = toStringOrEmpty(contextCompaction?.trigger_ratio)
		aiContextCompactionRecoveryTargetRatio = toStringOrEmpty(
			contextCompaction?.recovery_target_ratio
		)
		aiContextCompactionTargetUsageCapTokens = toStringOrEmpty(
			contextCompaction?.target_usage_cap_tokens
		)
		aiContextCompactionSummaryBatchMinTokens = toStringOrEmpty(
			contextCompaction?.summary_batch_min_tokens
		)
		aiContextCompactionSummaryBatchMaxTokens = toStringOrEmpty(
			contextCompaction?.summary_batch_max_tokens
		)
		aiContextCompactionPromptOverheadTokens = toStringOrEmpty(
			contextCompaction?.prompt_overhead_tokens
		)
		aiContextCompactionBlockingSummarizationEnabled =
			contextCompaction?.blocking_summarization_enabled ?? true
		aiContextCompactionBlockingSummarizationTimeoutSeconds = toStringOrEmpty(
			contextCompaction?.blocking_summarization_timeout_seconds
		)
		aiContextCompactionToolResultMaxShare = toStringOrEmpty(
			contextCompaction?.tool_result_max_share
		)
		aiContextCompactionToolResultHardCap = toStringOrEmpty(
			contextCompaction?.tool_result_hard_cap
		)
		aiContextCompactionToolResultsCombinedMaxShare = toStringOrEmpty(
			contextCompaction?.tool_results_combined_max_share
		)
		aiContextCompactionResponseHeadroom = toStringOrEmpty(contextCompaction?.response_headroom)

		aiContextCompactionSummarizationMaxCharsPerMessage = toStringOrEmpty(
			contextCompaction?.summarization_max_chars_per_message
		)

		const aiMedia = ai?.media
		const aiMediaImages = aiMedia?.images
		aiMediaImagesEnabled = aiMediaImages?.enabled ?? true
		aiMediaImagesModel = aiMediaImages?.model ?? ''
		aiMediaImagesDefaultSize = toStringOrEmpty(aiMediaImages?.default_size)
		aiMediaImagesDefaultSteps = toStringOrEmpty(aiMediaImages?.default_steps)
		aiMediaImagesDefaultN = toStringOrEmpty(aiMediaImages?.default_n)
		aiMediaImagesMaxN = toStringOrEmpty(aiMediaImages?.max_n)
		aiMediaVideosEnabled = aiMedia?.videos?.enabled ?? false
		aiMediaAudioEnabled = aiMedia?.audio?.enabled ?? false

		const branding = r.data.branding
		brandingSiteName = toStringOrEmpty(branding?.site_name)
		brandingLogoUrl = toStringOrEmpty(branding?.logo_url)
		brandingFaviconUrl = toStringOrEmpty(branding?.favicon_url)
		brandingPrimaryColor = toStringOrEmpty(branding?.primary_color)
		brandingPublicFrontendOrigin = toStringOrEmpty(branding?.public_frontend_origin)
		brandingPublicCdnOrigin = toStringOrEmpty(branding?.public_cdn_origin)
		brandingPublicConsoleOrigin = toStringOrEmpty(branding?.public_console_origin)
		brandingPwaManifestUrl = toStringOrEmpty(branding?.pwa_manifest_url)
		brandingPwaAssets = pwaAssetsFromResponse(branding?.pwa_assets)
		brandingSupportEmail = toStringOrEmpty(branding?.support_email)
		brandingAdminEmail = toStringOrEmpty(branding?.admin_email)

		brandingAppVersion = branding?.app_version ?? ''
		brandingAnalyticsKeyConfigured = Boolean(branding?.analytics_key)

		const media = r.data.media
		const mediaFavicon = toMediaAsset(media?.favicon)
		mediaFaviconSource = mediaFavicon.source
		mediaFaviconUrl = mediaFavicon.url
		const mediaAppleTouchIcon = toMediaAsset(media?.apple_touch_icon)
		mediaAppleTouchIconSource = mediaAppleTouchIcon.source
		mediaAppleTouchIconUrl = mediaAppleTouchIcon.url
		const softDelete = r.data.soft_delete
		softDeleteThreads = softDelete?.threads ?? true
		softDeleteNotes = softDelete?.notes ?? true
		softDeleteFiles = softDelete?.files ?? true
		const notificationSettings = r.data.notifications
		notificationsWebPushEnabled = notificationSettings?.web_push_enabled ?? false
		notificationsWebPushTtlSeconds = toStringOrEmpty(notificationSettings?.web_push_ttl_seconds)
		notificationsNotificationTtlSeconds = toStringOrEmpty(
			notificationSettings?.notification_ttl_seconds
		)
		notificationsMissedGraceDays = toStringOrEmpty(notificationSettings?.missed_grace_days)
		notificationsLookaheadDays = toStringOrEmpty(notificationSettings?.lookahead_days)
		notificationsVapidPublicKey = notificationSettings?.vapid_public_key ?? ''
		notificationsVapidPrivateKey = notificationSettings?.vapid_private_key ?? ''

		const webSearch = r.data.web_search
		webSearchMaxChars = toStringOrEmpty(webSearch?.max_chars)
		const agentic = webSearch?.agentic
		webSearchAgenticAgent = (agentic?.agent ?? 'native') as SearchAgent
		webSearchAgenticModelId = agentic?.model_id ?? ''
		webSearchAgenticSystemPrompt = agentic?.system_prompt ?? ''
		webSearchAgenticModelParams = formatJsonObject(agentic?.model_params)
		webSearchAgenticMaxIterations = toStringOrEmpty(agentic?.max_iterations)
		webSearchBlacklistedDomains = (webSearch?.blacklisted_domains ?? []).join(', ')
		webSearchEngineEngine = (webSearch?.search_engines?.engine ?? 'perplexity') as SearchEngine
		const integrations = r.data.integrations
		const searxng = integrations?.searxng
		webSearchSearxngInstanceUrl = toStringOrEmpty(searxng?.instance_url)
		webSearchSearxngMaxResults = toStringOrEmpty(searxng?.max_results)
		webSearchSearxngMaxConcurrentRequests = toStringOrEmpty(searxng?.max_concurrent_requests)
		webSearchSearxngTimeoutSeconds = toStringOrEmpty(searxng?.timeout_seconds)
		const webLoader = webSearch?.web_loaders
		webSearchWebLoaderEngine = (webLoader?.engine ?? 'native') as WebLoaderEngine
		webSearchWebLoaderTimeoutSeconds = toStringOrEmpty(webLoader?.timeout_seconds)
		webSearchWebLoaderUserAgent = toStringOrEmpty(webLoader?.user_agent)
		webSearchWebLoaderMaxChars = toStringOrEmpty(webLoader?.max_chars)
		const tavily = webLoader?.tavily
		webSearchTavilyExtractDepth = (tavily?.extract_depth ?? 'advanced') as 'basic' | 'advanced'
		webSearchTavilyApiKey = tavily?.api_key ?? ''
		webSearchTavilyMaxConcurrentRequests = toStringOrEmpty(tavily?.max_concurrent_requests)
		const perplexity = integrations?.perplexity
		webSearchPerplexityApiKey = perplexity?.api_key ?? ''
		webSearchPerplexityModel = (perplexity?.model ?? 'sonar') as PerplexityModel
		webSearchPerplexitySearchContextUsage = (perplexity?.search_context_usage ??
			'medium') as SearchContextUsage
		webSearchPerplexityTemperature = toStringOrEmpty(perplexity?.temperature)
		webSearchPerplexityImageResultsEnabled = perplexity?.image_results_enabled ?? false
		webSearchPerplexityMaxConcurrentRequests = toStringOrEmpty(
			perplexity?.max_concurrent_requests
		)

		const ci = r.data.code_interpreter
		codeInterpreterEnabled = ci?.enabled ?? true
		codeInterpreterEngine = (ci?.engine ?? 'e2b') as CodeInterpreterEngine
		codeInterpreterE2bApiKey = ci?.e2b?.api_key ?? ''
		codeInterpreterE2bTemplate = toStringOrEmpty(ci?.e2b?.template)
		codeInterpreterE2bAvailablePackages = (ci?.e2b?.available_packages ?? []).join(', ')
		codeInterpreterTimeout = toStringOrEmpty(ci?.timeout)

		const taskSettings = r.data.tasks
		const taskiq = taskSettings?.taskiq
		taskiqQueueName = taskiq?.queue_name ?? ''
		taskiqResultTtlSeconds = toStringOrEmpty(taskiq?.result_ttl_seconds)
		taskiqMaxConnections = toStringOrEmpty(taskiq?.max_connections)
		taskiqAutoWorkersMax = toStringOrEmpty(taskiq?.auto_workers_max)
		taskiqSchedulePrefix = taskiq?.schedule_prefix ?? ''
		const maintenance = taskSettings?.thread_maintenance
		taskMaintenanceInactivityHours = toStringOrEmpty(maintenance?.inactivity_hours)
		taskMaintenanceQueuedSupersedeAfterMinutes = toStringOrEmpty(
			maintenance?.queued_supersede_after_minutes
		)
		taskMaintenanceActiveSupersedeAfterMinutes = toStringOrEmpty(
			maintenance?.active_supersede_after_minutes
		)
		taskMaintenanceRunnerTimeoutSeconds = toStringOrEmpty(maintenance?.runner_timeout_seconds)
		taskMaintenanceStaleTaskCleanupAfterMinutes = toStringOrEmpty(
			maintenance?.stale_task_cleanup_after_minutes
		)
		const maintenanceBackfill = taskSettings?.maintenance_backfill
		taskMaintenanceBackfillEnabled = maintenanceBackfill?.enabled ?? false
		taskMaintenanceBackfillCron = toStringOrEmpty(maintenanceBackfill?.cron)
		taskMaintenanceBackfillBatchSize = toStringOrEmpty(maintenanceBackfill?.batch_size)
		taskMaintenanceBackfillMaxLookbackDays = toStringOrEmpty(
			maintenanceBackfill?.max_lookback_days
		)
		taskMaintenanceBackfillMinInactivityHours = toStringOrEmpty(
			maintenanceBackfill?.min_inactivity_hours
		)

		const limits = r.data.limits
		limitsMaxThreadsPerUser = toStringOrEmpty(limits?.max_threads_per_user)
		limitsMaxMessagesPerThread = toStringOrEmpty(limits?.max_messages_per_thread)
		limitsMaxChatInputChars = toStringOrEmpty(limits?.max_chat_input_chars)
		limitsMaxFileSizeMb = toStringOrEmpty(limits?.max_file_size_mb)
		limitsRateLimitRequestsPerMinute = toStringOrEmpty(limits?.rate_limit_requests_per_minute)

		const cache = r.data.cache
		cacheAccessibleUsersTtlSeconds = toStringOrEmpty(cache?.accessible_users_ttl_seconds)

		const security = r.data.security
		securityAccessTokenExpireMinutes = toStringOrEmpty(security?.access_token_expire_minutes)
		securityRefreshTokenExpireDays = toStringOrEmpty(security?.refresh_token_expire_days)
		securityAuthCookieSecure = security?.auth_cookie_secure ?? false
		securitySessionTimeoutMinutes = toStringOrEmpty(security?.session_timeout_minutes)
		securityRequireEmailVerification = security?.require_email_verification ?? false
		securityAllowedEmailDomains = (security?.allowed_email_domains ?? []).join(', ')
		securityAllowSignups = security?.allow_signups ?? true
		securityAutoSignupRoleIds = [...(security?.auto_signup_role_ids ?? [])]

		const oidc = security?.oidc
		securityOidcEnabled = oidc?.enabled ?? false
		securityOidcIssuerUrl = toStringOrEmpty(oidc?.issuer_url)
		securityOidcClientId = toStringOrEmpty(oidc?.client_id)
		securityOidcClientSecret = toStringOrEmpty(oidc?.client_secret)
		securityOidcRedirectUri = toStringOrEmpty(oidc?.redirect_uri)
		securityOidcScopes = (oidc?.scopes ?? []).join(', ')
		securityOidcOnly = oidc?.only ?? false

		securitySecretKeyConfigured = Boolean(security?.secret_key)
		securitySecretKeyUsesDefault = security?.secret_key_uses_default ?? false
		securityJwtAlgorithm = security?.jwt_algorithm ?? ''
		securityEnableOauth = toBool(security?.enable_oauth)
		securityCorsOrigins = (security?.cors_origins ?? []).join(', ')

		const assets = r.data.assets
		assetsDefaultEmbeddingModelId = assets?.default_embedding_model_id ?? ''
		const vectorDatabase = assets?.vector_database
		assetsVectorDatabaseProvider =
			(vectorDatabase?.provider as VectorDatabaseProvider) ?? 'qdrant'
		const qdrantVectorDatabase = vectorDatabase?.qdrant
		const chromaVectorDatabase = vectorDatabase?.chroma
		const pineconeVectorDatabase = vectorDatabase?.pinecone
		const weaviateVectorDatabase = vectorDatabase?.weaviate
		const milvusVectorDatabase = vectorDatabase?.milvus
		const pgvectorVectorDatabase = vectorDatabase?.pgvector
		const redisVectorDatabase = vectorDatabase?.redis
		const opensearchVectorDatabase = vectorDatabase?.opensearch
		const activeVectorDatabase =
			assetsVectorDatabaseProvider === 'qdrant'
				? qdrantVectorDatabase
				: assetsVectorDatabaseProvider === 'chroma'
					? chromaVectorDatabase
					: assetsVectorDatabaseProvider === 'pinecone'
						? pineconeVectorDatabase
						: assetsVectorDatabaseProvider === 'weaviate'
							? weaviateVectorDatabase
							: assetsVectorDatabaseProvider === 'milvus'
								? milvusVectorDatabase
								: assetsVectorDatabaseProvider === 'pgvector'
									? pgvectorVectorDatabase
									: assetsVectorDatabaseProvider === 'redis'
										? redisVectorDatabase
										: opensearchVectorDatabase
		assetsVectorDatabaseUrl =
			assetsVectorDatabaseProvider === 'qdrant'
				? toStringOrEmpty(activeVectorDatabase?.url)
				: (activeVectorDatabase?.url ?? '')
		assetsVectorDatabaseQdrantUseGrpc = qdrantVectorDatabase?.use_grpc ?? true
		assetsVectorDatabaseQdrantApiKey = qdrantVectorDatabase?.api_key ?? ''
		assetsVectorDatabaseChromaApiKey = chromaVectorDatabase?.api_key ?? ''
		assetsVectorDatabasePineconeApiKey = pineconeVectorDatabase?.api_key ?? ''
		assetsVectorDatabaseWeaviateApiKey = weaviateVectorDatabase?.api_key ?? ''
		assetsVectorDatabaseMilvusToken = milvusVectorDatabase?.token ?? ''
		assetsVectorDatabaseRedisPassword = redisVectorDatabase?.password ?? ''
		assetsVectorDatabaseOpensearchApiKey = opensearchVectorDatabase?.api_key ?? ''
		const vector = assets?.vector
		assetsVectorCollectionTemplate = toStringOrEmpty(vector?.collection_template)
		assetsVectorSparseEnabled = vector?.sparse_vectors_enabled ?? true
		assetsVectorFusionAlgorithm = vector?.fusion_algorithm ?? 'rrf'
		assetsVectorNormalizeScores = vector?.normalize_scores ?? true
		const embeddings = assets?.embeddings
		assetsEmbeddingsVectorSize = toStringOrEmpty(embeddings?.vector_size)
		assetsEmbeddingsBatchSize = toStringOrEmpty(embeddings?.batch_size)
		const rerank = assets?.rerank
		assetsRerankDefaultStrategy = toRerankDefaultStrategy(rerank?.default_strategy)
		assetsRerankTopK = toStringOrEmpty(rerank?.top_k)

		const storage = assets?.storage
		assetsStorageBackend = (storage?.backend ?? 'local') as StorageBackend
		assetsStorageLocalRootPath = toStringOrEmpty(storage?.local?.root_path)
		assetsStorageS3EndpointUrl = storage?.s3?.endpoint_url ?? ''
		assetsStorageS3Bucket = toStringOrEmpty(storage?.s3?.bucket)
		assetsStorageS3Region = toStringOrEmpty(storage?.s3?.region)
		assetsStorageS3AccessKeyId = storage?.s3?.access_key_id ?? ''
		assetsStorageS3SecretAccessKey = storage?.s3?.secret_access_key ?? ''
		assetsStorageS3Prefix = storage?.s3?.prefix ?? ''
		assetsStorageS3PresignedUrlTtl = toStringOrEmpty(storage?.s3?.presigned_url_ttl)
		assetsStorageS3MultipartThreshold = toStringOrEmpty(storage?.s3?.multipart_threshold)
		assetsStorageS3MultipartChunkSize = toStringOrEmpty(storage?.s3?.multipart_chunk_size)
		assetsStorageS3MaxRetries = toStringOrEmpty(storage?.s3?.max_retries)
		assetsStorageS3RetryMode = (storage?.s3?.retry_mode ?? 'adaptive') as
			| 'legacy'
			| 'standard'
			| 'adaptive'

		const defaults = r.data.default_permissions
		defaultPermissions = normalizeDefaultPermissions(
			defaults ?? { resource_access: {}, action_permissions: [] }
		)

		original = {
			uiDefaultTheme,
			uiDefaultBackground,
			uiAuthPagesBackground,
			uiSidebarCollapsed,
			aiDefaultAgentIds: [...aiDefaultAgentIds],
			aiMemoryEnable,
			aiMemorySimilarityThreshold,
			aiMemoryTopK,
			aiChatContextEnabled,
			aiChatContextMode,
			aiChatContextTopK,
			aiChatContextSimilarityThreshold,
			aiRetrievalTurns,
			aiRetrievalPreBuild,
			aiTaskDefaultModelId,
			aiTaskThreadMetadataModelId,
			aiTaskThreadMaintenanceModelId,
			aiTaskInputAutocompleteModelId,
			aiTaskSummarizationModelId,
			aiTaskMemoryPostProcessingModelId,
			aiTaskWebSearchModelId,
			aiTaskMaintenanceMaxCharsPerMessage,
			aiAttachmentImageDecayIterations,
			aiAttachmentAudioDecayIterations,
			aiAttachmentVideoDecayIterations,
			aiContextCompactionEnabled,
			aiContextCompactionTriggerRatio,
			aiContextCompactionRecoveryTargetRatio,
			aiContextCompactionTargetUsageCapTokens,
			aiContextCompactionSummaryBatchMinTokens,
			aiContextCompactionSummaryBatchMaxTokens,
			aiContextCompactionPromptOverheadTokens,
			aiContextCompactionBlockingSummarizationEnabled,
			aiContextCompactionBlockingSummarizationTimeoutSeconds,
			aiContextCompactionToolResultMaxShare,
			aiContextCompactionToolResultHardCap,
			aiContextCompactionToolResultsCombinedMaxShare,
			aiContextCompactionResponseHeadroom,
			aiContextCompactionSummarizationMaxCharsPerMessage,
			brandingSiteName,
			brandingLogoUrl,
			brandingFaviconUrl,
			brandingPrimaryColor,
			brandingPublicFrontendOrigin,
			brandingPublicCdnOrigin,
			brandingPublicConsoleOrigin,
			brandingPwaManifestUrl,
			brandingPwaAssets: clonePwaAssets(brandingPwaAssets),
			brandingSupportEmail,
			brandingAdminEmail,
			limitsMaxThreadsPerUser,
			limitsMaxMessagesPerThread,
			limitsMaxChatInputChars,
			limitsMaxFileSizeMb,
			limitsRateLimitRequestsPerMinute,
			cacheAccessibleUsersTtlSeconds,
			securityAccessTokenExpireMinutes,
			securityRefreshTokenExpireDays,
			securityAuthCookieSecure,
			securitySessionTimeoutMinutes,
			securityRequireEmailVerification,
			securityAllowedEmailDomains,
			securityAllowSignups,
			securityAutoSignupRoleIds,
			securityOidcEnabled,
			securityOidcIssuerUrl,
			securityOidcClientId,
			securityOidcClientSecret,
			securityOidcRedirectUri,
			securityOidcScopes,
			securityOidcOnly,
			assetsDefaultEmbeddingModelId,
			assetsVectorDatabaseProvider,
			assetsVectorDatabaseUrl,
			assetsVectorDatabaseQdrantUseGrpc,
			assetsVectorDatabaseQdrantApiKey,
			assetsVectorDatabaseChromaApiKey,
			assetsVectorDatabasePineconeApiKey,
			assetsVectorDatabaseWeaviateApiKey,
			assetsVectorDatabaseMilvusToken,
			assetsVectorDatabaseRedisPassword,
			assetsVectorDatabaseOpensearchApiKey,
			assetsVectorCollectionTemplate,
			assetsVectorSparseEnabled,
			assetsVectorFusionAlgorithm,
			assetsVectorNormalizeScores,
			assetsEmbeddingsVectorSize,
			assetsEmbeddingsBatchSize,
			assetsRerankDefaultStrategy,
			assetsRerankTopK,
			assetsStorageBackend,
			assetsStorageLocalRootPath,
			assetsStorageS3EndpointUrl,
			assetsStorageS3Bucket,
			assetsStorageS3Region,
			assetsStorageS3AccessKeyId,
			assetsStorageS3SecretAccessKey,
			assetsStorageS3Prefix,
			assetsStorageS3PresignedUrlTtl,
			assetsStorageS3MultipartThreshold,
			assetsStorageS3MultipartChunkSize,
			assetsStorageS3MaxRetries,
			assetsStorageS3RetryMode,
			mediaFaviconSource,
			mediaFaviconUrl,
			mediaAppleTouchIconSource,
			mediaAppleTouchIconUrl,
			softDeleteThreads,
			softDeleteNotes,
			softDeleteFiles,
			notificationsWebPushEnabled,
			notificationsWebPushTtlSeconds,
			notificationsNotificationTtlSeconds,
			notificationsMissedGraceDays,
			notificationsLookaheadDays,
			notificationsVapidPublicKey,
			notificationsVapidPrivateKey,
			aiMediaImagesEnabled,
			aiMediaImagesModel,
			aiMediaImagesDefaultSize,
			aiMediaImagesDefaultSteps,
			aiMediaImagesDefaultN,
			aiMediaImagesMaxN,
			aiMediaVideosEnabled,
			aiMediaAudioEnabled,
			webSearchMaxChars,
			webSearchAgenticAgent,
			webSearchAgenticModelId,
			webSearchAgenticSystemPrompt,
			webSearchAgenticModelParams,
			webSearchAgenticMaxIterations,
			webSearchBlacklistedDomains,
			webSearchEngineEngine,
			webSearchSearxngInstanceUrl,
			webSearchSearxngMaxResults,
			webSearchSearxngMaxConcurrentRequests,
			webSearchSearxngTimeoutSeconds,
			webSearchWebLoaderEngine,
			webSearchWebLoaderTimeoutSeconds,
			webSearchWebLoaderUserAgent,
			webSearchWebLoaderMaxChars,
			webSearchTavilyExtractDepth,
			webSearchTavilyApiKey,
			webSearchTavilyMaxConcurrentRequests,
			webSearchPerplexityApiKey,
			webSearchPerplexityModel,
			webSearchPerplexitySearchContextUsage,
			webSearchPerplexityTemperature,
			webSearchPerplexityImageResultsEnabled,
			webSearchPerplexityMaxConcurrentRequests,
			codeInterpreterEnabled,
			codeInterpreterEngine,
			codeInterpreterE2bApiKey,
			codeInterpreterE2bTemplate,
			codeInterpreterE2bAvailablePackages,
			codeInterpreterTimeout,
			taskiqQueueName,
			taskiqResultTtlSeconds,
			taskiqMaxConnections,
			taskiqAutoWorkersMax,
			taskiqSchedulePrefix,
			taskMaintenanceInactivityHours,
			taskMaintenanceQueuedSupersedeAfterMinutes,
			taskMaintenanceActiveSupersedeAfterMinutes,
			taskMaintenanceRunnerTimeoutSeconds,
			taskMaintenanceStaleTaskCleanupAfterMinutes,
			taskMaintenanceBackfillEnabled,
			taskMaintenanceBackfillCron,
			taskMaintenanceBackfillBatchSize,
			taskMaintenanceBackfillMaxLookbackDays,
			taskMaintenanceBackfillMinInactivityHours,
			defaultPermissions,
			defaultPermissionsKey: defaultPermissionsKey(defaultPermissions),
		}
	}

	async function fetchSettings() {
		isFetching = true
		error = null
		try {
			const r = unwrap(await api.GET('/v1/settings'))
			setFromResponse(r)
		} catch (e) {
			console.error('Failed to fetch settings', e)
			error = 'failed to load settings'
		} finally {
			isFetching = false
		}
	}

	async function fetchAgents() {
		isFetchingAgents = true
		agentsError = null
		try {
			const list = unwrap(await api.GET('/v1/agents'))
			agents = [...list].sort((a, b) => a.name.localeCompare(b.name))
		} catch (e) {
			console.error('Failed to fetch agents', e)
			agentsError = 'failed to load agents'
		} finally {
			isFetchingAgents = false
		}
	}

	async function fetchModels() {
		isFetchingModels = true
		modelsError = null
		try {
			const list = unwrap(await api.GET('/v1/models'))
			const label = (m: Model) => m.display_name || m.name || m.id
			models = [...list].sort((a, b) => label(a).localeCompare(label(b)))
		} catch (e) {
			console.error('Failed to fetch models', e)
			modelsError = 'failed to load models'
		} finally {
			isFetchingModels = false
		}
	}

	async function fetchProviders() {
		try {
			providers = unwrap(await api.GET('/v1/providers'))
		} catch (e) {
			console.error('Failed to fetch providers', e)
		}
	}

	function resetDraft() {
		uiDefaultTheme = original.uiDefaultTheme
		uiDefaultBackground = original.uiDefaultBackground
		uiAuthPagesBackground = original.uiAuthPagesBackground
		uiSidebarCollapsed = original.uiSidebarCollapsed
		aiDefaultAgentIds = original.aiDefaultAgentIds
		aiMemoryEnable = original.aiMemoryEnable
		aiMemorySimilarityThreshold = original.aiMemorySimilarityThreshold
		aiMemoryTopK = original.aiMemoryTopK
		aiChatContextEnabled = original.aiChatContextEnabled
		aiChatContextMode = original.aiChatContextMode
		aiChatContextTopK = original.aiChatContextTopK
		aiChatContextSimilarityThreshold = original.aiChatContextSimilarityThreshold
		aiRetrievalTurns = original.aiRetrievalTurns
		aiRetrievalPreBuild = original.aiRetrievalPreBuild
		aiTaskDefaultModelId = original.aiTaskDefaultModelId
		aiTaskThreadMetadataModelId = original.aiTaskThreadMetadataModelId
		aiTaskThreadMaintenanceModelId = original.aiTaskThreadMaintenanceModelId
		aiTaskInputAutocompleteModelId = original.aiTaskInputAutocompleteModelId
		aiTaskSummarizationModelId = original.aiTaskSummarizationModelId
		aiTaskMemoryPostProcessingModelId = original.aiTaskMemoryPostProcessingModelId
		aiTaskWebSearchModelId = original.aiTaskWebSearchModelId
		aiTaskMaintenanceMaxCharsPerMessage = original.aiTaskMaintenanceMaxCharsPerMessage
		aiAttachmentImageDecayIterations = original.aiAttachmentImageDecayIterations
		aiAttachmentAudioDecayIterations = original.aiAttachmentAudioDecayIterations
		aiAttachmentVideoDecayIterations = original.aiAttachmentVideoDecayIterations
		aiContextCompactionEnabled = original.aiContextCompactionEnabled
		aiContextCompactionTriggerRatio = original.aiContextCompactionTriggerRatio
		aiContextCompactionRecoveryTargetRatio = original.aiContextCompactionRecoveryTargetRatio
		aiContextCompactionTargetUsageCapTokens = original.aiContextCompactionTargetUsageCapTokens
		aiContextCompactionSummaryBatchMinTokens = original.aiContextCompactionSummaryBatchMinTokens
		aiContextCompactionSummaryBatchMaxTokens = original.aiContextCompactionSummaryBatchMaxTokens
		aiContextCompactionPromptOverheadTokens = original.aiContextCompactionPromptOverheadTokens
		aiContextCompactionBlockingSummarizationEnabled =
			original.aiContextCompactionBlockingSummarizationEnabled
		aiContextCompactionBlockingSummarizationTimeoutSeconds =
			original.aiContextCompactionBlockingSummarizationTimeoutSeconds
		aiContextCompactionToolResultMaxShare = original.aiContextCompactionToolResultMaxShare
		aiContextCompactionToolResultHardCap = original.aiContextCompactionToolResultHardCap
		aiContextCompactionToolResultsCombinedMaxShare =
			original.aiContextCompactionToolResultsCombinedMaxShare
		aiContextCompactionResponseHeadroom = original.aiContextCompactionResponseHeadroom
		aiContextCompactionSummarizationMaxCharsPerMessage =
			original.aiContextCompactionSummarizationMaxCharsPerMessage
		aiMediaImagesEnabled = original.aiMediaImagesEnabled
		aiMediaImagesModel = original.aiMediaImagesModel
		aiMediaImagesDefaultSize = original.aiMediaImagesDefaultSize
		aiMediaImagesDefaultSteps = original.aiMediaImagesDefaultSteps
		aiMediaImagesDefaultN = original.aiMediaImagesDefaultN
		aiMediaImagesMaxN = original.aiMediaImagesMaxN
		aiMediaVideosEnabled = original.aiMediaVideosEnabled
		aiMediaAudioEnabled = original.aiMediaAudioEnabled
		brandingSiteName = original.brandingSiteName
		brandingLogoUrl = original.brandingLogoUrl
		brandingFaviconUrl = original.brandingFaviconUrl
		brandingPrimaryColor = original.brandingPrimaryColor
		brandingPublicFrontendOrigin = original.brandingPublicFrontendOrigin
		brandingPublicCdnOrigin = original.brandingPublicCdnOrigin
		brandingPublicConsoleOrigin = original.brandingPublicConsoleOrigin
		brandingPwaManifestUrl = original.brandingPwaManifestUrl
		brandingPwaAssets = clonePwaAssets(original.brandingPwaAssets)
		brandingSupportEmail = original.brandingSupportEmail
		brandingAdminEmail = original.brandingAdminEmail
		limitsMaxThreadsPerUser = original.limitsMaxThreadsPerUser
		limitsMaxMessagesPerThread = original.limitsMaxMessagesPerThread
		limitsMaxChatInputChars = original.limitsMaxChatInputChars
		limitsMaxFileSizeMb = original.limitsMaxFileSizeMb
		limitsRateLimitRequestsPerMinute = original.limitsRateLimitRequestsPerMinute
		cacheAccessibleUsersTtlSeconds = original.cacheAccessibleUsersTtlSeconds
		securityAccessTokenExpireMinutes = original.securityAccessTokenExpireMinutes
		securityRefreshTokenExpireDays = original.securityRefreshTokenExpireDays
		securityAuthCookieSecure = original.securityAuthCookieSecure
		securitySessionTimeoutMinutes = original.securitySessionTimeoutMinutes
		securityRequireEmailVerification = original.securityRequireEmailVerification
		securityAllowedEmailDomains = original.securityAllowedEmailDomains
		securityAllowSignups = original.securityAllowSignups
		securityAutoSignupRoleIds = [...original.securityAutoSignupRoleIds]
		securityOidcEnabled = original.securityOidcEnabled
		securityOidcIssuerUrl = original.securityOidcIssuerUrl
		securityOidcClientId = original.securityOidcClientId
		securityOidcClientSecret = original.securityOidcClientSecret
		securityOidcRedirectUri = original.securityOidcRedirectUri
		securityOidcScopes = original.securityOidcScopes
		securityOidcOnly = original.securityOidcOnly
		assetsDefaultEmbeddingModelId = original.assetsDefaultEmbeddingModelId
		assetsVectorDatabaseProvider = original.assetsVectorDatabaseProvider
		assetsVectorDatabaseUrl = original.assetsVectorDatabaseUrl
		assetsVectorDatabaseQdrantUseGrpc = original.assetsVectorDatabaseQdrantUseGrpc
		assetsVectorDatabaseQdrantApiKey = original.assetsVectorDatabaseQdrantApiKey
		assetsVectorDatabaseChromaApiKey = original.assetsVectorDatabaseChromaApiKey
		assetsVectorDatabasePineconeApiKey = original.assetsVectorDatabasePineconeApiKey
		assetsVectorDatabaseWeaviateApiKey = original.assetsVectorDatabaseWeaviateApiKey
		assetsVectorDatabaseMilvusToken = original.assetsVectorDatabaseMilvusToken
		assetsVectorDatabaseRedisPassword = original.assetsVectorDatabaseRedisPassword
		assetsVectorDatabaseOpensearchApiKey = original.assetsVectorDatabaseOpensearchApiKey
		assetsVectorCollectionTemplate = original.assetsVectorCollectionTemplate
		assetsVectorSparseEnabled = original.assetsVectorSparseEnabled
		assetsVectorFusionAlgorithm = original.assetsVectorFusionAlgorithm
		assetsVectorNormalizeScores = original.assetsVectorNormalizeScores
		assetsEmbeddingsVectorSize = original.assetsEmbeddingsVectorSize
		assetsEmbeddingsBatchSize = original.assetsEmbeddingsBatchSize
		assetsRerankDefaultStrategy = original.assetsRerankDefaultStrategy
		assetsRerankTopK = original.assetsRerankTopK
		assetsStorageBackend = original.assetsStorageBackend
		assetsStorageLocalRootPath = original.assetsStorageLocalRootPath
		assetsStorageS3EndpointUrl = original.assetsStorageS3EndpointUrl
		assetsStorageS3Bucket = original.assetsStorageS3Bucket
		assetsStorageS3Region = original.assetsStorageS3Region
		assetsStorageS3AccessKeyId = original.assetsStorageS3AccessKeyId
		assetsStorageS3SecretAccessKey = original.assetsStorageS3SecretAccessKey
		assetsStorageS3Prefix = original.assetsStorageS3Prefix
		assetsStorageS3PresignedUrlTtl = original.assetsStorageS3PresignedUrlTtl
		assetsStorageS3MultipartThreshold = original.assetsStorageS3MultipartThreshold
		assetsStorageS3MultipartChunkSize = original.assetsStorageS3MultipartChunkSize
		assetsStorageS3MaxRetries = original.assetsStorageS3MaxRetries
		assetsStorageS3RetryMode = original.assetsStorageS3RetryMode
		mediaFaviconSource = original.mediaFaviconSource
		mediaFaviconUrl = original.mediaFaviconUrl
		mediaAppleTouchIconSource = original.mediaAppleTouchIconSource
		mediaAppleTouchIconUrl = original.mediaAppleTouchIconUrl
		softDeleteThreads = original.softDeleteThreads
		softDeleteNotes = original.softDeleteNotes
		softDeleteFiles = original.softDeleteFiles
		notificationsWebPushEnabled = original.notificationsWebPushEnabled
		notificationsWebPushTtlSeconds = original.notificationsWebPushTtlSeconds
		notificationsNotificationTtlSeconds = original.notificationsNotificationTtlSeconds
		notificationsMissedGraceDays = original.notificationsMissedGraceDays
		notificationsLookaheadDays = original.notificationsLookaheadDays
		notificationsVapidPublicKey = original.notificationsVapidPublicKey
		notificationsVapidPrivateKey = original.notificationsVapidPrivateKey
		webSearchMaxChars = original.webSearchMaxChars
		webSearchAgenticAgent = original.webSearchAgenticAgent
		webSearchAgenticModelId = original.webSearchAgenticModelId
		webSearchAgenticSystemPrompt = original.webSearchAgenticSystemPrompt
		webSearchAgenticModelParams = original.webSearchAgenticModelParams
		webSearchAgenticMaxIterations = original.webSearchAgenticMaxIterations
		webSearchBlacklistedDomains = original.webSearchBlacklistedDomains
		webSearchEngineEngine = original.webSearchEngineEngine
		webSearchSearxngInstanceUrl = original.webSearchSearxngInstanceUrl
		webSearchSearxngMaxResults = original.webSearchSearxngMaxResults
		webSearchSearxngMaxConcurrentRequests = original.webSearchSearxngMaxConcurrentRequests
		webSearchSearxngTimeoutSeconds = original.webSearchSearxngTimeoutSeconds
		webSearchWebLoaderEngine = original.webSearchWebLoaderEngine
		webSearchWebLoaderTimeoutSeconds = original.webSearchWebLoaderTimeoutSeconds
		webSearchWebLoaderUserAgent = original.webSearchWebLoaderUserAgent
		webSearchWebLoaderMaxChars = original.webSearchWebLoaderMaxChars
		webSearchTavilyExtractDepth = original.webSearchTavilyExtractDepth
		webSearchTavilyApiKey = original.webSearchTavilyApiKey
		webSearchTavilyMaxConcurrentRequests = original.webSearchTavilyMaxConcurrentRequests
		webSearchPerplexityApiKey = original.webSearchPerplexityApiKey
		webSearchPerplexityModel = original.webSearchPerplexityModel
		webSearchPerplexitySearchContextUsage = original.webSearchPerplexitySearchContextUsage
		webSearchPerplexityTemperature = original.webSearchPerplexityTemperature
		webSearchPerplexityImageResultsEnabled = original.webSearchPerplexityImageResultsEnabled
		webSearchPerplexityMaxConcurrentRequests = original.webSearchPerplexityMaxConcurrentRequests
		codeInterpreterEnabled = original.codeInterpreterEnabled
		codeInterpreterEngine = original.codeInterpreterEngine
		codeInterpreterE2bApiKey = original.codeInterpreterE2bApiKey
		codeInterpreterE2bTemplate = original.codeInterpreterE2bTemplate
		codeInterpreterE2bAvailablePackages = original.codeInterpreterE2bAvailablePackages
		codeInterpreterTimeout = original.codeInterpreterTimeout
		taskiqQueueName = original.taskiqQueueName
		taskiqResultTtlSeconds = original.taskiqResultTtlSeconds
		taskiqMaxConnections = original.taskiqMaxConnections
		taskiqAutoWorkersMax = original.taskiqAutoWorkersMax
		taskiqSchedulePrefix = original.taskiqSchedulePrefix
		taskMaintenanceInactivityHours = original.taskMaintenanceInactivityHours
		taskMaintenanceQueuedSupersedeAfterMinutes =
			original.taskMaintenanceQueuedSupersedeAfterMinutes
		taskMaintenanceActiveSupersedeAfterMinutes =
			original.taskMaintenanceActiveSupersedeAfterMinutes
		taskMaintenanceRunnerTimeoutSeconds = original.taskMaintenanceRunnerTimeoutSeconds
		taskMaintenanceStaleTaskCleanupAfterMinutes =
			original.taskMaintenanceStaleTaskCleanupAfterMinutes
		taskMaintenanceBackfillEnabled = original.taskMaintenanceBackfillEnabled
		taskMaintenanceBackfillCron = original.taskMaintenanceBackfillCron
		taskMaintenanceBackfillBatchSize = original.taskMaintenanceBackfillBatchSize
		taskMaintenanceBackfillMaxLookbackDays = original.taskMaintenanceBackfillMaxLookbackDays
		taskMaintenanceBackfillMinInactivityHours =
			original.taskMaintenanceBackfillMinInactivityHours
		defaultPermissions = normalizeDefaultPermissions(original.defaultPermissions)
		saveError = null
		saveSuccess = null
	}

	function buildDefaultPermissionsPatch(): DefaultPermissionsSettingsPatch {
		return {
			resource_access: {
				thread: defaultPermissions.resource_access?.thread ?? null,
				project: defaultPermissions.resource_access?.project ?? null,
				file: defaultPermissions.resource_access?.file ?? null,
				calendar: defaultPermissions.resource_access?.calendar ?? null,
				note: defaultPermissions.resource_access?.note ?? null,
				group: defaultPermissions.resource_access?.group ?? null,
				reminder_list: defaultPermissions.resource_access?.reminder_list ?? null,
			},
			action_permissions: defaultPermissions.action_permissions ?? [],
		}
	}

	function buildUpdateRequest(): SettingsUpdateRequest {
		const data: SettingsPatch = {}

		if (
			uiDefaultTheme !== original.uiDefaultTheme ||
			uiDefaultBackground !== original.uiDefaultBackground ||
			uiAuthPagesBackground !== original.uiAuthPagesBackground ||
			uiSidebarCollapsed !== original.uiSidebarCollapsed
		) {
			data.ui = {}
			if (uiDefaultTheme !== original.uiDefaultTheme) data.ui.default_theme = uiDefaultTheme
			if (uiDefaultBackground !== original.uiDefaultBackground)
				data.ui.default_background = uiDefaultBackground ?? 'none'
			if (uiAuthPagesBackground !== original.uiAuthPagesBackground)
				data.ui.auth_pages_background = uiAuthPagesBackground ?? 'none'
			if (uiSidebarCollapsed !== original.uiSidebarCollapsed)
				data.ui.sidebar_collapsed = uiSidebarCollapsed
		}

		if (
			JSON.stringify(aiDefaultAgentIds) !== JSON.stringify(original.aiDefaultAgentIds) ||
			aiMemoryEnable !== original.aiMemoryEnable ||
			aiMemorySimilarityThreshold !== original.aiMemorySimilarityThreshold ||
			aiMemoryTopK !== original.aiMemoryTopK ||
			aiChatContextEnabled !== original.aiChatContextEnabled ||
			aiChatContextMode !== original.aiChatContextMode ||
			aiChatContextTopK !== original.aiChatContextTopK ||
			aiChatContextSimilarityThreshold !== original.aiChatContextSimilarityThreshold ||
			aiRetrievalTurns !== original.aiRetrievalTurns ||
			aiRetrievalPreBuild !== original.aiRetrievalPreBuild ||
			aiTaskDefaultModelId !== original.aiTaskDefaultModelId ||
			aiTaskThreadMetadataModelId !== original.aiTaskThreadMetadataModelId ||
			aiTaskThreadMaintenanceModelId !== original.aiTaskThreadMaintenanceModelId ||
			aiTaskInputAutocompleteModelId !== original.aiTaskInputAutocompleteModelId ||
			aiTaskSummarizationModelId !== original.aiTaskSummarizationModelId ||
			aiTaskMemoryPostProcessingModelId !== original.aiTaskMemoryPostProcessingModelId ||
			aiTaskWebSearchModelId !== original.aiTaskWebSearchModelId ||
			aiTaskMaintenanceMaxCharsPerMessage !== original.aiTaskMaintenanceMaxCharsPerMessage ||
			aiAttachmentImageDecayIterations !== original.aiAttachmentImageDecayIterations ||
			aiAttachmentAudioDecayIterations !== original.aiAttachmentAudioDecayIterations ||
			aiAttachmentVideoDecayIterations !== original.aiAttachmentVideoDecayIterations ||
			aiContextCompactionEnabled !== original.aiContextCompactionEnabled ||
			aiContextCompactionTriggerRatio !== original.aiContextCompactionTriggerRatio ||
			aiContextCompactionRecoveryTargetRatio !==
				original.aiContextCompactionRecoveryTargetRatio ||
			aiContextCompactionTargetUsageCapTokens !==
				original.aiContextCompactionTargetUsageCapTokens ||
			aiContextCompactionSummaryBatchMinTokens !==
				original.aiContextCompactionSummaryBatchMinTokens ||
			aiContextCompactionSummaryBatchMaxTokens !==
				original.aiContextCompactionSummaryBatchMaxTokens ||
			aiContextCompactionPromptOverheadTokens !==
				original.aiContextCompactionPromptOverheadTokens ||
			aiContextCompactionBlockingSummarizationEnabled !==
				original.aiContextCompactionBlockingSummarizationEnabled ||
			aiContextCompactionBlockingSummarizationTimeoutSeconds !==
				original.aiContextCompactionBlockingSummarizationTimeoutSeconds ||
			aiContextCompactionToolResultMaxShare !==
				original.aiContextCompactionToolResultMaxShare ||
			aiContextCompactionToolResultHardCap !==
				original.aiContextCompactionToolResultHardCap ||
			aiContextCompactionToolResultsCombinedMaxShare !==
				original.aiContextCompactionToolResultsCombinedMaxShare ||
			aiContextCompactionResponseHeadroom !== original.aiContextCompactionResponseHeadroom ||
			aiContextCompactionSummarizationMaxCharsPerMessage !==
				original.aiContextCompactionSummarizationMaxCharsPerMessage ||
			aiMediaImagesEnabled !== original.aiMediaImagesEnabled ||
			aiMediaImagesModel !== original.aiMediaImagesModel ||
			aiMediaImagesDefaultSize !== original.aiMediaImagesDefaultSize ||
			aiMediaImagesDefaultSteps !== original.aiMediaImagesDefaultSteps ||
			aiMediaImagesDefaultN !== original.aiMediaImagesDefaultN ||
			aiMediaImagesMaxN !== original.aiMediaImagesMaxN ||
			aiMediaVideosEnabled !== original.aiMediaVideosEnabled ||
			aiMediaAudioEnabled !== original.aiMediaAudioEnabled
		) {
			const aiPatch: AISettingsPatch = {}
			if (JSON.stringify(aiDefaultAgentIds) !== JSON.stringify(original.aiDefaultAgentIds))
				aiPatch.default_agent_ids = aiDefaultAgentIds

			if (
				aiMemoryEnable !== original.aiMemoryEnable ||
				aiMemorySimilarityThreshold !== original.aiMemorySimilarityThreshold ||
				aiMemoryTopK !== original.aiMemoryTopK
			) {
				aiPatch.memory = {}
				if (aiMemoryEnable !== original.aiMemoryEnable)
					aiPatch.memory.enable_memory = aiMemoryEnable
				if (aiMemorySimilarityThreshold !== original.aiMemorySimilarityThreshold)
					aiPatch.memory.similarity_threshold = asNumberOrUndefined(
						aiMemorySimilarityThreshold
					)
				if (aiMemoryTopK !== original.aiMemoryTopK)
					aiPatch.memory.top_k = asNumberOrUndefined(aiMemoryTopK)
			}

			if (
				aiChatContextEnabled !== original.aiChatContextEnabled ||
				aiChatContextMode !== original.aiChatContextMode ||
				aiChatContextTopK !== original.aiChatContextTopK ||
				aiChatContextSimilarityThreshold !== original.aiChatContextSimilarityThreshold
			) {
				aiPatch.chat_context = {}
				if (aiChatContextEnabled !== original.aiChatContextEnabled)
					aiPatch.chat_context.enabled = aiChatContextEnabled
				if (aiChatContextMode !== original.aiChatContextMode)
					aiPatch.chat_context.mode = aiChatContextMode
				if (aiChatContextTopK !== original.aiChatContextTopK)
					aiPatch.chat_context.top_k = asNumberOrUndefined(aiChatContextTopK)
				if (aiChatContextSimilarityThreshold !== original.aiChatContextSimilarityThreshold)
					aiPatch.chat_context.similarity_threshold = asNumberOrUndefined(
						aiChatContextSimilarityThreshold
					)
			}
			if (aiRetrievalTurns !== original.aiRetrievalTurns)
				aiPatch.retrieval_turns = asNumberOrUndefined(aiRetrievalTurns)
			if (aiRetrievalPreBuild !== original.aiRetrievalPreBuild)
				aiPatch.retrieval_pre_build = aiRetrievalPreBuild

			if (
				aiTaskDefaultModelId !== original.aiTaskDefaultModelId ||
				aiTaskThreadMetadataModelId !== original.aiTaskThreadMetadataModelId ||
				aiTaskThreadMaintenanceModelId !== original.aiTaskThreadMaintenanceModelId ||
				aiTaskInputAutocompleteModelId !== original.aiTaskInputAutocompleteModelId ||
				aiTaskSummarizationModelId !== original.aiTaskSummarizationModelId ||
				aiTaskMemoryPostProcessingModelId !== original.aiTaskMemoryPostProcessingModelId ||
				aiTaskWebSearchModelId !== original.aiTaskWebSearchModelId ||
				aiTaskMaintenanceMaxCharsPerMessage !== original.aiTaskMaintenanceMaxCharsPerMessage
			) {
				aiPatch.tasks = {}
				if (aiTaskDefaultModelId !== original.aiTaskDefaultModelId)
					aiPatch.tasks.default_model_id = aiTaskDefaultModelId
						? aiTaskDefaultModelId
						: null
				if (aiTaskThreadMetadataModelId !== original.aiTaskThreadMetadataModelId)
					aiPatch.tasks.thread_metadata_model_id = aiTaskThreadMetadataModelId
						? aiTaskThreadMetadataModelId
						: null
				if (aiTaskThreadMaintenanceModelId !== original.aiTaskThreadMaintenanceModelId)
					aiPatch.tasks.thread_maintenance_model_id = aiTaskThreadMaintenanceModelId
						? aiTaskThreadMaintenanceModelId
						: null
				if (aiTaskInputAutocompleteModelId !== original.aiTaskInputAutocompleteModelId)
					aiPatch.tasks.input_autocomplete_model_id = aiTaskInputAutocompleteModelId
						? aiTaskInputAutocompleteModelId
						: null
				if (aiTaskSummarizationModelId !== original.aiTaskSummarizationModelId)
					aiPatch.tasks.summarization_model_id = aiTaskSummarizationModelId
						? aiTaskSummarizationModelId
						: null
				if (
					aiTaskMemoryPostProcessingModelId !== original.aiTaskMemoryPostProcessingModelId
				) {
					aiPatch.tasks.memory_post_processing_model_id =
						aiTaskMemoryPostProcessingModelId ? aiTaskMemoryPostProcessingModelId : null
				}
				if (aiTaskWebSearchModelId !== original.aiTaskWebSearchModelId)
					aiPatch.tasks.web_search_model_id = aiTaskWebSearchModelId
						? aiTaskWebSearchModelId
						: null
				if (
					aiTaskMaintenanceMaxCharsPerMessage !==
					original.aiTaskMaintenanceMaxCharsPerMessage
				) {
					aiPatch.tasks.maintenance_max_chars_per_message = asNumberOrNull(
						aiTaskMaintenanceMaxCharsPerMessage
					)
				}
			}

			if (
				aiAttachmentImageDecayIterations !== original.aiAttachmentImageDecayIterations ||
				aiAttachmentAudioDecayIterations !== original.aiAttachmentAudioDecayIterations ||
				aiAttachmentVideoDecayIterations !== original.aiAttachmentVideoDecayIterations
			) {
				aiPatch.attachments = {}
				if (aiAttachmentImageDecayIterations !== original.aiAttachmentImageDecayIterations)
					aiPatch.attachments.image_decay_iterations = asNumberOrUndefined(
						aiAttachmentImageDecayIterations
					)
				if (aiAttachmentAudioDecayIterations !== original.aiAttachmentAudioDecayIterations)
					aiPatch.attachments.audio_decay_iterations = asNumberOrUndefined(
						aiAttachmentAudioDecayIterations
					)
				if (aiAttachmentVideoDecayIterations !== original.aiAttachmentVideoDecayIterations)
					aiPatch.attachments.video_decay_iterations = asNumberOrUndefined(
						aiAttachmentVideoDecayIterations
					)
			}

			if (
				aiContextCompactionEnabled !== original.aiContextCompactionEnabled ||
				aiContextCompactionTriggerRatio !== original.aiContextCompactionTriggerRatio ||
				aiContextCompactionRecoveryTargetRatio !==
					original.aiContextCompactionRecoveryTargetRatio ||
				aiContextCompactionSummaryBatchMinTokens !==
					original.aiContextCompactionSummaryBatchMinTokens ||
				aiContextCompactionSummaryBatchMaxTokens !==
					original.aiContextCompactionSummaryBatchMaxTokens ||
				aiContextCompactionPromptOverheadTokens !==
					original.aiContextCompactionPromptOverheadTokens ||
				aiContextCompactionBlockingSummarizationEnabled !==
					original.aiContextCompactionBlockingSummarizationEnabled ||
				aiContextCompactionBlockingSummarizationTimeoutSeconds !==
					original.aiContextCompactionBlockingSummarizationTimeoutSeconds ||
				aiContextCompactionToolResultMaxShare !==
					original.aiContextCompactionToolResultMaxShare ||
				aiContextCompactionToolResultHardCap !==
					original.aiContextCompactionToolResultHardCap ||
				aiContextCompactionToolResultsCombinedMaxShare !==
					original.aiContextCompactionToolResultsCombinedMaxShare ||
				aiContextCompactionResponseHeadroom !==
					original.aiContextCompactionResponseHeadroom ||
				aiContextCompactionSummarizationMaxCharsPerMessage !==
					original.aiContextCompactionSummarizationMaxCharsPerMessage
			) {
				aiPatch.context_compaction = {}
				if (aiContextCompactionEnabled !== original.aiContextCompactionEnabled)
					aiPatch.context_compaction.enabled = aiContextCompactionEnabled
				if (aiContextCompactionTriggerRatio !== original.aiContextCompactionTriggerRatio)
					aiPatch.context_compaction.trigger_ratio = asNumberOrUndefined(
						aiContextCompactionTriggerRatio
					)
				if (
					aiContextCompactionRecoveryTargetRatio !==
					original.aiContextCompactionRecoveryTargetRatio
				)
					aiPatch.context_compaction.recovery_target_ratio = asNumberOrUndefined(
						aiContextCompactionRecoveryTargetRatio
					)
				if (
					aiContextCompactionTargetUsageCapTokens !==
					original.aiContextCompactionTargetUsageCapTokens
				) {
					aiPatch.context_compaction.target_usage_cap_tokens = asNumberOrNull(
						aiContextCompactionTargetUsageCapTokens
					)
				}
				if (
					aiContextCompactionSummaryBatchMinTokens !==
					original.aiContextCompactionSummaryBatchMinTokens
				)
					aiPatch.context_compaction.summary_batch_min_tokens = asNumberOrUndefined(
						aiContextCompactionSummaryBatchMinTokens
					)
				if (
					aiContextCompactionSummaryBatchMaxTokens !==
					original.aiContextCompactionSummaryBatchMaxTokens
				)
					aiPatch.context_compaction.summary_batch_max_tokens = asNumberOrUndefined(
						aiContextCompactionSummaryBatchMaxTokens
					)
				if (
					aiContextCompactionPromptOverheadTokens !==
					original.aiContextCompactionPromptOverheadTokens
				) {
					aiPatch.context_compaction.prompt_overhead_tokens = asNumberOrUndefined(
						aiContextCompactionPromptOverheadTokens
					)
				}
				if (
					aiContextCompactionBlockingSummarizationEnabled !==
					original.aiContextCompactionBlockingSummarizationEnabled
				) {
					aiPatch.context_compaction.blocking_summarization_enabled =
						aiContextCompactionBlockingSummarizationEnabled
				}
				if (
					aiContextCompactionBlockingSummarizationTimeoutSeconds !==
					original.aiContextCompactionBlockingSummarizationTimeoutSeconds
				) {
					aiPatch.context_compaction.blocking_summarization_timeout_seconds =
						asNumberOrUndefined(aiContextCompactionBlockingSummarizationTimeoutSeconds)
				}
				if (
					aiContextCompactionToolResultMaxShare !==
					original.aiContextCompactionToolResultMaxShare
				)
					aiPatch.context_compaction.tool_result_max_share = asNumberOrUndefined(
						aiContextCompactionToolResultMaxShare
					)
				if (
					aiContextCompactionToolResultHardCap !==
					original.aiContextCompactionToolResultHardCap
				)
					aiPatch.context_compaction.tool_result_hard_cap = asNumberOrUndefined(
						aiContextCompactionToolResultHardCap
					)
				if (
					aiContextCompactionToolResultsCombinedMaxShare !==
					original.aiContextCompactionToolResultsCombinedMaxShare
				)
					aiPatch.context_compaction.tool_results_combined_max_share =
						asNumberOrUndefined(aiContextCompactionToolResultsCombinedMaxShare)
				if (
					aiContextCompactionResponseHeadroom !==
					original.aiContextCompactionResponseHeadroom
				)
					aiPatch.context_compaction.response_headroom = asNumberOrUndefined(
						aiContextCompactionResponseHeadroom
					)
				if (
					aiContextCompactionSummarizationMaxCharsPerMessage !==
					original.aiContextCompactionSummarizationMaxCharsPerMessage
				) {
					aiPatch.context_compaction.summarization_max_chars_per_message = asNumberOrNull(
						aiContextCompactionSummarizationMaxCharsPerMessage
					)
				}
			}

			if (
				aiMediaImagesEnabled !== original.aiMediaImagesEnabled ||
				aiMediaImagesModel !== original.aiMediaImagesModel ||
				aiMediaImagesDefaultSize !== original.aiMediaImagesDefaultSize ||
				aiMediaImagesDefaultSteps !== original.aiMediaImagesDefaultSteps ||
				aiMediaImagesDefaultN !== original.aiMediaImagesDefaultN ||
				aiMediaImagesMaxN !== original.aiMediaImagesMaxN ||
				aiMediaVideosEnabled !== original.aiMediaVideosEnabled ||
				aiMediaAudioEnabled !== original.aiMediaAudioEnabled
			) {
				const mediaPatch: AIMediaSettingsPatch = {}
				if (
					aiMediaImagesEnabled !== original.aiMediaImagesEnabled ||
					aiMediaImagesModel !== original.aiMediaImagesModel ||
					aiMediaImagesDefaultSize !== original.aiMediaImagesDefaultSize ||
					aiMediaImagesDefaultSteps !== original.aiMediaImagesDefaultSteps ||
					aiMediaImagesDefaultN !== original.aiMediaImagesDefaultN ||
					aiMediaImagesMaxN !== original.aiMediaImagesMaxN
				) {
					const imagesPatch: ImageGenerationSettingsPatch = {}
					if (aiMediaImagesEnabled !== original.aiMediaImagesEnabled)
						imagesPatch.enabled = aiMediaImagesEnabled
					if (aiMediaImagesModel !== original.aiMediaImagesModel)
						imagesPatch.model = aiMediaImagesModel || null
					if (aiMediaImagesDefaultSize !== original.aiMediaImagesDefaultSize)
						imagesPatch.default_size = aiMediaImagesDefaultSize || undefined
					if (aiMediaImagesDefaultSteps !== original.aiMediaImagesDefaultSteps)
						imagesPatch.default_steps = asNumberOrNull(aiMediaImagesDefaultSteps)
					if (aiMediaImagesDefaultN !== original.aiMediaImagesDefaultN)
						imagesPatch.default_n = asNumberOrUndefined(aiMediaImagesDefaultN)
					if (aiMediaImagesMaxN !== original.aiMediaImagesMaxN)
						imagesPatch.max_n = asNumberOrUndefined(aiMediaImagesMaxN)
					mediaPatch.images = imagesPatch
				}
				if (aiMediaVideosEnabled !== original.aiMediaVideosEnabled)
					mediaPatch.videos = { enabled: aiMediaVideosEnabled }
				if (aiMediaAudioEnabled !== original.aiMediaAudioEnabled)
					mediaPatch.audio = { enabled: aiMediaAudioEnabled }
				aiPatch.media = mediaPatch
			}

			data.ai = aiPatch
		}

		if (
			brandingSiteName !== original.brandingSiteName ||
			brandingLogoUrl !== original.brandingLogoUrl ||
			brandingFaviconUrl !== original.brandingFaviconUrl ||
			brandingPrimaryColor !== original.brandingPrimaryColor ||
			brandingPublicFrontendOrigin !== original.brandingPublicFrontendOrigin ||
			brandingPublicCdnOrigin !== original.brandingPublicCdnOrigin ||
			brandingPublicConsoleOrigin !== original.brandingPublicConsoleOrigin ||
			brandingPwaManifestUrl !== original.brandingPwaManifestUrl ||
			pwaAssetsKey(brandingPwaAssets) !== pwaAssetsKey(original.brandingPwaAssets) ||
			brandingSupportEmail !== original.brandingSupportEmail ||
			brandingAdminEmail !== original.brandingAdminEmail
		) {
			data.branding = {}
			if (brandingSiteName !== original.brandingSiteName)
				data.branding.site_name = brandingSiteName
			if (brandingLogoUrl !== original.brandingLogoUrl)
				data.branding.logo_url = brandingLogoUrl || null
			if (brandingFaviconUrl !== original.brandingFaviconUrl)
				data.branding.favicon_url = brandingFaviconUrl || null
			if (brandingPrimaryColor !== original.brandingPrimaryColor)
				data.branding.primary_color = brandingPrimaryColor
			if (brandingPublicFrontendOrigin !== original.brandingPublicFrontendOrigin)
				data.branding.public_frontend_origin = brandingPublicFrontendOrigin || null
			if (brandingPublicCdnOrigin !== original.brandingPublicCdnOrigin)
				data.branding.public_cdn_origin = brandingPublicCdnOrigin || null
			if (brandingPublicConsoleOrigin !== original.brandingPublicConsoleOrigin)
				data.branding.public_console_origin = brandingPublicConsoleOrigin || null
			if (brandingPwaManifestUrl !== original.brandingPwaManifestUrl)
				data.branding.pwa_manifest_url = brandingPwaManifestUrl || null
			if (pwaAssetsKey(brandingPwaAssets) !== pwaAssetsKey(original.brandingPwaAssets))
				data.branding.pwa_assets = pwaAssetsToPatch(brandingPwaAssets)
			if (brandingSupportEmail !== original.brandingSupportEmail)
				data.branding.support_email = brandingSupportEmail || null
			if (brandingAdminEmail !== original.brandingAdminEmail)
				data.branding.admin_email = brandingAdminEmail || null
		}

		if (
			limitsMaxThreadsPerUser !== original.limitsMaxThreadsPerUser ||
			limitsMaxMessagesPerThread !== original.limitsMaxMessagesPerThread ||
			limitsMaxChatInputChars !== original.limitsMaxChatInputChars ||
			limitsMaxFileSizeMb !== original.limitsMaxFileSizeMb ||
			limitsRateLimitRequestsPerMinute !== original.limitsRateLimitRequestsPerMinute
		) {
			data.limits = {}
			if (limitsMaxThreadsPerUser !== original.limitsMaxThreadsPerUser)
				data.limits.max_threads_per_user = asNumberOrUndefined(limitsMaxThreadsPerUser)
			if (limitsMaxMessagesPerThread !== original.limitsMaxMessagesPerThread)
				data.limits.max_messages_per_thread = asNumberOrUndefined(
					limitsMaxMessagesPerThread
				)
			if (limitsMaxChatInputChars !== original.limitsMaxChatInputChars)
				data.limits.max_chat_input_chars = asNumberOrNull(limitsMaxChatInputChars)
			if (limitsMaxFileSizeMb !== original.limitsMaxFileSizeMb)
				data.limits.max_file_size_mb = asNumberOrUndefined(limitsMaxFileSizeMb)
			if (limitsRateLimitRequestsPerMinute !== original.limitsRateLimitRequestsPerMinute)
				data.limits.rate_limit_requests_per_minute = asNumberOrUndefined(
					limitsRateLimitRequestsPerMinute
				)
		}

		if (cacheAccessibleUsersTtlSeconds !== original.cacheAccessibleUsersTtlSeconds) {
			const cachePatch: CacheSettingsPatch = {}
			cachePatch.accessible_users_ttl_seconds = asNumberOrUndefined(
				cacheAccessibleUsersTtlSeconds
			)
			data.cache = cachePatch
		}

		if (
			securityAccessTokenExpireMinutes !== original.securityAccessTokenExpireMinutes ||
			securityRefreshTokenExpireDays !== original.securityRefreshTokenExpireDays ||
			securityAuthCookieSecure !== original.securityAuthCookieSecure ||
			securitySessionTimeoutMinutes !== original.securitySessionTimeoutMinutes ||
			securityRequireEmailVerification !== original.securityRequireEmailVerification ||
			securityAllowedEmailDomains !== original.securityAllowedEmailDomains ||
			securityAllowSignups !== original.securityAllowSignups ||
			!arrayEquals(securityAutoSignupRoleIds, original.securityAutoSignupRoleIds) ||
			securityOidcEnabled !== original.securityOidcEnabled ||
			securityOidcIssuerUrl !== original.securityOidcIssuerUrl ||
			securityOidcClientId !== original.securityOidcClientId ||
			securityOidcClientSecret !== original.securityOidcClientSecret ||
			securityOidcRedirectUri !== original.securityOidcRedirectUri ||
			securityOidcScopes !== original.securityOidcScopes ||
			securityOidcOnly !== original.securityOidcOnly
		) {
			data.security = {}
			if (securityAccessTokenExpireMinutes !== original.securityAccessTokenExpireMinutes)
				data.security.access_token_expire_minutes = asNumberOrUndefined(
					securityAccessTokenExpireMinutes
				)
			if (securityRefreshTokenExpireDays !== original.securityRefreshTokenExpireDays)
				data.security.refresh_token_expire_days = asNumberOrUndefined(
					securityRefreshTokenExpireDays
				)
			if (securityAuthCookieSecure !== original.securityAuthCookieSecure)
				data.security.auth_cookie_secure = securityAuthCookieSecure
			if (securitySessionTimeoutMinutes !== original.securitySessionTimeoutMinutes)
				data.security.session_timeout_minutes = asNumberOrUndefined(
					securitySessionTimeoutMinutes
				)
			if (securityRequireEmailVerification !== original.securityRequireEmailVerification)
				data.security.require_email_verification = securityRequireEmailVerification
			if (securityAllowedEmailDomains !== original.securityAllowedEmailDomains)
				data.security.allowed_email_domains = parseCommaList(securityAllowedEmailDomains)
			if (securityAllowSignups !== original.securityAllowSignups)
				data.security.allow_signups = securityAllowSignups
			if (!arrayEquals(securityAutoSignupRoleIds, original.securityAutoSignupRoleIds))
				data.security.auto_signup_role_ids = securityAutoSignupRoleIds

			if (
				securityOidcEnabled !== original.securityOidcEnabled ||
				securityOidcIssuerUrl !== original.securityOidcIssuerUrl ||
				securityOidcClientId !== original.securityOidcClientId ||
				securityOidcClientSecret !== original.securityOidcClientSecret ||
				securityOidcRedirectUri !== original.securityOidcRedirectUri ||
				securityOidcScopes !== original.securityOidcScopes ||
				securityOidcOnly !== original.securityOidcOnly
			) {
				data.security.oidc = {}
				if (securityOidcEnabled !== original.securityOidcEnabled)
					data.security.oidc.enabled = securityOidcEnabled
				if (securityOidcIssuerUrl !== original.securityOidcIssuerUrl)
					data.security.oidc.issuer_url = securityOidcIssuerUrl || null
				if (securityOidcClientId !== original.securityOidcClientId)
					data.security.oidc.client_id = securityOidcClientId || null
				if (securityOidcClientSecret !== original.securityOidcClientSecret)
					data.security.oidc.client_secret = securityOidcClientSecret || null
				if (securityOidcRedirectUri !== original.securityOidcRedirectUri)
					data.security.oidc.redirect_uri = securityOidcRedirectUri || null
				if (securityOidcScopes !== original.securityOidcScopes)
					data.security.oidc.scopes = parseCommaList(securityOidcScopes)
				if (securityOidcOnly !== original.securityOidcOnly)
					data.security.oidc.only = securityOidcOnly
			}
		}

		if (
			assetsDefaultEmbeddingModelId !== original.assetsDefaultEmbeddingModelId ||
			assetsVectorDatabaseProvider !== original.assetsVectorDatabaseProvider ||
			assetsVectorDatabaseUrl !== original.assetsVectorDatabaseUrl ||
			assetsVectorDatabaseQdrantApiKey !== original.assetsVectorDatabaseQdrantApiKey ||
			assetsVectorDatabasePineconeApiKey !== original.assetsVectorDatabasePineconeApiKey ||
			assetsVectorDatabaseWeaviateApiKey !== original.assetsVectorDatabaseWeaviateApiKey ||
			assetsVectorDatabaseMilvusToken !== original.assetsVectorDatabaseMilvusToken ||
			assetsVectorDatabaseRedisPassword !== original.assetsVectorDatabaseRedisPassword ||
			assetsVectorDatabaseOpensearchApiKey !==
				original.assetsVectorDatabaseOpensearchApiKey ||
			assetsVectorCollectionTemplate !== original.assetsVectorCollectionTemplate ||
			assetsVectorSparseEnabled !== original.assetsVectorSparseEnabled ||
			assetsVectorFusionAlgorithm !== original.assetsVectorFusionAlgorithm ||
			assetsVectorNormalizeScores !== original.assetsVectorNormalizeScores ||
			assetsEmbeddingsVectorSize !== original.assetsEmbeddingsVectorSize ||
			assetsEmbeddingsBatchSize !== original.assetsEmbeddingsBatchSize ||
			assetsRerankDefaultStrategy !== original.assetsRerankDefaultStrategy ||
			assetsRerankTopK !== original.assetsRerankTopK ||
			assetsStorageBackend !== original.assetsStorageBackend ||
			assetsStorageLocalRootPath !== original.assetsStorageLocalRootPath ||
			assetsStorageS3EndpointUrl !== original.assetsStorageS3EndpointUrl ||
			assetsStorageS3Bucket !== original.assetsStorageS3Bucket ||
			assetsStorageS3Region !== original.assetsStorageS3Region ||
			assetsStorageS3AccessKeyId !== original.assetsStorageS3AccessKeyId ||
			assetsStorageS3SecretAccessKey !== original.assetsStorageS3SecretAccessKey ||
			assetsStorageS3Prefix !== original.assetsStorageS3Prefix ||
			assetsStorageS3PresignedUrlTtl !== original.assetsStorageS3PresignedUrlTtl ||
			assetsStorageS3MultipartThreshold !== original.assetsStorageS3MultipartThreshold ||
			assetsStorageS3MultipartChunkSize !== original.assetsStorageS3MultipartChunkSize ||
			assetsStorageS3MaxRetries !== original.assetsStorageS3MaxRetries ||
			assetsStorageS3RetryMode !== original.assetsStorageS3RetryMode
		) {
			const assetsPatch: AssetsSettingsPatch = {}
			if (assetsDefaultEmbeddingModelId !== original.assetsDefaultEmbeddingModelId)
				assetsPatch.default_embedding_model_id = assetsDefaultEmbeddingModelId || null

			if (
				assetsVectorDatabaseProvider !== original.assetsVectorDatabaseProvider ||
				assetsVectorDatabaseUrl !== original.assetsVectorDatabaseUrl ||
				assetsVectorDatabaseQdrantUseGrpc !== original.assetsVectorDatabaseQdrantUseGrpc ||
				assetsVectorDatabaseQdrantApiKey !== original.assetsVectorDatabaseQdrantApiKey ||
				assetsVectorDatabaseChromaApiKey !== original.assetsVectorDatabaseChromaApiKey ||
				assetsVectorDatabasePineconeApiKey !==
					original.assetsVectorDatabasePineconeApiKey ||
				assetsVectorDatabaseWeaviateApiKey !==
					original.assetsVectorDatabaseWeaviateApiKey ||
				assetsVectorDatabaseMilvusToken !== original.assetsVectorDatabaseMilvusToken ||
				assetsVectorDatabaseRedisPassword !== original.assetsVectorDatabaseRedisPassword ||
				assetsVectorDatabaseOpensearchApiKey !==
					original.assetsVectorDatabaseOpensearchApiKey
			) {
				const vectorDatabasePatch: VectorDatabaseSettingsPatch = {}
				if (assetsVectorDatabaseProvider !== original.assetsVectorDatabaseProvider)
					vectorDatabasePatch.provider = assetsVectorDatabaseProvider
				if (
					assetsVectorDatabaseProvider === 'qdrant' &&
					(assetsVectorDatabaseUrl !== original.assetsVectorDatabaseUrl ||
						assetsVectorDatabaseQdrantUseGrpc !==
							original.assetsVectorDatabaseQdrantUseGrpc ||
						assetsVectorDatabaseQdrantApiKey !==
							original.assetsVectorDatabaseQdrantApiKey)
				) {
					const qdrantPatch: QdrantVectorDatabaseSettingsPatch = {}
					if (assetsVectorDatabaseUrl !== original.assetsVectorDatabaseUrl)
						qdrantPatch.url = assetsVectorDatabaseUrl || undefined
					if (
						assetsVectorDatabaseQdrantUseGrpc !==
						original.assetsVectorDatabaseQdrantUseGrpc
					)
						qdrantPatch.use_grpc = assetsVectorDatabaseQdrantUseGrpc
					if (
						assetsVectorDatabaseQdrantApiKey !==
						original.assetsVectorDatabaseQdrantApiKey
					)
						qdrantPatch.api_key = assetsVectorDatabaseQdrantApiKey || null
					vectorDatabasePatch.qdrant = qdrantPatch
				}

				if (
					assetsVectorDatabaseProvider === 'chroma' &&
					(assetsVectorDatabaseUrl !== original.assetsVectorDatabaseUrl ||
						assetsVectorDatabaseChromaApiKey !==
							original.assetsVectorDatabaseChromaApiKey)
				) {
					const chromaPatch: ChromaVectorDatabaseSettingsPatch = {}
					if (assetsVectorDatabaseUrl !== original.assetsVectorDatabaseUrl)
						chromaPatch.url = assetsVectorDatabaseUrl || null
					if (
						assetsVectorDatabaseChromaApiKey !==
						original.assetsVectorDatabaseChromaApiKey
					)
						chromaPatch.api_key = assetsVectorDatabaseChromaApiKey || null
					vectorDatabasePatch.chroma = chromaPatch
				}

				if (
					assetsVectorDatabaseProvider === 'pinecone' &&
					(assetsVectorDatabaseUrl !== original.assetsVectorDatabaseUrl ||
						assetsVectorDatabasePineconeApiKey !==
							original.assetsVectorDatabasePineconeApiKey)
				) {
					const pineconePatch: PineconeVectorDatabaseSettingsPatch = {}
					if (assetsVectorDatabaseUrl !== original.assetsVectorDatabaseUrl)
						pineconePatch.url = assetsVectorDatabaseUrl || null
					if (
						assetsVectorDatabasePineconeApiKey !==
						original.assetsVectorDatabasePineconeApiKey
					)
						pineconePatch.api_key = assetsVectorDatabasePineconeApiKey || null
					vectorDatabasePatch.pinecone = pineconePatch
				}

				if (
					assetsVectorDatabaseProvider === 'weaviate' &&
					(assetsVectorDatabaseUrl !== original.assetsVectorDatabaseUrl ||
						assetsVectorDatabaseWeaviateApiKey !==
							original.assetsVectorDatabaseWeaviateApiKey)
				) {
					const weaviatePatch: WeaviateVectorDatabaseSettingsPatch = {}
					if (assetsVectorDatabaseUrl !== original.assetsVectorDatabaseUrl)
						weaviatePatch.url = assetsVectorDatabaseUrl || null
					if (
						assetsVectorDatabaseWeaviateApiKey !==
						original.assetsVectorDatabaseWeaviateApiKey
					)
						weaviatePatch.api_key = assetsVectorDatabaseWeaviateApiKey || null
					vectorDatabasePatch.weaviate = weaviatePatch
				}

				if (
					assetsVectorDatabaseProvider === 'milvus' &&
					(assetsVectorDatabaseUrl !== original.assetsVectorDatabaseUrl ||
						assetsVectorDatabaseMilvusToken !==
							original.assetsVectorDatabaseMilvusToken)
				) {
					const milvusPatch: MilvusVectorDatabaseSettingsPatch = {}
					if (assetsVectorDatabaseUrl !== original.assetsVectorDatabaseUrl)
						milvusPatch.url = assetsVectorDatabaseUrl || null
					if (
						assetsVectorDatabaseMilvusToken !== original.assetsVectorDatabaseMilvusToken
					)
						milvusPatch.token = assetsVectorDatabaseMilvusToken || null
					vectorDatabasePatch.milvus = milvusPatch
				}

				if (
					assetsVectorDatabaseProvider === 'pgvector' &&
					assetsVectorDatabaseUrl !== original.assetsVectorDatabaseUrl
				) {
					vectorDatabasePatch.pgvector = {
						url: assetsVectorDatabaseUrl || null,
					}
				}

				if (
					assetsVectorDatabaseProvider === 'redis' &&
					(assetsVectorDatabaseUrl !== original.assetsVectorDatabaseUrl ||
						assetsVectorDatabaseRedisPassword !==
							original.assetsVectorDatabaseRedisPassword)
				) {
					const redisPatch: RedisVectorDatabaseSettingsPatch = {}
					if (assetsVectorDatabaseUrl !== original.assetsVectorDatabaseUrl)
						redisPatch.url = assetsVectorDatabaseUrl || null
					if (
						assetsVectorDatabaseRedisPassword !==
						original.assetsVectorDatabaseRedisPassword
					)
						redisPatch.password = assetsVectorDatabaseRedisPassword || null
					vectorDatabasePatch.redis = redisPatch
				}

				if (
					assetsVectorDatabaseProvider === 'opensearch' &&
					(assetsVectorDatabaseUrl !== original.assetsVectorDatabaseUrl ||
						assetsVectorDatabaseOpensearchApiKey !==
							original.assetsVectorDatabaseOpensearchApiKey)
				) {
					const opensearchPatch: OpensearchVectorDatabaseSettingsPatch = {}
					if (assetsVectorDatabaseUrl !== original.assetsVectorDatabaseUrl)
						opensearchPatch.url = assetsVectorDatabaseUrl || null
					if (
						assetsVectorDatabaseOpensearchApiKey !==
						original.assetsVectorDatabaseOpensearchApiKey
					)
						opensearchPatch.api_key = assetsVectorDatabaseOpensearchApiKey || null
					vectorDatabasePatch.opensearch = opensearchPatch
				}

				assetsPatch.vector_database = vectorDatabasePatch
			}

			if (
				assetsVectorCollectionTemplate !== original.assetsVectorCollectionTemplate ||
				assetsVectorSparseEnabled !== original.assetsVectorSparseEnabled ||
				assetsVectorFusionAlgorithm !== original.assetsVectorFusionAlgorithm ||
				assetsVectorNormalizeScores !== original.assetsVectorNormalizeScores
			) {
				const vectorPatch: VectorSettingsPatch = {}
				if (assetsVectorCollectionTemplate !== original.assetsVectorCollectionTemplate)
					vectorPatch.collection_template = assetsVectorCollectionTemplate || undefined
				if (assetsVectorSparseEnabled !== original.assetsVectorSparseEnabled)
					vectorPatch.sparse_vectors_enabled = assetsVectorSparseEnabled
				if (assetsVectorFusionAlgorithm !== original.assetsVectorFusionAlgorithm)
					vectorPatch.fusion_algorithm = assetsVectorFusionAlgorithm
				if (assetsVectorNormalizeScores !== original.assetsVectorNormalizeScores)
					vectorPatch.normalize_scores = assetsVectorNormalizeScores
				assetsPatch.vector = vectorPatch
			}

			if (
				assetsEmbeddingsVectorSize !== original.assetsEmbeddingsVectorSize ||
				assetsEmbeddingsBatchSize !== original.assetsEmbeddingsBatchSize
			) {
				const embPatch: EmbeddingsSettingsPatch = {}
				if (assetsEmbeddingsVectorSize !== original.assetsEmbeddingsVectorSize)
					embPatch.vector_size = asNumberOrUndefined(assetsEmbeddingsVectorSize)
				if (assetsEmbeddingsBatchSize !== original.assetsEmbeddingsBatchSize)
					embPatch.batch_size = asNumberOrUndefined(assetsEmbeddingsBatchSize)
				assetsPatch.embeddings = embPatch
			}

			if (
				assetsRerankDefaultStrategy !== original.assetsRerankDefaultStrategy ||
				assetsRerankTopK !== original.assetsRerankTopK
			) {
				const rerankPatch: RerankSettingsPatch = {}
				if (assetsRerankDefaultStrategy !== original.assetsRerankDefaultStrategy)
					rerankPatch.default_strategy = assetsRerankDefaultStrategy || undefined
				if (assetsRerankTopK !== original.assetsRerankTopK)
					rerankPatch.top_k = asNumberOrUndefined(assetsRerankTopK)
				assetsPatch.rerank = rerankPatch
			}

			if (
				assetsStorageBackend !== original.assetsStorageBackend ||
				assetsStorageLocalRootPath !== original.assetsStorageLocalRootPath ||
				assetsStorageS3EndpointUrl !== original.assetsStorageS3EndpointUrl ||
				assetsStorageS3Bucket !== original.assetsStorageS3Bucket ||
				assetsStorageS3Region !== original.assetsStorageS3Region ||
				assetsStorageS3AccessKeyId !== original.assetsStorageS3AccessKeyId ||
				assetsStorageS3SecretAccessKey !== original.assetsStorageS3SecretAccessKey ||
				assetsStorageS3Prefix !== original.assetsStorageS3Prefix ||
				assetsStorageS3PresignedUrlTtl !== original.assetsStorageS3PresignedUrlTtl ||
				assetsStorageS3MultipartThreshold !== original.assetsStorageS3MultipartThreshold ||
				assetsStorageS3MultipartChunkSize !== original.assetsStorageS3MultipartChunkSize ||
				assetsStorageS3MaxRetries !== original.assetsStorageS3MaxRetries ||
				assetsStorageS3RetryMode !== original.assetsStorageS3RetryMode
			) {
				const storagePatch: StorageSettingsPatch = {}
				if (assetsStorageBackend !== original.assetsStorageBackend)
					storagePatch.backend = assetsStorageBackend
				if (
					assetsStorageLocalRootPath !== original.assetsStorageLocalRootPath &&
					assetsStorageBackend === 'local'
				) {
					storagePatch.local = { root_path: assetsStorageLocalRootPath || undefined }
				}
				if (
					(assetsStorageS3EndpointUrl !== original.assetsStorageS3EndpointUrl ||
						assetsStorageS3Bucket !== original.assetsStorageS3Bucket ||
						assetsStorageS3Region !== original.assetsStorageS3Region ||
						assetsStorageS3AccessKeyId !== original.assetsStorageS3AccessKeyId ||
						assetsStorageS3SecretAccessKey !==
							original.assetsStorageS3SecretAccessKey ||
						assetsStorageS3Prefix !== original.assetsStorageS3Prefix ||
						assetsStorageS3PresignedUrlTtl !==
							original.assetsStorageS3PresignedUrlTtl ||
						assetsStorageS3MultipartThreshold !==
							original.assetsStorageS3MultipartThreshold ||
						assetsStorageS3MultipartChunkSize !==
							original.assetsStorageS3MultipartChunkSize ||
						assetsStorageS3MaxRetries !== original.assetsStorageS3MaxRetries ||
						assetsStorageS3RetryMode !== original.assetsStorageS3RetryMode) &&
					assetsStorageBackend === 's3'
				) {
					const s3Patch: S3StorageConfigPatch = {}
					if (assetsStorageS3EndpointUrl !== original.assetsStorageS3EndpointUrl)
						s3Patch.endpoint_url = assetsStorageS3EndpointUrl || null
					if (assetsStorageS3Bucket !== original.assetsStorageS3Bucket)
						s3Patch.bucket = assetsStorageS3Bucket || undefined
					if (assetsStorageS3Region !== original.assetsStorageS3Region)
						s3Patch.region = assetsStorageS3Region || undefined
					if (assetsStorageS3AccessKeyId !== original.assetsStorageS3AccessKeyId)
						s3Patch.access_key_id = assetsStorageS3AccessKeyId || null
					if (assetsStorageS3SecretAccessKey !== original.assetsStorageS3SecretAccessKey)
						s3Patch.secret_access_key = assetsStorageS3SecretAccessKey || null
					if (assetsStorageS3Prefix !== original.assetsStorageS3Prefix)
						s3Patch.prefix = assetsStorageS3Prefix || undefined
					if (assetsStorageS3PresignedUrlTtl !== original.assetsStorageS3PresignedUrlTtl)
						s3Patch.presigned_url_ttl = asNumberOrUndefined(
							assetsStorageS3PresignedUrlTtl
						)
					if (
						assetsStorageS3MultipartThreshold !==
						original.assetsStorageS3MultipartThreshold
					)
						s3Patch.multipart_threshold = asNumberOrUndefined(
							assetsStorageS3MultipartThreshold
						)
					if (
						assetsStorageS3MultipartChunkSize !==
						original.assetsStorageS3MultipartChunkSize
					)
						s3Patch.multipart_chunk_size = asNumberOrUndefined(
							assetsStorageS3MultipartChunkSize
						)
					if (assetsStorageS3MaxRetries !== original.assetsStorageS3MaxRetries)
						s3Patch.max_retries = asNumberOrUndefined(assetsStorageS3MaxRetries)
					if (assetsStorageS3RetryMode !== original.assetsStorageS3RetryMode)
						s3Patch.retry_mode = assetsStorageS3RetryMode
					storagePatch.s3 = s3Patch
				}
				assetsPatch.storage = storagePatch
			}

			data.assets = assetsPatch
		}

		if (
			mediaFaviconSource !== original.mediaFaviconSource ||
			mediaFaviconUrl !== original.mediaFaviconUrl ||
			mediaAppleTouchIconSource !== original.mediaAppleTouchIconSource ||
			mediaAppleTouchIconUrl !== original.mediaAppleTouchIconUrl
		) {
			data.media = {}
			if (
				mediaFaviconSource !== original.mediaFaviconSource ||
				mediaFaviconUrl !== original.mediaFaviconUrl
			) {
				data.media.favicon = {
					source: mediaFaviconSource,
					url: mediaFaviconSource === 'custom' ? mediaFaviconUrl || null : null,
				}
			}
			if (
				mediaAppleTouchIconSource !== original.mediaAppleTouchIconSource ||
				mediaAppleTouchIconUrl !== original.mediaAppleTouchIconUrl
			) {
				data.media.apple_touch_icon = {
					source: mediaAppleTouchIconSource,
					url:
						mediaAppleTouchIconSource === 'custom'
							? mediaAppleTouchIconUrl || null
							: null,
				}
			}
		}

		if (
			softDeleteThreads !== original.softDeleteThreads ||
			softDeleteNotes !== original.softDeleteNotes ||
			softDeleteFiles !== original.softDeleteFiles
		) {
			data.soft_delete = {}
			if (softDeleteThreads !== original.softDeleteThreads)
				data.soft_delete.threads = softDeleteThreads
			if (softDeleteNotes !== original.softDeleteNotes)
				data.soft_delete.notes = softDeleteNotes
			if (softDeleteFiles !== original.softDeleteFiles)
				data.soft_delete.files = softDeleteFiles
		}

		if (
			notificationsWebPushEnabled !== original.notificationsWebPushEnabled ||
			notificationsWebPushTtlSeconds !== original.notificationsWebPushTtlSeconds ||
			notificationsNotificationTtlSeconds !== original.notificationsNotificationTtlSeconds ||
			notificationsMissedGraceDays !== original.notificationsMissedGraceDays ||
			notificationsLookaheadDays !== original.notificationsLookaheadDays ||
			notificationsVapidPublicKey !== original.notificationsVapidPublicKey ||
			notificationsVapidPrivateKey !== original.notificationsVapidPrivateKey
		) {
			const notificationsPatch: NotificationSettingsPatch = {}
			if (notificationsWebPushEnabled !== original.notificationsWebPushEnabled)
				notificationsPatch.web_push_enabled = notificationsWebPushEnabled
			if (notificationsWebPushTtlSeconds !== original.notificationsWebPushTtlSeconds)
				notificationsPatch.web_push_ttl_seconds = asNumberOrUndefined(
					notificationsWebPushTtlSeconds
				)
			if (
				notificationsNotificationTtlSeconds !== original.notificationsNotificationTtlSeconds
			)
				notificationsPatch.notification_ttl_seconds = asNumberOrNull(
					notificationsNotificationTtlSeconds
				)
			if (notificationsMissedGraceDays !== original.notificationsMissedGraceDays)
				notificationsPatch.missed_grace_days = asNumberOrUndefined(
					notificationsMissedGraceDays
				)
			if (notificationsLookaheadDays !== original.notificationsLookaheadDays)
				notificationsPatch.lookahead_days = asNumberOrUndefined(notificationsLookaheadDays)
			if (notificationsVapidPublicKey !== original.notificationsVapidPublicKey)
				notificationsPatch.vapid_public_key = notificationsVapidPublicKey || null
			if (notificationsVapidPrivateKey !== original.notificationsVapidPrivateKey)
				notificationsPatch.vapid_private_key = notificationsVapidPrivateKey || null
			data.notifications = notificationsPatch
		}

		if (
			webSearchMaxChars !== original.webSearchMaxChars ||
			webSearchAgenticAgent !== original.webSearchAgenticAgent ||
			webSearchAgenticModelId !== original.webSearchAgenticModelId ||
			webSearchAgenticSystemPrompt !== original.webSearchAgenticSystemPrompt ||
			webSearchAgenticModelParams !== original.webSearchAgenticModelParams ||
			webSearchAgenticMaxIterations !== original.webSearchAgenticMaxIterations ||
			webSearchBlacklistedDomains !== original.webSearchBlacklistedDomains ||
			webSearchEngineEngine !== original.webSearchEngineEngine ||
			webSearchWebLoaderEngine !== original.webSearchWebLoaderEngine ||
			webSearchWebLoaderTimeoutSeconds !== original.webSearchWebLoaderTimeoutSeconds ||
			webSearchWebLoaderUserAgent !== original.webSearchWebLoaderUserAgent ||
			webSearchWebLoaderMaxChars !== original.webSearchWebLoaderMaxChars ||
			webSearchTavilyApiKey !== original.webSearchTavilyApiKey ||
			webSearchTavilyExtractDepth !== original.webSearchTavilyExtractDepth ||
			webSearchTavilyMaxConcurrentRequests !== original.webSearchTavilyMaxConcurrentRequests
		) {
			const wsPatch: WebSearchSettingsPatch = {}
			if (webSearchMaxChars !== original.webSearchMaxChars)
				wsPatch.max_chars = asNumberOrUndefined(webSearchMaxChars)
			if (webSearchBlacklistedDomains !== original.webSearchBlacklistedDomains)
				wsPatch.blacklisted_domains = parseCommaList(webSearchBlacklistedDomains)

			if (
				webSearchAgenticAgent !== original.webSearchAgenticAgent ||
				webSearchAgenticModelId !== original.webSearchAgenticModelId ||
				webSearchAgenticSystemPrompt !== original.webSearchAgenticSystemPrompt ||
				webSearchAgenticModelParams !== original.webSearchAgenticModelParams ||
				webSearchAgenticMaxIterations !== original.webSearchAgenticMaxIterations
			) {
				const agenticPatch: AgenticWebSearchSettingsPatch = {}
				if (webSearchAgenticAgent !== original.webSearchAgenticAgent)
					agenticPatch.agent = webSearchAgenticAgent
				if (webSearchAgenticModelId !== original.webSearchAgenticModelId)
					agenticPatch.model_id = webSearchAgenticModelId || null
				if (webSearchAgenticSystemPrompt !== original.webSearchAgenticSystemPrompt)
					agenticPatch.system_prompt = webSearchAgenticSystemPrompt
				if (webSearchAgenticModelParams !== original.webSearchAgenticModelParams)
					agenticPatch.model_params = parseJsonObject(webSearchAgenticModelParams)
				if (webSearchAgenticMaxIterations !== original.webSearchAgenticMaxIterations)
					agenticPatch.max_iterations = asNumberOrUndefined(webSearchAgenticMaxIterations)
				wsPatch.agentic = agenticPatch
			}

			if (webSearchEngineEngine !== original.webSearchEngineEngine) {
				wsPatch.search_engines = { engine: webSearchEngineEngine }
			}

			if (
				webSearchWebLoaderEngine !== original.webSearchWebLoaderEngine ||
				webSearchWebLoaderTimeoutSeconds !== original.webSearchWebLoaderTimeoutSeconds ||
				webSearchWebLoaderUserAgent !== original.webSearchWebLoaderUserAgent ||
				webSearchWebLoaderMaxChars !== original.webSearchWebLoaderMaxChars ||
				webSearchTavilyApiKey !== original.webSearchTavilyApiKey ||
				webSearchTavilyExtractDepth !== original.webSearchTavilyExtractDepth ||
				webSearchTavilyMaxConcurrentRequests !==
					original.webSearchTavilyMaxConcurrentRequests
			) {
				const wlPatch: WebLoaderSettingsPatch = {}
				if (webSearchWebLoaderEngine !== original.webSearchWebLoaderEngine)
					wlPatch.engine = webSearchWebLoaderEngine
				if (webSearchWebLoaderTimeoutSeconds !== original.webSearchWebLoaderTimeoutSeconds)
					wlPatch.timeout_seconds = asNumberOrUndefined(webSearchWebLoaderTimeoutSeconds)
				if (webSearchWebLoaderUserAgent !== original.webSearchWebLoaderUserAgent)
					wlPatch.user_agent = webSearchWebLoaderUserAgent || undefined
				if (webSearchWebLoaderMaxChars !== original.webSearchWebLoaderMaxChars)
					wlPatch.max_chars = asNumberOrUndefined(webSearchWebLoaderMaxChars)
				if (
					webSearchTavilyApiKey !== original.webSearchTavilyApiKey ||
					webSearchTavilyExtractDepth !== original.webSearchTavilyExtractDepth ||
					webSearchTavilyMaxConcurrentRequests !==
						original.webSearchTavilyMaxConcurrentRequests
				) {
					const tavilyPatch: TavilySettingsPatch = {}
					if (webSearchTavilyApiKey !== original.webSearchTavilyApiKey)
						tavilyPatch.api_key = webSearchTavilyApiKey || null
					if (webSearchTavilyExtractDepth !== original.webSearchTavilyExtractDepth)
						tavilyPatch.extract_depth = webSearchTavilyExtractDepth
					if (
						webSearchTavilyMaxConcurrentRequests !==
						original.webSearchTavilyMaxConcurrentRequests
					)
						tavilyPatch.max_concurrent_requests = asNumberOrUndefined(
							webSearchTavilyMaxConcurrentRequests
						)
					wlPatch.tavily = tavilyPatch
				}
				wsPatch.web_loaders = wlPatch
			}

			data.web_search = wsPatch
		}

		if (
			webSearchSearxngInstanceUrl !== original.webSearchSearxngInstanceUrl ||
			webSearchSearxngMaxResults !== original.webSearchSearxngMaxResults ||
			webSearchSearxngMaxConcurrentRequests !==
				original.webSearchSearxngMaxConcurrentRequests ||
			webSearchSearxngTimeoutSeconds !== original.webSearchSearxngTimeoutSeconds ||
			webSearchPerplexityApiKey !== original.webSearchPerplexityApiKey ||
			webSearchPerplexityModel !== original.webSearchPerplexityModel ||
			webSearchPerplexitySearchContextUsage !==
				original.webSearchPerplexitySearchContextUsage ||
			webSearchPerplexityTemperature !== original.webSearchPerplexityTemperature ||
			webSearchPerplexityImageResultsEnabled !==
				original.webSearchPerplexityImageResultsEnabled ||
			webSearchPerplexityMaxConcurrentRequests !==
				original.webSearchPerplexityMaxConcurrentRequests
		) {
			const integrationsPatch: IntegrationsSettingsPatch = {}
			if (
				webSearchSearxngInstanceUrl !== original.webSearchSearxngInstanceUrl ||
				webSearchSearxngMaxResults !== original.webSearchSearxngMaxResults ||
				webSearchSearxngMaxConcurrentRequests !==
					original.webSearchSearxngMaxConcurrentRequests ||
				webSearchSearxngTimeoutSeconds !== original.webSearchSearxngTimeoutSeconds
			) {
				const searxngPatch: SearxngSettingsPatch = {}
				if (webSearchSearxngInstanceUrl !== original.webSearchSearxngInstanceUrl)
					searxngPatch.instance_url = webSearchSearxngInstanceUrl || undefined
				if (webSearchSearxngMaxResults !== original.webSearchSearxngMaxResults)
					searxngPatch.max_results = asNumberOrUndefined(webSearchSearxngMaxResults)
				if (
					webSearchSearxngMaxConcurrentRequests !==
					original.webSearchSearxngMaxConcurrentRequests
				)
					searxngPatch.max_concurrent_requests = asNumberOrUndefined(
						webSearchSearxngMaxConcurrentRequests
					)
				if (webSearchSearxngTimeoutSeconds !== original.webSearchSearxngTimeoutSeconds)
					searxngPatch.timeout_seconds = asNumberOrUndefined(
						webSearchSearxngTimeoutSeconds
					)
				integrationsPatch.searxng = searxngPatch
			}

			if (
				webSearchPerplexityApiKey !== original.webSearchPerplexityApiKey ||
				webSearchPerplexityModel !== original.webSearchPerplexityModel ||
				webSearchPerplexitySearchContextUsage !==
					original.webSearchPerplexitySearchContextUsage ||
				webSearchPerplexityTemperature !== original.webSearchPerplexityTemperature ||
				webSearchPerplexityImageResultsEnabled !==
					original.webSearchPerplexityImageResultsEnabled ||
				webSearchPerplexityMaxConcurrentRequests !==
					original.webSearchPerplexityMaxConcurrentRequests
			) {
				const perplexityPatch: PerplexitySettingsPatch = {}
				if (webSearchPerplexityApiKey !== original.webSearchPerplexityApiKey)
					perplexityPatch.api_key = webSearchPerplexityApiKey || null
				if (webSearchPerplexityModel !== original.webSearchPerplexityModel)
					perplexityPatch.model = webSearchPerplexityModel || undefined
				if (
					webSearchPerplexitySearchContextUsage !==
					original.webSearchPerplexitySearchContextUsage
				)
					perplexityPatch.search_context_usage =
						webSearchPerplexitySearchContextUsage || undefined
				if (webSearchPerplexityTemperature !== original.webSearchPerplexityTemperature)
					perplexityPatch.temperature = asNumberOrUndefined(
						webSearchPerplexityTemperature
					)
				if (
					webSearchPerplexityImageResultsEnabled !==
					original.webSearchPerplexityImageResultsEnabled
				)
					perplexityPatch.image_results_enabled = webSearchPerplexityImageResultsEnabled
				if (
					webSearchPerplexityMaxConcurrentRequests !==
					original.webSearchPerplexityMaxConcurrentRequests
				)
					perplexityPatch.max_concurrent_requests = asNumberOrUndefined(
						webSearchPerplexityMaxConcurrentRequests
					)
				integrationsPatch.perplexity = perplexityPatch
			}

			data.integrations = integrationsPatch
		}

		if (
			codeInterpreterEnabled !== original.codeInterpreterEnabled ||
			codeInterpreterEngine !== original.codeInterpreterEngine ||
			codeInterpreterE2bApiKey !== original.codeInterpreterE2bApiKey ||
			codeInterpreterE2bTemplate !== original.codeInterpreterE2bTemplate ||
			codeInterpreterE2bAvailablePackages !== original.codeInterpreterE2bAvailablePackages ||
			codeInterpreterTimeout !== original.codeInterpreterTimeout
		) {
			const ciPatch: CodeInterpreterSettingsPatch = {}
			if (codeInterpreterEnabled !== original.codeInterpreterEnabled)
				ciPatch.enabled = codeInterpreterEnabled
			if (codeInterpreterEngine !== original.codeInterpreterEngine)
				ciPatch.engine = codeInterpreterEngine
			if (
				codeInterpreterE2bApiKey !== original.codeInterpreterE2bApiKey ||
				codeInterpreterE2bTemplate !== original.codeInterpreterE2bTemplate ||
				codeInterpreterE2bAvailablePackages !== original.codeInterpreterE2bAvailablePackages
			) {
				const e2bPatch: E2bSettingsPatch = {}
				if (codeInterpreterE2bApiKey !== original.codeInterpreterE2bApiKey)
					e2bPatch.api_key = codeInterpreterE2bApiKey || null
				if (codeInterpreterE2bTemplate !== original.codeInterpreterE2bTemplate)
					e2bPatch.template = codeInterpreterE2bTemplate || undefined
				if (
					codeInterpreterE2bAvailablePackages !==
					original.codeInterpreterE2bAvailablePackages
				)
					e2bPatch.available_packages = parseCommaList(
						codeInterpreterE2bAvailablePackages
					)
				ciPatch.e2b = e2bPatch
			}
			if (codeInterpreterTimeout !== original.codeInterpreterTimeout)
				ciPatch.timeout = asNumberOrUndefined(codeInterpreterTimeout)
			data.code_interpreter = ciPatch
		}

		if (
			taskMaintenanceInactivityHours !== original.taskMaintenanceInactivityHours ||
			taskMaintenanceQueuedSupersedeAfterMinutes !==
				original.taskMaintenanceQueuedSupersedeAfterMinutes ||
			taskMaintenanceActiveSupersedeAfterMinutes !==
				original.taskMaintenanceActiveSupersedeAfterMinutes ||
			taskMaintenanceRunnerTimeoutSeconds !== original.taskMaintenanceRunnerTimeoutSeconds ||
			taskMaintenanceStaleTaskCleanupAfterMinutes !==
				original.taskMaintenanceStaleTaskCleanupAfterMinutes ||
			taskMaintenanceBackfillEnabled !== original.taskMaintenanceBackfillEnabled ||
			taskMaintenanceBackfillCron !== original.taskMaintenanceBackfillCron ||
			taskMaintenanceBackfillBatchSize !== original.taskMaintenanceBackfillBatchSize ||
			taskMaintenanceBackfillMaxLookbackDays !==
				original.taskMaintenanceBackfillMaxLookbackDays ||
			taskMaintenanceBackfillMinInactivityHours !==
				original.taskMaintenanceBackfillMinInactivityHours
		) {
			data.tasks = {}
			if (
				taskMaintenanceInactivityHours !== original.taskMaintenanceInactivityHours ||
				taskMaintenanceQueuedSupersedeAfterMinutes !==
					original.taskMaintenanceQueuedSupersedeAfterMinutes ||
				taskMaintenanceActiveSupersedeAfterMinutes !==
					original.taskMaintenanceActiveSupersedeAfterMinutes ||
				taskMaintenanceRunnerTimeoutSeconds !==
					original.taskMaintenanceRunnerTimeoutSeconds ||
				taskMaintenanceStaleTaskCleanupAfterMinutes !==
					original.taskMaintenanceStaleTaskCleanupAfterMinutes
			) {
				data.tasks.thread_maintenance = {}
				const maintenancePatch = data.tasks.thread_maintenance
				if (maintenancePatch) {
					if (taskMaintenanceInactivityHours !== original.taskMaintenanceInactivityHours)
						maintenancePatch.inactivity_hours = asNumberOrUndefined(
							taskMaintenanceInactivityHours
						)
					if (
						taskMaintenanceQueuedSupersedeAfterMinutes !==
						original.taskMaintenanceQueuedSupersedeAfterMinutes
					)
						maintenancePatch.queued_supersede_after_minutes = asNumberOrUndefined(
							taskMaintenanceQueuedSupersedeAfterMinutes
						)
					if (
						taskMaintenanceActiveSupersedeAfterMinutes !==
						original.taskMaintenanceActiveSupersedeAfterMinutes
					)
						maintenancePatch.active_supersede_after_minutes = asNumberOrUndefined(
							taskMaintenanceActiveSupersedeAfterMinutes
						)
					if (
						taskMaintenanceRunnerTimeoutSeconds !==
						original.taskMaintenanceRunnerTimeoutSeconds
					)
						maintenancePatch.runner_timeout_seconds = asNumberOrUndefined(
							taskMaintenanceRunnerTimeoutSeconds
						)
					if (
						taskMaintenanceStaleTaskCleanupAfterMinutes !==
						original.taskMaintenanceStaleTaskCleanupAfterMinutes
					)
						maintenancePatch.stale_task_cleanup_after_minutes = asNumberOrUndefined(
							taskMaintenanceStaleTaskCleanupAfterMinutes
						)
				}
			}
			if (
				taskMaintenanceBackfillEnabled !== original.taskMaintenanceBackfillEnabled ||
				taskMaintenanceBackfillCron !== original.taskMaintenanceBackfillCron ||
				taskMaintenanceBackfillBatchSize !== original.taskMaintenanceBackfillBatchSize ||
				taskMaintenanceBackfillMaxLookbackDays !==
					original.taskMaintenanceBackfillMaxLookbackDays ||
				taskMaintenanceBackfillMinInactivityHours !==
					original.taskMaintenanceBackfillMinInactivityHours
			) {
				data.tasks.maintenance_backfill = {}
			}
			const backfillPatch = data.tasks.maintenance_backfill
			if (backfillPatch) {
				if (taskMaintenanceBackfillEnabled !== original.taskMaintenanceBackfillEnabled)
					backfillPatch.enabled = taskMaintenanceBackfillEnabled
				if (taskMaintenanceBackfillCron !== original.taskMaintenanceBackfillCron)
					backfillPatch.cron = taskMaintenanceBackfillCron
				if (taskMaintenanceBackfillBatchSize !== original.taskMaintenanceBackfillBatchSize)
					backfillPatch.batch_size = asNumberOrUndefined(taskMaintenanceBackfillBatchSize)
				if (
					taskMaintenanceBackfillMaxLookbackDays !==
					original.taskMaintenanceBackfillMaxLookbackDays
				)
					backfillPatch.max_lookback_days = asNumberOrUndefined(
						taskMaintenanceBackfillMaxLookbackDays
					)
				if (
					taskMaintenanceBackfillMinInactivityHours !==
					original.taskMaintenanceBackfillMinInactivityHours
				)
					backfillPatch.min_inactivity_hours = asNumberOrUndefined(
						taskMaintenanceBackfillMinInactivityHours
					)
			}
		}

		if (defaultPermissionsKey(defaultPermissions) !== original.defaultPermissionsKey) {
			data.default_permissions = buildDefaultPermissionsPatch()
		}

		return {
			data,
			expected_versions: response?.versions ?? null,
		}
	}

	async function save() {
		if (!response) return
		if (!hasChanges) return
		isSaving = true
		saveError = null
		saveSuccess = null

		try {
			const req = buildUpdateRequest()
			const result = await api.PATCH('/v1/settings', { body: req })
			if (result.error) {
				if (result.response.status === 409) {
					saveError = 'settings were updated elsewhere. reload and try again.'
				} else {
					const detail = result.error?.detail
					saveError = typeof detail === 'string' ? detail : 'failed to save settings'
				}
				return
			}
			setFromResponse(result.data!)
			saveSuccess = 'saved'
		} catch (e) {
			console.error('Failed to save settings', e)
			saveError = 'failed to save settings'
		} finally {
			isSaving = false
		}
	}

	async function generateVapidKeys() {
		if (!response || isGeneratingVapidKeys) return
		if (notificationsVapidPublicKey.trim() || notificationsVapidPrivateKey.trim()) return

		isGeneratingVapidKeys = true
		vapidGenerationError = null
		saveSuccess = null

		try {
			const result = await api.POST('/v1/settings/vapid-keypair', {})
			if (result.error) {
				const detail = result.error?.detail
				vapidGenerationError =
					typeof detail === 'string' ? detail : 'failed to generate VAPID keys'
				return
			}
			if (!result.data) {
				vapidGenerationError = 'failed to generate VAPID keys'
				return
			}
			notificationsVapidPublicKey = result.data.public_key
			notificationsVapidPrivateKey = result.data.private_key
		} catch (e) {
			console.error('Failed to generate VAPID keys', e)
			vapidGenerationError = 'failed to generate VAPID keys'
		} finally {
			isGeneratingVapidKeys = false
		}
	}

	onMount(() => {
		Promise.all([fetchSettings(), fetchAgents(), fetchModels(), fetchProviders()])
	})
</script>

<div class="flex min-h-0 min-w-0 flex-1 flex-col gap-6">
	<div class="flex shrink-0 flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
		<div>
			<h2 class="text-2xl font-bold tracking-tight">settings</h2>
			<p class="text-zinc-400">manage backend settings (admin only).</p>
		</div>
		<div class="flex items-center gap-2">
			<Button
				variant="secondary"
				class="rounded-xl"
				onclick={fetchSettings}
				disabled={isFetching || isSaving || isGeneratingVapidKeys}
			>
				<RefreshCw class="mr-1.5 h-4 w-4" />
				reload
			</Button>
			<Button
				variant="secondary"
				class="rounded-xl"
				onclick={resetDraft}
				disabled={!response ||
					isFetching ||
					isSaving ||
					isGeneratingVapidKeys ||
					!hasChanges}
			>
				<RotateCcw class="mr-1.5 h-4 w-4" />
				reset
			</Button>
			<Button
				class="rounded-xl"
				onclick={save}
				disabled={!response ||
					isFetching ||
					isSaving ||
					isGeneratingVapidKeys ||
					!hasChanges}
			>
				<Save class="mr-1.5 h-4 w-4" />
				{isSaving ? 'saving...' : 'save'}
			</Button>
		</div>
	</div>

	<div class="min-h-0 min-w-0 flex-1 overflow-hidden">
		<div class="mx-auto flex h-full min-h-0 w-full max-w-full min-w-0 flex-col gap-6">
			{#if error}
				<div
					class="rounded-lg border border-red-900/40 bg-red-950/40 p-4 text-sm text-red-200"
				>
					{error}
				</div>
			{/if}
			{#if saveError}
				<div
					class="rounded-lg border border-red-900/40 bg-red-950/40 p-4 text-sm text-red-200"
				>
					{saveError}
				</div>
			{/if}
			{#if saveSuccess}
				<div
					class="rounded-lg border border-emerald-900/40 bg-emerald-950/40 p-4 text-sm text-emerald-200"
				>
					{saveSuccess}
				</div>
			{/if}

			{#if isFetching}
				<div class="flex min-h-0 flex-1 items-center justify-center">
					<NokodoLoader className="opacity-70" />
				</div>
			{:else if response}
				<div
					class="grid min-h-0 flex-1 grid-cols-1 gap-4 lg:grid-cols-[240px_minmax(0,1fr)]"
				>
					<aside class="min-h-0 rounded-2xl border border-zinc-800 bg-zinc-950/70 p-3">
						<div
							class="mb-3 flex items-center gap-2 rounded-xl border border-zinc-800 bg-zinc-900/60 px-3 py-2"
						>
							<Search class="h-4 w-4 shrink-0 text-zinc-500" />
							<input
								bind:value={settingsSearch}
								placeholder="search settings..."
								class="min-w-0 flex-1 bg-transparent text-sm text-zinc-100 placeholder:text-zinc-500 focus:outline-none"
							/>
						</div>
						<nav class="flex max-h-[45vh] flex-col gap-1 overflow-y-auto lg:max-h-none">
							{#each filteredSections as section (section.id)}
								<button
									type="button"
									onclick={() => (activeSection = section.id)}
									class="flex items-center gap-2.5 rounded-xl px-3 py-2 text-left text-sm transition-colors {activeSection ===
									section.id
										? `${section.activeBg} text-zinc-100`
										: 'text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200'}"
								>
									<section.icon
										class="h-4 w-4 shrink-0 {activeSection === section.id
											? section.color
											: ''}"
									/>
									{section.label}
								</button>
							{:else}
								<div
									class="rounded-xl border border-dashed border-zinc-800 p-4 text-sm text-zinc-500"
								>
									no sections match
								</div>
							{/each}
						</nav>
					</aside>

					<div class="min-h-0 min-w-0 overflow-y-auto pr-1">
						<div class="min-w-0">
							{#if activeSection === 'section-ui'}
								<section>
									<SettingsUI
										bind:defaultTheme={uiDefaultTheme}
										bind:defaultBackground={uiDefaultBackground}
										bind:authPagesBackground={uiAuthPagesBackground}
										bind:sidebarCollapsed={uiSidebarCollapsed}
									/>
								</section>
							{:else if activeSection === 'section-ai'}
								<section>
									<SettingsAI
										bind:defaultAgentIds={aiDefaultAgentIds}
										bind:memoryEnable={aiMemoryEnable}
										bind:memorySimilarityThreshold={aiMemorySimilarityThreshold}
										bind:memoryTopK={aiMemoryTopK}
										bind:chatContextEnabled={aiChatContextEnabled}
										bind:chatContextMode={aiChatContextMode}
										bind:chatContextTopK={aiChatContextTopK}
										bind:chatContextSimilarityThreshold={
											aiChatContextSimilarityThreshold
										}
										bind:retrievalPreBuild={aiRetrievalPreBuild}
										bind:retrievalTurns={aiRetrievalTurns}
										bind:taskDefaultModelId={aiTaskDefaultModelId}
										bind:taskThreadMetadataModelId={aiTaskThreadMetadataModelId}
										bind:taskThreadMaintenanceModelId={
											aiTaskThreadMaintenanceModelId
										}
										bind:taskInputAutocompleteModelId={
											aiTaskInputAutocompleteModelId
										}
										bind:taskSummarizationModelId={aiTaskSummarizationModelId}
										bind:taskMemoryPostProcessingModelId={
											aiTaskMemoryPostProcessingModelId
										}
										bind:taskWebSearchModelId={aiTaskWebSearchModelId}
										bind:taskMaintenanceMaxCharsPerMessage={
											aiTaskMaintenanceMaxCharsPerMessage
										}
										bind:mediaImagesEnabled={aiMediaImagesEnabled}
										bind:mediaImagesModel={aiMediaImagesModel}
										bind:mediaImagesDefaultSize={aiMediaImagesDefaultSize}
										bind:mediaImagesDefaultSteps={aiMediaImagesDefaultSteps}
										bind:mediaImagesDefaultN={aiMediaImagesDefaultN}
										bind:mediaImagesMaxN={aiMediaImagesMaxN}
										bind:mediaVideosEnabled={aiMediaVideosEnabled}
										bind:mediaAudioEnabled={aiMediaAudioEnabled}
										bind:attachmentImageDecayIterations={
											aiAttachmentImageDecayIterations
										}
										bind:attachmentAudioDecayIterations={
											aiAttachmentAudioDecayIterations
										}
										bind:attachmentVideoDecayIterations={
											aiAttachmentVideoDecayIterations
										}
										bind:contextCompactionEnabled={aiContextCompactionEnabled}
										bind:contextCompactionTriggerRatio={
											aiContextCompactionTriggerRatio
										}
										bind:contextCompactionRecoveryTargetRatio={
											aiContextCompactionRecoveryTargetRatio
										}
										bind:contextCompactionTargetUsageCapTokens={
											aiContextCompactionTargetUsageCapTokens
										}
										bind:contextCompactionSummaryBatchMinTokens={
											aiContextCompactionSummaryBatchMinTokens
										}
										bind:contextCompactionSummaryBatchMaxTokens={
											aiContextCompactionSummaryBatchMaxTokens
										}
										bind:contextCompactionPromptOverheadTokens={
											aiContextCompactionPromptOverheadTokens
										}
										bind:contextCompactionBlockingSummarizationEnabled={
											aiContextCompactionBlockingSummarizationEnabled
										}
										bind:contextCompactionBlockingSummarizationTimeoutSeconds={
											aiContextCompactionBlockingSummarizationTimeoutSeconds
										}
										bind:contextCompactionToolResultMaxShare={
											aiContextCompactionToolResultMaxShare
										}
										bind:contextCompactionToolResultHardCap={
											aiContextCompactionToolResultHardCap
										}
										bind:contextCompactionToolResultsCombinedMaxShare={
											aiContextCompactionToolResultsCombinedMaxShare
										}
										bind:contextCompactionResponseHeadroom={
											aiContextCompactionResponseHeadroom
										}
										bind:contextCompactionSummarizationMaxCharsPerMessage={
											aiContextCompactionSummarizationMaxCharsPerMessage
										}
										{agents}
										{models}
										{providers}
										{isFetchingAgents}
										{isFetchingModels}
										{agentsError}
										{modelsError}
									/>
								</section>
							{:else if activeSection === 'section-branding'}
								<section>
									<SettingsBranding
										bind:siteName={brandingSiteName}
										bind:logoUrl={brandingLogoUrl}
										bind:faviconUrl={brandingFaviconUrl}
										bind:primaryColor={brandingPrimaryColor}
										bind:supportEmail={brandingSupportEmail}
										bind:adminEmail={brandingAdminEmail}
										bind:publicFrontendOrigin={brandingPublicFrontendOrigin}
										bind:publicCdnOrigin={brandingPublicCdnOrigin}
										bind:publicConsoleOrigin={brandingPublicConsoleOrigin}
										bind:pwaManifestUrl={brandingPwaManifestUrl}
										bind:pwaAssets={brandingPwaAssets}
										appVersion={brandingAppVersion}
										analyticsKeyConfigured={brandingAnalyticsKeyConfigured}
									/>
								</section>
							{:else if activeSection === 'section-media'}
								<section>
									<SettingsMedia
										publicCdnOrigin={brandingPublicCdnOrigin}
										bind:faviconSource={mediaFaviconSource}
										bind:faviconUrl={mediaFaviconUrl}
										bind:appleTouchIconSource={mediaAppleTouchIconSource}
										bind:appleTouchIconUrl={mediaAppleTouchIconUrl}
									/>
								</section>
							{:else if activeSection === 'section-assets'}
								<section>
									<SettingsAssets
										bind:defaultEmbeddingModelId={assetsDefaultEmbeddingModelId}
										bind:vectorDatabaseProvider={assetsVectorDatabaseProvider}
										bind:vectorDatabaseUrl={assetsVectorDatabaseUrl}
										bind:vectorDatabaseQdrantUseGrpc={
											assetsVectorDatabaseQdrantUseGrpc
										}
										bind:vectorDatabaseQdrantApiKey={
											assetsVectorDatabaseQdrantApiKey
										}
										bind:vectorDatabaseChromaApiKey={
											assetsVectorDatabaseChromaApiKey
										}
										bind:vectorDatabasePineconeApiKey={
											assetsVectorDatabasePineconeApiKey
										}
										bind:vectorDatabaseWeaviateApiKey={
											assetsVectorDatabaseWeaviateApiKey
										}
										bind:vectorDatabaseMilvusToken={
											assetsVectorDatabaseMilvusToken
										}
										bind:vectorDatabaseRedisPassword={
											assetsVectorDatabaseRedisPassword
										}
										bind:vectorDatabaseOpensearchApiKey={
											assetsVectorDatabaseOpensearchApiKey
										}
										bind:vectorCollectionTemplate={
											assetsVectorCollectionTemplate
										}
										bind:vectorSparseEnabled={assetsVectorSparseEnabled}
										bind:vectorFusionAlgorithm={assetsVectorFusionAlgorithm}
										bind:vectorNormalizeScores={assetsVectorNormalizeScores}
										bind:embeddingsVectorSize={assetsEmbeddingsVectorSize}
										bind:embeddingsBatchSize={assetsEmbeddingsBatchSize}
										bind:rerankDefaultStrategy={assetsRerankDefaultStrategy}
										bind:rerankTopK={assetsRerankTopK}
										bind:storageBackend={assetsStorageBackend}
										bind:storageLocalRootPath={assetsStorageLocalRootPath}
										bind:storageS3EndpointUrl={assetsStorageS3EndpointUrl}
										bind:storageS3Bucket={assetsStorageS3Bucket}
										bind:storageS3Region={assetsStorageS3Region}
										bind:storageS3AccessKeyId={assetsStorageS3AccessKeyId}
										bind:storageS3SecretAccessKey={
											assetsStorageS3SecretAccessKey
										}
										bind:storageS3Prefix={assetsStorageS3Prefix}
										bind:storageS3PresignedUrlTtl={
											assetsStorageS3PresignedUrlTtl
										}
										bind:storageS3MultipartThreshold={
											assetsStorageS3MultipartThreshold
										}
										bind:storageS3MultipartChunkSize={
											assetsStorageS3MultipartChunkSize
										}
										bind:storageS3MaxRetries={assetsStorageS3MaxRetries}
										bind:storageS3RetryMode={assetsStorageS3RetryMode}
										{models}
										{providers}
										{isFetchingModels}
										{modelsError}
									/>
								</section>
							{:else if activeSection === 'section-limits'}
								<section>
									<SettingsLimits
										bind:maxThreadsPerUser={limitsMaxThreadsPerUser}
										bind:maxMessagesPerThread={limitsMaxMessagesPerThread}
										bind:maxChatInputChars={limitsMaxChatInputChars}
										bind:maxFileSizeMb={limitsMaxFileSizeMb}
										bind:rateLimitRequestsPerMinute={
											limitsRateLimitRequestsPerMinute
										}
										bind:accessibleUsersTtlSeconds={
											cacheAccessibleUsersTtlSeconds
										}
									/>
								</section>
							{:else if activeSection === 'section-soft-delete'}
								<section>
									<SettingsSoftDelete
										bind:threads={softDeleteThreads}
										bind:notes={softDeleteNotes}
										bind:files={softDeleteFiles}
									/>
								</section>
							{:else if activeSection === 'section-web-search'}
								<section>
									<SettingsWebSearch
										bind:maxChars={webSearchMaxChars}
										bind:agenticAgent={webSearchAgenticAgent}
										bind:agenticModelId={webSearchAgenticModelId}
										bind:agenticSystemPrompt={webSearchAgenticSystemPrompt}
										bind:agenticModelParams={webSearchAgenticModelParams}
										bind:agenticMaxIterations={webSearchAgenticMaxIterations}
										bind:blacklistedDomains={webSearchBlacklistedDomains}
										bind:engineEngine={webSearchEngineEngine}
										bind:searxngInstanceUrl={webSearchSearxngInstanceUrl}
										bind:searxngMaxResults={webSearchSearxngMaxResults}
										bind:searxngMaxConcurrentRequests={
											webSearchSearxngMaxConcurrentRequests
										}
										bind:searxngTimeoutSeconds={webSearchSearxngTimeoutSeconds}
										bind:webLoaderEngine={webSearchWebLoaderEngine}
										bind:webLoaderTimeoutSeconds={
											webSearchWebLoaderTimeoutSeconds
										}
										bind:webLoaderUserAgent={webSearchWebLoaderUserAgent}
										bind:webLoaderMaxChars={webSearchWebLoaderMaxChars}
										bind:tavilyExtractDepth={webSearchTavilyExtractDepth}
										bind:tavilyApiKey={webSearchTavilyApiKey}
										bind:tavilyMaxConcurrentRequests={
											webSearchTavilyMaxConcurrentRequests
										}
										bind:perplexityApiKey={webSearchPerplexityApiKey}
										bind:perplexityModel={webSearchPerplexityModel}
										bind:perplexitySearchContextUsage={
											webSearchPerplexitySearchContextUsage
										}
										bind:perplexityTemperature={webSearchPerplexityTemperature}
										bind:perplexityImageResultsEnabled={
											webSearchPerplexityImageResultsEnabled
										}
										bind:perplexityMaxConcurrentRequests={
											webSearchPerplexityMaxConcurrentRequests
										}
										{models}
										{providers}
										{isFetchingModels}
										{modelsError}
									/>
								</section>
							{:else if activeSection === 'section-code-interpreter'}
								<section>
									<SettingsCodeInterpreter
										bind:enabled={codeInterpreterEnabled}
										bind:engine={codeInterpreterEngine}
										bind:e2bApiKey={codeInterpreterE2bApiKey}
										bind:e2bTemplate={codeInterpreterE2bTemplate}
										bind:e2bAvailablePackages={
											codeInterpreterE2bAvailablePackages
										}
										bind:timeout={codeInterpreterTimeout}
									/>
								</section>
							{:else if activeSection === 'section-tasks'}
								<section>
									<SettingsTasks
										{taskiqQueueName}
										{taskiqResultTtlSeconds}
										{taskiqMaxConnections}
										{taskiqAutoWorkersMax}
										{taskiqSchedulePrefix}
										bind:maintenanceInactivityHours={
											taskMaintenanceInactivityHours
										}
										bind:maintenanceQueuedSupersedeAfterMinutes={
											taskMaintenanceQueuedSupersedeAfterMinutes
										}
										bind:maintenanceActiveSupersedeAfterMinutes={
											taskMaintenanceActiveSupersedeAfterMinutes
										}
										bind:maintenanceRunnerTimeoutSeconds={
											taskMaintenanceRunnerTimeoutSeconds
										}
										bind:maintenanceStaleTaskCleanupAfterMinutes={
											taskMaintenanceStaleTaskCleanupAfterMinutes
										}
										bind:backfillEnabled={taskMaintenanceBackfillEnabled}
										bind:backfillCron={taskMaintenanceBackfillCron}
										bind:backfillBatchSize={taskMaintenanceBackfillBatchSize}
										bind:backfillMaxLookbackDays={
											taskMaintenanceBackfillMaxLookbackDays
										}
										bind:backfillMinInactivityHours={
											taskMaintenanceBackfillMinInactivityHours
										}
									/>
								</section>
							{:else if activeSection === 'section-notifications'}
								<section>
									<SettingsNotifications
										bind:webPushEnabled={notificationsWebPushEnabled}
										bind:webPushTtlSeconds={notificationsWebPushTtlSeconds}
										bind:notificationTtlSeconds={
											notificationsNotificationTtlSeconds
										}
										bind:missedGraceDays={notificationsMissedGraceDays}
										bind:lookaheadDays={notificationsLookaheadDays}
										bind:vapidPublicKey={notificationsVapidPublicKey}
										bind:vapidPrivateKey={notificationsVapidPrivateKey}
										{isGeneratingVapidKeys}
										{vapidGenerationError}
										onGenerateVapidKeys={generateVapidKeys}
									/>
								</section>
							{:else if activeSection === 'section-security'}
								<section>
									<SettingsSecurity
										bind:accessTokenExpireMinutes={
											securityAccessTokenExpireMinutes
										}
										bind:refreshTokenExpireDays={securityRefreshTokenExpireDays}
										bind:authCookieSecure={securityAuthCookieSecure}
										bind:sessionTimeoutMinutes={securitySessionTimeoutMinutes}
										bind:requireEmailVerification={
											securityRequireEmailVerification
										}
										bind:allowedEmailDomains={securityAllowedEmailDomains}
										bind:allowSignups={securityAllowSignups}
										bind:autoSignupRoleIds={securityAutoSignupRoleIds}
										bind:oidcEnabled={securityOidcEnabled}
										bind:oidcIssuerUrl={securityOidcIssuerUrl}
										bind:oidcClientId={securityOidcClientId}
										bind:oidcClientSecret={securityOidcClientSecret}
										bind:oidcRedirectUri={securityOidcRedirectUri}
										bind:oidcScopes={securityOidcScopes}
										bind:oidcOnly={securityOidcOnly}
										secretKeyConfigured={securitySecretKeyConfigured}
										secretKeyUsesDefault={securitySecretKeyUsesDefault}
										jwtAlgorithm={securityJwtAlgorithm}
										enableOauth={securityEnableOauth}
										corsOrigins={securityCorsOrigins}
									/>
								</section>
							{:else if activeSection === 'section-permissions'}
								<section>
									<SettingsDefaultPermissions bind:value={defaultPermissions} />
								</section>
							{:else if activeSection === 'section-integrations'}
								<section>
									<SettingsIntegrations />
								</section>
							{/if}
						</div>
					</div>
				</div>
			{:else}
				<div class="rounded-lg border border-zinc-800 p-8 text-zinc-400">
					no settings loaded.
				</div>
			{/if}
		</div>
	</div>
</div>
