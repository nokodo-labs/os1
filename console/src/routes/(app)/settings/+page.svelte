<script lang="ts">
	import { api, unwrap, type BackgroundType, type Schemas } from '$lib/api'

	type Agent = Schemas['Agent']
	type DefaultPermissionsSettings = Schemas['DefaultPermissionsSettings']
	type DefaultPermissionsSettingsPatch = Schemas['DefaultPermissionsSettingsPatch']
	type Model = Schemas['Model']
	type SettingsResponse = Schemas['SettingsResponse']
	type SettingsUpdateRequest = Schemas['SettingsUpdateRequest']

	import NokodoLoader from '$lib/components/NokodoLoader.svelte'
	import SettingsAI from '$lib/components/settings/SettingsAI.svelte'
	import SettingsAssets from '$lib/components/settings/SettingsAssets.svelte'
	import SettingsBranding from '$lib/components/settings/SettingsBranding.svelte'
	import SettingsDefaultPermissions from '$lib/components/settings/SettingsDefaultPermissions.svelte'
	import SettingsLimits from '$lib/components/settings/SettingsLimits.svelte'
	import SettingsMedia from '$lib/components/settings/SettingsMedia.svelte'
	import SettingsSecurity from '$lib/components/settings/SettingsSecurity.svelte'
	import SettingsSoftDelete from '$lib/components/settings/SettingsSoftDelete.svelte'
	import SettingsUI from '$lib/components/settings/SettingsUI.svelte'
	import { Button } from '$lib/components/ui/button'
	import { onMount } from 'svelte'

	type ThemeMode = 'light' | 'dark' | 'system'
	type StorageBackend = 'local' | 's3'

	let isFetching = $state(true)
	let isSaving = $state(false)
	let error = $state<string | null>(null)
	let saveError = $state<string | null>(null)
	let saveSuccess = $state<string | null>(null)

	let response = $state<SettingsResponse | null>(null)

	let isFetchingAgents = $state(false)
	let agentsError = $state<string | null>(null)
	let agents = $state<Agent[]>([])

	let isFetchingModels = $state(false)
	let modelsError = $state<string | null>(null)
	let models = $state<Model[]>([])

	// Read-only (env-only/write-locked) display values
	let brandingAppVersion = $state<string>('')
	let brandingAnalyticsKeyConfigured = $state<boolean>(false)
	let securitySecretKeyConfigured = $state<boolean>(false)
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
		| 'pinecone'
		| 'weaviate'
		| 'milvus'
		| 'pgvector'
		| 'redis'
		| 'opensearch'

	let aiDefaultAgentIds = $state<string[]>([])

	let aiMemoryEnable = $state(false)
	let aiMemorySimilarityThreshold = $state<string>('')
	let aiMemoryTopK = $state<string>('')
	let aiMemoryMessagesToConsider = $state<string>('')

	let aiChatContextMode = $state<ChatContextMode>('recent')
	let aiChatContextTopK = $state<string>('')

	let aiTaskDefaultModelId = $state<string>('')
	let aiTaskThreadMetadataModelId = $state<string>('')
	let aiTaskInputAutocompleteModelId = $state<string>('')
	let aiTaskSummarizationModelId = $state<string>('')

	// attachment decay
	let aiAttachmentImageDecayTurns = $state<string>('')
	let aiAttachmentAudioDecayTurns = $state<string>('')
	let aiAttachmentVideoDecayTurns = $state<string>('')
	let aiAttachmentRevealDecayTurns = $state<string>('')

	// message windowing
	let aiWindowingEnabled = $state(true)
	let aiWindowingMaxMessages = $state<string>('')
	let aiWindowingTriggerRatio = $state<string>('')
	let aiWindowingHardRatio = $state<string>('')
	let aiWindowingSummaryBatchSize = $state<string>('')
	let aiWindowingMaxSummariesBeforeCondense = $state<string>('')
	let aiWindowingToolResultMaxShare = $state<string>('')
	let aiWindowingToolResultHardCap = $state<string>('')
	let aiWindowingToolResultsCombinedMaxShare = $state<string>('')
	let aiWindowingResponseHeadroom = $state<string>('')

	let brandingSiteName = $state('')
	let brandingLogoUrl = $state('')
	let brandingFaviconUrl = $state('')
	let brandingPrimaryColor = $state('')
	let brandingPublicFrontendOrigin = $state('')
	let brandingPublicCdnOrigin = $state('')
	let brandingPwaManifestUrl = $state('')

	let limitsMaxThreadsPerUser = $state<string>('')
	let limitsMaxMessagesPerThread = $state<string>('')
	let limitsMaxFileSizeMb = $state<string>('')
	let limitsRateLimitRequestsPerMinute = $state<string>('')

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
	let assetsVectorDatabaseQdrantApiKey = $state('')
	let assetsVectorDatabasePineconeApiKey = $state('')
	let assetsVectorDatabaseWeaviateApiKey = $state('')
	let assetsVectorDatabaseMilvusToken = $state('')
	let assetsVectorDatabaseRedisPassword = $state('')
	let assetsVectorDatabaseOpensearchApiKey = $state('')
	let assetsVectorCollectionTemplate = $state('')
	let assetsVectorSparseEnabled = $state(true)
	let assetsVectorPrefetchLimit = $state<string>('')
	let assetsVectorFusionAlgorithm = $state('rrf')
	let assetsVectorNormalizeScores = $state(true)
	let assetsEmbeddingsVectorSize = $state<string>('')
	let assetsEmbeddingsBatchSize = $state<string>('')
	let assetsRerankDefaultStrategy = $state('native')
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

	// branding extras
	let brandingPublicConsoleOrigin = $state('')
	let brandingSupportEmail = $state('')
	let brandingAdminEmail = $state('')

	// media
	let mediaBaseUrl = $state('')
	let mediaFaviconUrl = $state('')
	let mediaAppleTouchIconUrl = $state('')
	let mediaSidebarLogoUrl = $state('')
	let mediaSplashLogoUrl = $state('')

	// soft delete
	let softDeleteThreads = $state(true)
	let softDeleteNotes = $state(true)
	let softDeleteFiles = $state(true)

	let defaultPermissions = $state<DefaultPermissionsSettings>({
		resource_access: {
			thread: null,
			project: null,
			file: null,
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
		aiMemoryMessagesToConsider: '',
		aiChatContextMode: 'recent' as ChatContextMode,
		aiChatContextTopK: '',
		aiTaskDefaultModelId: '',
		aiTaskThreadMetadataModelId: '',
		aiTaskInputAutocompleteModelId: '',
		aiTaskSummarizationModelId: '',
		aiAttachmentImageDecayTurns: '',
		aiAttachmentAudioDecayTurns: '',
		aiAttachmentVideoDecayTurns: '',
		aiAttachmentRevealDecayTurns: '',
		aiWindowingEnabled: true,
		aiWindowingMaxMessages: '',
		aiWindowingTriggerRatio: '',
		aiWindowingHardRatio: '',
		aiWindowingSummaryBatchSize: '',
		aiWindowingMaxSummariesBeforeCondense: '',
		aiWindowingToolResultMaxShare: '',
		aiWindowingToolResultHardCap: '',
		aiWindowingToolResultsCombinedMaxShare: '',
		aiWindowingResponseHeadroom: '',
		brandingSiteName: '',
		brandingLogoUrl: '',
		brandingFaviconUrl: '',
		brandingPrimaryColor: '',
		brandingPublicFrontendOrigin: '',
		brandingPublicCdnOrigin: '',
		brandingPublicConsoleOrigin: '',
		brandingPwaManifestUrl: '',
		limitsMaxThreadsPerUser: '',
		limitsMaxMessagesPerThread: '',
		limitsMaxFileSizeMb: '',
		limitsRateLimitRequestsPerMinute: '',
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
		assetsVectorDatabaseQdrantApiKey: '',
		assetsVectorDatabasePineconeApiKey: '',
		assetsVectorDatabaseWeaviateApiKey: '',
		assetsVectorDatabaseMilvusToken: '',
		assetsVectorDatabaseRedisPassword: '',
		assetsVectorDatabaseOpensearchApiKey: '',
		assetsVectorCollectionTemplate: '',
		assetsVectorSparseEnabled: true,
		assetsVectorPrefetchLimit: '',
		assetsVectorFusionAlgorithm: 'rrf',
		assetsVectorNormalizeScores: true,
		assetsEmbeddingsVectorSize: '',
		assetsEmbeddingsBatchSize: '',
		assetsRerankDefaultStrategy: 'native',
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
		brandingSupportEmail: '',
		brandingAdminEmail: '',
		mediaBaseUrl: '',
		mediaFaviconUrl: '',
		mediaAppleTouchIconUrl: '',
		mediaSidebarLogoUrl: '',
		mediaSplashLogoUrl: '',
		softDeleteThreads: true,
		softDeleteNotes: true,
		softDeleteFiles: true,
		defaultPermissions: {
			resource_access: {
				thread: null,
				project: null,
				file: null,
				note: null,
				group: null,
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
			aiMemoryMessagesToConsider !== original.aiMemoryMessagesToConsider ||
			aiChatContextMode !== original.aiChatContextMode ||
			aiChatContextTopK !== original.aiChatContextTopK ||
			aiTaskDefaultModelId !== original.aiTaskDefaultModelId ||
			aiTaskThreadMetadataModelId !== original.aiTaskThreadMetadataModelId ||
			aiTaskInputAutocompleteModelId !== original.aiTaskInputAutocompleteModelId ||
			aiTaskSummarizationModelId !== original.aiTaskSummarizationModelId ||
			aiAttachmentImageDecayTurns !== original.aiAttachmentImageDecayTurns ||
			aiAttachmentAudioDecayTurns !== original.aiAttachmentAudioDecayTurns ||
			aiAttachmentVideoDecayTurns !== original.aiAttachmentVideoDecayTurns ||
			aiAttachmentRevealDecayTurns !== original.aiAttachmentRevealDecayTurns ||
			aiWindowingEnabled !== original.aiWindowingEnabled ||
			aiWindowingMaxMessages !== original.aiWindowingMaxMessages ||
			aiWindowingTriggerRatio !== original.aiWindowingTriggerRatio ||
			aiWindowingHardRatio !== original.aiWindowingHardRatio ||
			aiWindowingSummaryBatchSize !== original.aiWindowingSummaryBatchSize ||
			aiWindowingMaxSummariesBeforeCondense !==
				original.aiWindowingMaxSummariesBeforeCondense ||
			aiWindowingToolResultMaxShare !== original.aiWindowingToolResultMaxShare ||
			aiWindowingToolResultHardCap !== original.aiWindowingToolResultHardCap ||
			aiWindowingToolResultsCombinedMaxShare !==
				original.aiWindowingToolResultsCombinedMaxShare ||
			aiWindowingResponseHeadroom !== original.aiWindowingResponseHeadroom ||
			brandingSiteName !== original.brandingSiteName ||
			brandingLogoUrl !== original.brandingLogoUrl ||
			brandingFaviconUrl !== original.brandingFaviconUrl ||
			brandingPrimaryColor !== original.brandingPrimaryColor ||
			brandingPublicFrontendOrigin !== original.brandingPublicFrontendOrigin ||
			brandingPublicCdnOrigin !== original.brandingPublicCdnOrigin ||
			brandingPublicConsoleOrigin !== original.brandingPublicConsoleOrigin ||
			brandingPwaManifestUrl !== original.brandingPwaManifestUrl ||
			brandingSupportEmail !== original.brandingSupportEmail ||
			brandingAdminEmail !== original.brandingAdminEmail ||
			limitsMaxThreadsPerUser !== original.limitsMaxThreadsPerUser ||
			limitsMaxMessagesPerThread !== original.limitsMaxMessagesPerThread ||
			limitsMaxFileSizeMb !== original.limitsMaxFileSizeMb ||
			limitsRateLimitRequestsPerMinute !== original.limitsRateLimitRequestsPerMinute ||
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
			assetsVectorDatabaseQdrantApiKey !== original.assetsVectorDatabaseQdrantApiKey ||
			assetsVectorDatabasePineconeApiKey !== original.assetsVectorDatabasePineconeApiKey ||
			assetsVectorDatabaseWeaviateApiKey !== original.assetsVectorDatabaseWeaviateApiKey ||
			assetsVectorDatabaseMilvusToken !== original.assetsVectorDatabaseMilvusToken ||
			assetsVectorDatabaseRedisPassword !== original.assetsVectorDatabaseRedisPassword ||
			assetsVectorDatabaseOpensearchApiKey !==
				original.assetsVectorDatabaseOpensearchApiKey ||
			assetsVectorCollectionTemplate !== original.assetsVectorCollectionTemplate ||
			assetsVectorSparseEnabled !== original.assetsVectorSparseEnabled ||
			assetsVectorPrefetchLimit !== original.assetsVectorPrefetchLimit ||
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
			mediaBaseUrl !== original.mediaBaseUrl ||
			mediaFaviconUrl !== original.mediaFaviconUrl ||
			mediaAppleTouchIconUrl !== original.mediaAppleTouchIconUrl ||
			mediaSidebarLogoUrl !== original.mediaSidebarLogoUrl ||
			mediaSplashLogoUrl !== original.mediaSplashLogoUrl ||
			softDeleteThreads !== original.softDeleteThreads ||
			softDeleteNotes !== original.softDeleteNotes ||
			softDeleteFiles !== original.softDeleteFiles ||
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

	function parseCommaList(value: string): string[] {
		return value
			.split(',')
			.map((s) => s.trim())
			.filter(Boolean)
	}

	function normalizeDefaultPermissions(
		input: DefaultPermissionsSettings
	): DefaultPermissionsSettings {
		return {
			resource_access: {
				thread: input.resource_access?.thread ?? null,
				project: input.resource_access?.project ?? null,
				file: input.resource_access?.file ?? null,
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
		aiMemoryMessagesToConsider = toStringOrEmpty(memory?.messages_to_consider)

		const chatContext = ai?.chat_context
		aiChatContextMode = (chatContext?.mode ?? 'recent') as ChatContextMode
		aiChatContextTopK = toStringOrEmpty(chatContext?.top_k)

		const tasks = ai?.tasks
		aiTaskDefaultModelId = tasks?.default_model_id ?? ''
		aiTaskThreadMetadataModelId = tasks?.thread_metadata_model_id ?? ''
		aiTaskInputAutocompleteModelId = tasks?.input_autocomplete_model_id ?? ''
		aiTaskSummarizationModelId = tasks?.summarization_model_id ?? ''

		const attachments = ai?.attachments
		aiAttachmentImageDecayTurns = toStringOrEmpty(attachments?.image_decay_turns)
		aiAttachmentAudioDecayTurns = toStringOrEmpty(attachments?.audio_decay_turns)
		aiAttachmentVideoDecayTurns = toStringOrEmpty(attachments?.video_decay_turns)
		aiAttachmentRevealDecayTurns = toStringOrEmpty(attachments?.reveal_decay_turns)

		const windowing = ai?.windowing
		aiWindowingEnabled = windowing?.enabled ?? true
		aiWindowingMaxMessages = toStringOrEmpty(windowing?.max_messages)
		aiWindowingTriggerRatio = toStringOrEmpty(windowing?.trigger_ratio)
		aiWindowingHardRatio = toStringOrEmpty(windowing?.hard_ratio)
		aiWindowingSummaryBatchSize = toStringOrEmpty(windowing?.summary_batch_size)
		aiWindowingMaxSummariesBeforeCondense = toStringOrEmpty(
			windowing?.max_summaries_before_condense
		)
		aiWindowingToolResultMaxShare = toStringOrEmpty(windowing?.tool_result_max_share)
		aiWindowingToolResultHardCap = toStringOrEmpty(windowing?.tool_result_hard_cap)
		aiWindowingToolResultsCombinedMaxShare = toStringOrEmpty(
			windowing?.tool_results_combined_max_share
		)
		aiWindowingResponseHeadroom = toStringOrEmpty(windowing?.response_headroom)

		const branding = r.data.branding
		brandingSiteName = branding?.site_name ?? ''
		brandingLogoUrl = toStringOrEmpty(branding?.logo_url)
		brandingFaviconUrl = toStringOrEmpty(branding?.favicon_url)
		brandingPrimaryColor = branding?.primary_color ?? ''
		brandingPublicFrontendOrigin = toStringOrEmpty(branding?.public_frontend_origin)
		brandingPublicCdnOrigin = toStringOrEmpty(branding?.public_cdn_origin)
		brandingPublicConsoleOrigin = toStringOrEmpty(branding?.public_console_origin)
		brandingPwaManifestUrl = toStringOrEmpty(branding?.pwa_manifest_url)
		brandingSupportEmail = toStringOrEmpty(branding?.support_email)
		brandingAdminEmail = toStringOrEmpty(branding?.admin_email)

		brandingAppVersion = branding?.app_version ?? ''
		brandingAnalyticsKeyConfigured = Boolean(branding?.analytics_key)

		const media = r.data.media
		mediaBaseUrl = toStringOrEmpty(media?.base_url)
		mediaFaviconUrl = toStringOrEmpty(media?.favicon_url)
		mediaAppleTouchIconUrl = toStringOrEmpty(media?.apple_touch_icon_url)
		mediaSidebarLogoUrl = toStringOrEmpty(media?.sidebar_logo_url)
		mediaSplashLogoUrl = toStringOrEmpty(media?.splash_logo_url)

		const softDelete = r.data.soft_delete
		softDeleteThreads = softDelete?.threads ?? true
		softDeleteNotes = softDelete?.notes ?? true
		softDeleteFiles = softDelete?.files ?? true

		const limits = r.data.limits
		limitsMaxThreadsPerUser = toStringOrEmpty(limits?.max_threads_per_user)
		limitsMaxMessagesPerThread = toStringOrEmpty(limits?.max_messages_per_thread)
		limitsMaxFileSizeMb = toStringOrEmpty(limits?.max_file_size_mb)
		limitsRateLimitRequestsPerMinute = toStringOrEmpty(limits?.rate_limit_requests_per_minute)

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
		securityJwtAlgorithm = security?.jwt_algorithm ?? ''
		securityEnableOauth = toBool(security?.enable_oauth)
		securityCorsOrigins = (security?.cors_origins ?? []).join(', ')

		const assets = r.data.assets
		assetsDefaultEmbeddingModelId = assets?.default_embedding_model_id ?? ''
		const vectorDatabase = assets?.vector_database
		assetsVectorDatabaseProvider =
			(vectorDatabase?.provider as VectorDatabaseProvider) ?? 'qdrant'
		assetsVectorDatabaseUrl = vectorDatabase?.url ?? ''
		const vectorDatabaseApiKeys = vectorDatabase?.api_keys
		assetsVectorDatabaseQdrantApiKey = vectorDatabaseApiKeys?.qdrant_api_key ?? ''
		assetsVectorDatabasePineconeApiKey = vectorDatabaseApiKeys?.pinecone_api_key ?? ''
		assetsVectorDatabaseWeaviateApiKey = vectorDatabaseApiKeys?.weaviate_api_key ?? ''
		assetsVectorDatabaseMilvusToken = vectorDatabaseApiKeys?.milvus_token ?? ''
		assetsVectorDatabaseRedisPassword = vectorDatabaseApiKeys?.redis_password ?? ''
		assetsVectorDatabaseOpensearchApiKey = vectorDatabaseApiKeys?.opensearch_api_key ?? ''
		const vector = assets?.vector
		assetsVectorCollectionTemplate = vector?.collection_template ?? ''
		assetsVectorSparseEnabled = vector?.sparse_vectors_enabled ?? true
		assetsVectorPrefetchLimit = toStringOrEmpty(vector?.prefetch_limit)
		assetsVectorFusionAlgorithm = vector?.fusion_algorithm ?? 'rrf'
		assetsVectorNormalizeScores = vector?.normalize_scores ?? true
		const embeddings = assets?.embeddings
		assetsEmbeddingsVectorSize = toStringOrEmpty(embeddings?.vector_size)
		assetsEmbeddingsBatchSize = toStringOrEmpty(embeddings?.batch_size)
		const rerank = assets?.rerank
		assetsRerankDefaultStrategy = rerank?.default_strategy ?? 'native'
		assetsRerankTopK = toStringOrEmpty(rerank?.top_k)

		const storage = assets?.storage
		assetsStorageBackend = (storage?.backend ?? 'local') as StorageBackend
		assetsStorageLocalRootPath = storage?.local?.root_path ?? ''
		assetsStorageS3EndpointUrl = storage?.s3?.endpoint_url ?? ''
		assetsStorageS3Bucket = storage?.s3?.bucket ?? ''
		assetsStorageS3Region = storage?.s3?.region ?? ''
		assetsStorageS3AccessKeyId = storage?.s3?.access_key_id ?? ''
		assetsStorageS3SecretAccessKey = storage?.s3?.secret_access_key ?? ''
		assetsStorageS3Prefix = storage?.s3?.prefix ?? ''
		assetsStorageS3PresignedUrlTtl = toStringOrEmpty(storage?.s3?.presigned_url_ttl)

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
			aiMemoryMessagesToConsider,
			aiChatContextMode,
			aiChatContextTopK,
			aiTaskDefaultModelId,
			aiTaskThreadMetadataModelId,
			aiTaskInputAutocompleteModelId,
			aiTaskSummarizationModelId,
			aiAttachmentImageDecayTurns,
			aiAttachmentAudioDecayTurns,
			aiAttachmentVideoDecayTurns,
			aiAttachmentRevealDecayTurns,
			aiWindowingEnabled,
			aiWindowingMaxMessages,
			aiWindowingTriggerRatio,
			aiWindowingHardRatio,
			aiWindowingSummaryBatchSize,
			aiWindowingMaxSummariesBeforeCondense,
			aiWindowingToolResultMaxShare,
			aiWindowingToolResultHardCap,
			aiWindowingToolResultsCombinedMaxShare,
			aiWindowingResponseHeadroom,
			brandingSiteName,
			brandingLogoUrl,
			brandingFaviconUrl,
			brandingPrimaryColor,
			brandingPublicFrontendOrigin,
			brandingPublicCdnOrigin,
			brandingPublicConsoleOrigin,
			brandingPwaManifestUrl,
			brandingSupportEmail,
			brandingAdminEmail,
			limitsMaxThreadsPerUser,
			limitsMaxMessagesPerThread,
			limitsMaxFileSizeMb,
			limitsRateLimitRequestsPerMinute,
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
			assetsVectorDatabaseQdrantApiKey,
			assetsVectorDatabasePineconeApiKey,
			assetsVectorDatabaseWeaviateApiKey,
			assetsVectorDatabaseMilvusToken,
			assetsVectorDatabaseRedisPassword,
			assetsVectorDatabaseOpensearchApiKey,
			assetsVectorCollectionTemplate,
			assetsVectorSparseEnabled,
			assetsVectorPrefetchLimit,
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
			mediaBaseUrl,
			mediaFaviconUrl,
			mediaAppleTouchIconUrl,
			mediaSidebarLogoUrl,
			mediaSplashLogoUrl,
			softDeleteThreads,
			softDeleteNotes,
			softDeleteFiles,
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

	function resetDraft() {
		uiDefaultTheme = original.uiDefaultTheme
		uiDefaultBackground = original.uiDefaultBackground
		uiAuthPagesBackground = original.uiAuthPagesBackground
		uiSidebarCollapsed = original.uiSidebarCollapsed
		aiDefaultAgentIds = original.aiDefaultAgentIds
		aiMemoryEnable = original.aiMemoryEnable
		aiMemorySimilarityThreshold = original.aiMemorySimilarityThreshold
		aiMemoryTopK = original.aiMemoryTopK
		aiMemoryMessagesToConsider = original.aiMemoryMessagesToConsider
		aiChatContextMode = original.aiChatContextMode
		aiChatContextTopK = original.aiChatContextTopK
		aiTaskDefaultModelId = original.aiTaskDefaultModelId
		aiTaskThreadMetadataModelId = original.aiTaskThreadMetadataModelId
		aiTaskInputAutocompleteModelId = original.aiTaskInputAutocompleteModelId
		aiTaskSummarizationModelId = original.aiTaskSummarizationModelId
		aiAttachmentImageDecayTurns = original.aiAttachmentImageDecayTurns
		aiAttachmentAudioDecayTurns = original.aiAttachmentAudioDecayTurns
		aiAttachmentVideoDecayTurns = original.aiAttachmentVideoDecayTurns
		aiAttachmentRevealDecayTurns = original.aiAttachmentRevealDecayTurns
		aiWindowingEnabled = original.aiWindowingEnabled
		aiWindowingMaxMessages = original.aiWindowingMaxMessages
		aiWindowingTriggerRatio = original.aiWindowingTriggerRatio
		aiWindowingHardRatio = original.aiWindowingHardRatio
		aiWindowingSummaryBatchSize = original.aiWindowingSummaryBatchSize
		aiWindowingMaxSummariesBeforeCondense = original.aiWindowingMaxSummariesBeforeCondense
		aiWindowingToolResultMaxShare = original.aiWindowingToolResultMaxShare
		aiWindowingToolResultHardCap = original.aiWindowingToolResultHardCap
		aiWindowingToolResultsCombinedMaxShare = original.aiWindowingToolResultsCombinedMaxShare
		aiWindowingResponseHeadroom = original.aiWindowingResponseHeadroom
		brandingSiteName = original.brandingSiteName
		brandingLogoUrl = original.brandingLogoUrl
		brandingFaviconUrl = original.brandingFaviconUrl
		brandingPrimaryColor = original.brandingPrimaryColor
		brandingPublicFrontendOrigin = original.brandingPublicFrontendOrigin
		brandingPublicCdnOrigin = original.brandingPublicCdnOrigin
		brandingPublicConsoleOrigin = original.brandingPublicConsoleOrigin
		brandingPwaManifestUrl = original.brandingPwaManifestUrl
		brandingSupportEmail = original.brandingSupportEmail
		brandingAdminEmail = original.brandingAdminEmail
		limitsMaxThreadsPerUser = original.limitsMaxThreadsPerUser
		limitsMaxMessagesPerThread = original.limitsMaxMessagesPerThread
		limitsMaxFileSizeMb = original.limitsMaxFileSizeMb
		limitsRateLimitRequestsPerMinute = original.limitsRateLimitRequestsPerMinute
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
		assetsVectorDatabaseQdrantApiKey = original.assetsVectorDatabaseQdrantApiKey
		assetsVectorDatabasePineconeApiKey = original.assetsVectorDatabasePineconeApiKey
		assetsVectorDatabaseWeaviateApiKey = original.assetsVectorDatabaseWeaviateApiKey
		assetsVectorDatabaseMilvusToken = original.assetsVectorDatabaseMilvusToken
		assetsVectorDatabaseRedisPassword = original.assetsVectorDatabaseRedisPassword
		assetsVectorDatabaseOpensearchApiKey = original.assetsVectorDatabaseOpensearchApiKey
		assetsVectorCollectionTemplate = original.assetsVectorCollectionTemplate
		assetsVectorSparseEnabled = original.assetsVectorSparseEnabled
		assetsVectorPrefetchLimit = original.assetsVectorPrefetchLimit
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
		mediaBaseUrl = original.mediaBaseUrl
		mediaFaviconUrl = original.mediaFaviconUrl
		mediaAppleTouchIconUrl = original.mediaAppleTouchIconUrl
		mediaSidebarLogoUrl = original.mediaSidebarLogoUrl
		mediaSplashLogoUrl = original.mediaSplashLogoUrl
		softDeleteThreads = original.softDeleteThreads
		softDeleteNotes = original.softDeleteNotes
		softDeleteFiles = original.softDeleteFiles
		defaultPermissions = normalizeDefaultPermissions(original.defaultPermissions)
		saveError = null
		saveSuccess = null
	}

	function asNumberOrNull(s: string): number | null {
		const trimmed = s.trim()
		if (!trimmed) return null
		const n = Number(trimmed)
		return Number.isFinite(n) ? n : null
	}

	function buildDefaultPermissionsPatch(): DefaultPermissionsSettingsPatch {
		return {
			resource_access: {
				thread: defaultPermissions.resource_access?.thread ?? null,
				project: defaultPermissions.resource_access?.project ?? null,
				file: defaultPermissions.resource_access?.file ?? null,
				note: defaultPermissions.resource_access?.note ?? null,
				group: defaultPermissions.resource_access?.group ?? null,
				reminder_list: defaultPermissions.resource_access?.reminder_list ?? null,
			},
			action_permissions: defaultPermissions.action_permissions ?? [],
		}
	}

	function buildUpdateRequest(): SettingsUpdateRequest {
		const data: NonNullable<SettingsUpdateRequest['data']> = {}

		if (
			uiDefaultTheme !== original.uiDefaultTheme ||
			uiDefaultBackground !== original.uiDefaultBackground ||
			uiAuthPagesBackground !== original.uiAuthPagesBackground ||
			uiSidebarCollapsed !== original.uiSidebarCollapsed
		) {
			data.ui = {}
			if (uiDefaultTheme !== original.uiDefaultTheme) data.ui.default_theme = uiDefaultTheme
			if (uiDefaultBackground !== original.uiDefaultBackground)
				data.ui.default_background = uiDefaultBackground ?? null
			if (uiAuthPagesBackground !== original.uiAuthPagesBackground)
				data.ui.auth_pages_background = uiAuthPagesBackground ?? null
			if (uiSidebarCollapsed !== original.uiSidebarCollapsed)
				data.ui.sidebar_collapsed = uiSidebarCollapsed
		}

		if (
			JSON.stringify(aiDefaultAgentIds) !== JSON.stringify(original.aiDefaultAgentIds) ||
			aiMemoryEnable !== original.aiMemoryEnable ||
			aiMemorySimilarityThreshold !== original.aiMemorySimilarityThreshold ||
			aiMemoryTopK !== original.aiMemoryTopK ||
			aiMemoryMessagesToConsider !== original.aiMemoryMessagesToConsider ||
			aiChatContextMode !== original.aiChatContextMode ||
			aiChatContextTopK !== original.aiChatContextTopK ||
			aiTaskDefaultModelId !== original.aiTaskDefaultModelId ||
			aiTaskThreadMetadataModelId !== original.aiTaskThreadMetadataModelId ||
			aiTaskInputAutocompleteModelId !== original.aiTaskInputAutocompleteModelId ||
			aiTaskSummarizationModelId !== original.aiTaskSummarizationModelId ||
			aiAttachmentImageDecayTurns !== original.aiAttachmentImageDecayTurns ||
			aiAttachmentAudioDecayTurns !== original.aiAttachmentAudioDecayTurns ||
			aiAttachmentVideoDecayTurns !== original.aiAttachmentVideoDecayTurns ||
			aiAttachmentRevealDecayTurns !== original.aiAttachmentRevealDecayTurns ||
			aiWindowingEnabled !== original.aiWindowingEnabled ||
			aiWindowingMaxMessages !== original.aiWindowingMaxMessages ||
			aiWindowingTriggerRatio !== original.aiWindowingTriggerRatio ||
			aiWindowingHardRatio !== original.aiWindowingHardRatio ||
			aiWindowingSummaryBatchSize !== original.aiWindowingSummaryBatchSize ||
			aiWindowingMaxSummariesBeforeCondense !==
				original.aiWindowingMaxSummariesBeforeCondense ||
			aiWindowingToolResultMaxShare !== original.aiWindowingToolResultMaxShare ||
			aiWindowingToolResultHardCap !== original.aiWindowingToolResultHardCap ||
			aiWindowingToolResultsCombinedMaxShare !==
				original.aiWindowingToolResultsCombinedMaxShare ||
			aiWindowingResponseHeadroom !== original.aiWindowingResponseHeadroom
		) {
			const aiPatch: NonNullable<NonNullable<SettingsUpdateRequest['data']>['ai']> = {}
			if (JSON.stringify(aiDefaultAgentIds) !== JSON.stringify(original.aiDefaultAgentIds))
				aiPatch.default_agent_ids = aiDefaultAgentIds.length > 0 ? aiDefaultAgentIds : null

			if (
				aiMemoryEnable !== original.aiMemoryEnable ||
				aiMemorySimilarityThreshold !== original.aiMemorySimilarityThreshold ||
				aiMemoryTopK !== original.aiMemoryTopK ||
				aiMemoryMessagesToConsider !== original.aiMemoryMessagesToConsider
			) {
				aiPatch.memory = {}
				if (aiMemoryEnable !== original.aiMemoryEnable)
					aiPatch.memory.enable_memory = aiMemoryEnable
				if (aiMemorySimilarityThreshold !== original.aiMemorySimilarityThreshold)
					aiPatch.memory.similarity_threshold = asNumberOrNull(
						aiMemorySimilarityThreshold
					)
				if (aiMemoryTopK !== original.aiMemoryTopK)
					aiPatch.memory.top_k = asNumberOrNull(aiMemoryTopK)
				if (aiMemoryMessagesToConsider !== original.aiMemoryMessagesToConsider)
					aiPatch.memory.messages_to_consider = asNumberOrNull(aiMemoryMessagesToConsider)
			}

			if (
				aiChatContextMode !== original.aiChatContextMode ||
				aiChatContextTopK !== original.aiChatContextTopK
			) {
				aiPatch.chat_context = {}
				if (aiChatContextMode !== original.aiChatContextMode)
					aiPatch.chat_context.mode = aiChatContextMode
				if (aiChatContextTopK !== original.aiChatContextTopK)
					aiPatch.chat_context.top_k = asNumberOrNull(aiChatContextTopK)
			}

			if (
				aiTaskDefaultModelId !== original.aiTaskDefaultModelId ||
				aiTaskThreadMetadataModelId !== original.aiTaskThreadMetadataModelId ||
				aiTaskInputAutocompleteModelId !== original.aiTaskInputAutocompleteModelId ||
				aiTaskSummarizationModelId !== original.aiTaskSummarizationModelId
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
				if (aiTaskInputAutocompleteModelId !== original.aiTaskInputAutocompleteModelId)
					aiPatch.tasks.input_autocomplete_model_id = aiTaskInputAutocompleteModelId
						? aiTaskInputAutocompleteModelId
						: null
				if (aiTaskSummarizationModelId !== original.aiTaskSummarizationModelId)
					aiPatch.tasks.summarization_model_id = aiTaskSummarizationModelId
						? aiTaskSummarizationModelId
						: null
			}

			if (
				aiAttachmentImageDecayTurns !== original.aiAttachmentImageDecayTurns ||
				aiAttachmentAudioDecayTurns !== original.aiAttachmentAudioDecayTurns ||
				aiAttachmentVideoDecayTurns !== original.aiAttachmentVideoDecayTurns ||
				aiAttachmentRevealDecayTurns !== original.aiAttachmentRevealDecayTurns
			) {
				aiPatch.attachments = {}
				if (aiAttachmentImageDecayTurns !== original.aiAttachmentImageDecayTurns)
					aiPatch.attachments.image_decay_turns = asNumberOrNull(
						aiAttachmentImageDecayTurns
					)
				if (aiAttachmentAudioDecayTurns !== original.aiAttachmentAudioDecayTurns)
					aiPatch.attachments.audio_decay_turns = asNumberOrNull(
						aiAttachmentAudioDecayTurns
					)
				if (aiAttachmentVideoDecayTurns !== original.aiAttachmentVideoDecayTurns)
					aiPatch.attachments.video_decay_turns = asNumberOrNull(
						aiAttachmentVideoDecayTurns
					)
				if (aiAttachmentRevealDecayTurns !== original.aiAttachmentRevealDecayTurns)
					aiPatch.attachments.reveal_decay_turns = asNumberOrNull(
						aiAttachmentRevealDecayTurns
					)
			}

			if (
				aiWindowingEnabled !== original.aiWindowingEnabled ||
				aiWindowingMaxMessages !== original.aiWindowingMaxMessages ||
				aiWindowingTriggerRatio !== original.aiWindowingTriggerRatio ||
				aiWindowingHardRatio !== original.aiWindowingHardRatio ||
				aiWindowingSummaryBatchSize !== original.aiWindowingSummaryBatchSize ||
				aiWindowingMaxSummariesBeforeCondense !==
					original.aiWindowingMaxSummariesBeforeCondense ||
				aiWindowingToolResultMaxShare !== original.aiWindowingToolResultMaxShare ||
				aiWindowingToolResultHardCap !== original.aiWindowingToolResultHardCap ||
				aiWindowingToolResultsCombinedMaxShare !==
					original.aiWindowingToolResultsCombinedMaxShare ||
				aiWindowingResponseHeadroom !== original.aiWindowingResponseHeadroom
			) {
				aiPatch.windowing = {}
				if (aiWindowingEnabled !== original.aiWindowingEnabled)
					aiPatch.windowing.enabled = aiWindowingEnabled
				if (aiWindowingMaxMessages !== original.aiWindowingMaxMessages)
					aiPatch.windowing.max_messages = asNumberOrNull(aiWindowingMaxMessages)
				if (aiWindowingTriggerRatio !== original.aiWindowingTriggerRatio)
					aiPatch.windowing.trigger_ratio = asNumberOrNull(aiWindowingTriggerRatio)
				if (aiWindowingHardRatio !== original.aiWindowingHardRatio)
					aiPatch.windowing.hard_ratio = asNumberOrNull(aiWindowingHardRatio)
				if (aiWindowingSummaryBatchSize !== original.aiWindowingSummaryBatchSize)
					aiPatch.windowing.summary_batch_size = asNumberOrNull(
						aiWindowingSummaryBatchSize
					)
				if (
					aiWindowingMaxSummariesBeforeCondense !==
					original.aiWindowingMaxSummariesBeforeCondense
				)
					aiPatch.windowing.max_summaries_before_condense = asNumberOrNull(
						aiWindowingMaxSummariesBeforeCondense
					)
				if (aiWindowingToolResultMaxShare !== original.aiWindowingToolResultMaxShare)
					aiPatch.windowing.tool_result_max_share = asNumberOrNull(
						aiWindowingToolResultMaxShare
					)
				if (aiWindowingToolResultHardCap !== original.aiWindowingToolResultHardCap)
					aiPatch.windowing.tool_result_hard_cap = asNumberOrNull(
						aiWindowingToolResultHardCap
					)
				if (
					aiWindowingToolResultsCombinedMaxShare !==
					original.aiWindowingToolResultsCombinedMaxShare
				)
					aiPatch.windowing.tool_results_combined_max_share = asNumberOrNull(
						aiWindowingToolResultsCombinedMaxShare
					)
				if (aiWindowingResponseHeadroom !== original.aiWindowingResponseHeadroom)
					aiPatch.windowing.response_headroom = asNumberOrNull(
						aiWindowingResponseHeadroom
					)
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
			if (brandingSupportEmail !== original.brandingSupportEmail)
				data.branding.support_email = brandingSupportEmail || null
			if (brandingAdminEmail !== original.brandingAdminEmail)
				data.branding.admin_email = brandingAdminEmail || null
		}

		if (
			limitsMaxThreadsPerUser !== original.limitsMaxThreadsPerUser ||
			limitsMaxMessagesPerThread !== original.limitsMaxMessagesPerThread ||
			limitsMaxFileSizeMb !== original.limitsMaxFileSizeMb ||
			limitsRateLimitRequestsPerMinute !== original.limitsRateLimitRequestsPerMinute
		) {
			data.limits = {}
			if (limitsMaxThreadsPerUser !== original.limitsMaxThreadsPerUser)
				data.limits.max_threads_per_user = asNumberOrNull(limitsMaxThreadsPerUser)
			if (limitsMaxMessagesPerThread !== original.limitsMaxMessagesPerThread)
				data.limits.max_messages_per_thread = asNumberOrNull(limitsMaxMessagesPerThread)
			if (limitsMaxFileSizeMb !== original.limitsMaxFileSizeMb)
				data.limits.max_file_size_mb = asNumberOrNull(limitsMaxFileSizeMb)
			if (limitsRateLimitRequestsPerMinute !== original.limitsRateLimitRequestsPerMinute)
				data.limits.rate_limit_requests_per_minute = asNumberOrNull(
					limitsRateLimitRequestsPerMinute
				)
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
				data.security.access_token_expire_minutes = asNumberOrNull(
					securityAccessTokenExpireMinutes
				)
			if (securityRefreshTokenExpireDays !== original.securityRefreshTokenExpireDays)
				data.security.refresh_token_expire_days = asNumberOrNull(
					securityRefreshTokenExpireDays
				)
			if (securityAuthCookieSecure !== original.securityAuthCookieSecure)
				data.security.auth_cookie_secure = securityAuthCookieSecure
			if (securitySessionTimeoutMinutes !== original.securitySessionTimeoutMinutes)
				data.security.session_timeout_minutes = asNumberOrNull(
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
			assetsVectorPrefetchLimit !== original.assetsVectorPrefetchLimit ||
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
			assetsStorageS3PresignedUrlTtl !== original.assetsStorageS3PresignedUrlTtl
		) {
			const assetsPatch: Record<string, unknown> = {}
			if (assetsDefaultEmbeddingModelId !== original.assetsDefaultEmbeddingModelId)
				assetsPatch.default_embedding_model_id = assetsDefaultEmbeddingModelId || null

			if (
				assetsVectorDatabaseProvider !== original.assetsVectorDatabaseProvider ||
				assetsVectorDatabaseUrl !== original.assetsVectorDatabaseUrl ||
				assetsVectorDatabaseQdrantApiKey !== original.assetsVectorDatabaseQdrantApiKey ||
				assetsVectorDatabasePineconeApiKey !==
					original.assetsVectorDatabasePineconeApiKey ||
				assetsVectorDatabaseWeaviateApiKey !==
					original.assetsVectorDatabaseWeaviateApiKey ||
				assetsVectorDatabaseMilvusToken !== original.assetsVectorDatabaseMilvusToken ||
				assetsVectorDatabaseRedisPassword !== original.assetsVectorDatabaseRedisPassword ||
				assetsVectorDatabaseOpensearchApiKey !==
					original.assetsVectorDatabaseOpensearchApiKey
			) {
				const vectorDatabasePatch: Record<string, unknown> = {}
				if (assetsVectorDatabaseProvider !== original.assetsVectorDatabaseProvider)
					vectorDatabasePatch.provider = assetsVectorDatabaseProvider
				if (assetsVectorDatabaseUrl !== original.assetsVectorDatabaseUrl)
					vectorDatabasePatch.url = assetsVectorDatabaseUrl || null

				if (
					assetsVectorDatabaseQdrantApiKey !==
						original.assetsVectorDatabaseQdrantApiKey ||
					assetsVectorDatabasePineconeApiKey !==
						original.assetsVectorDatabasePineconeApiKey ||
					assetsVectorDatabaseWeaviateApiKey !==
						original.assetsVectorDatabaseWeaviateApiKey ||
					assetsVectorDatabaseMilvusToken !== original.assetsVectorDatabaseMilvusToken ||
					assetsVectorDatabaseRedisPassword !==
						original.assetsVectorDatabaseRedisPassword ||
					assetsVectorDatabaseOpensearchApiKey !==
						original.assetsVectorDatabaseOpensearchApiKey
				) {
					const apiKeysPatch: Record<string, unknown> = {}
					if (
						assetsVectorDatabaseQdrantApiKey !==
						original.assetsVectorDatabaseQdrantApiKey
					)
						apiKeysPatch.qdrant_api_key = assetsVectorDatabaseQdrantApiKey || null
					if (
						assetsVectorDatabasePineconeApiKey !==
						original.assetsVectorDatabasePineconeApiKey
					)
						apiKeysPatch.pinecone_api_key = assetsVectorDatabasePineconeApiKey || null
					if (
						assetsVectorDatabaseWeaviateApiKey !==
						original.assetsVectorDatabaseWeaviateApiKey
					)
						apiKeysPatch.weaviate_api_key = assetsVectorDatabaseWeaviateApiKey || null
					if (
						assetsVectorDatabaseMilvusToken !== original.assetsVectorDatabaseMilvusToken
					)
						apiKeysPatch.milvus_token = assetsVectorDatabaseMilvusToken || null
					if (
						assetsVectorDatabaseRedisPassword !==
						original.assetsVectorDatabaseRedisPassword
					)
						apiKeysPatch.redis_password = assetsVectorDatabaseRedisPassword || null
					if (
						assetsVectorDatabaseOpensearchApiKey !==
						original.assetsVectorDatabaseOpensearchApiKey
					)
						apiKeysPatch.opensearch_api_key =
							assetsVectorDatabaseOpensearchApiKey || null
					vectorDatabasePatch.api_keys = apiKeysPatch
				}

				assetsPatch.vector_database = vectorDatabasePatch
			}

			if (
				assetsVectorCollectionTemplate !== original.assetsVectorCollectionTemplate ||
				assetsVectorSparseEnabled !== original.assetsVectorSparseEnabled ||
				assetsVectorPrefetchLimit !== original.assetsVectorPrefetchLimit ||
				assetsVectorFusionAlgorithm !== original.assetsVectorFusionAlgorithm ||
				assetsVectorNormalizeScores !== original.assetsVectorNormalizeScores
			) {
				const vectorPatch: Record<string, unknown> = {}
				if (assetsVectorCollectionTemplate !== original.assetsVectorCollectionTemplate)
					vectorPatch.collection_template = assetsVectorCollectionTemplate || null
				if (assetsVectorSparseEnabled !== original.assetsVectorSparseEnabled)
					vectorPatch.sparse_vectors_enabled = assetsVectorSparseEnabled
				if (assetsVectorPrefetchLimit !== original.assetsVectorPrefetchLimit)
					vectorPatch.prefetch_limit = asNumberOrNull(assetsVectorPrefetchLimit)
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
				const embPatch: Record<string, unknown> = {}
				if (assetsEmbeddingsVectorSize !== original.assetsEmbeddingsVectorSize)
					embPatch.vector_size = asNumberOrNull(assetsEmbeddingsVectorSize)
				if (assetsEmbeddingsBatchSize !== original.assetsEmbeddingsBatchSize)
					embPatch.batch_size = asNumberOrNull(assetsEmbeddingsBatchSize)
				assetsPatch.embeddings = embPatch
			}

			if (
				assetsRerankDefaultStrategy !== original.assetsRerankDefaultStrategy ||
				assetsRerankTopK !== original.assetsRerankTopK
			) {
				const rerankPatch: Record<string, unknown> = {}
				if (assetsRerankDefaultStrategy !== original.assetsRerankDefaultStrategy)
					rerankPatch.default_strategy = assetsRerankDefaultStrategy || null
				if (assetsRerankTopK !== original.assetsRerankTopK)
					rerankPatch.top_k = asNumberOrNull(assetsRerankTopK)
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
				assetsStorageS3PresignedUrlTtl !== original.assetsStorageS3PresignedUrlTtl
			) {
				const storagePatch: Record<string, unknown> = {}
				if (assetsStorageBackend !== original.assetsStorageBackend)
					storagePatch.backend = assetsStorageBackend
				if (
					assetsStorageLocalRootPath !== original.assetsStorageLocalRootPath &&
					assetsStorageBackend === 'local'
				) {
					storagePatch.local = { root_path: assetsStorageLocalRootPath || null }
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
							original.assetsStorageS3PresignedUrlTtl) &&
					assetsStorageBackend === 's3'
				) {
					const s3Patch: Record<string, unknown> = {}
					if (assetsStorageS3EndpointUrl !== original.assetsStorageS3EndpointUrl)
						s3Patch.endpoint_url = assetsStorageS3EndpointUrl || null
					if (assetsStorageS3Bucket !== original.assetsStorageS3Bucket)
						s3Patch.bucket = assetsStorageS3Bucket || null
					if (assetsStorageS3Region !== original.assetsStorageS3Region)
						s3Patch.region = assetsStorageS3Region || null
					if (assetsStorageS3AccessKeyId !== original.assetsStorageS3AccessKeyId)
						s3Patch.access_key_id = assetsStorageS3AccessKeyId || null
					if (assetsStorageS3SecretAccessKey !== original.assetsStorageS3SecretAccessKey)
						s3Patch.secret_access_key = assetsStorageS3SecretAccessKey || null
					if (assetsStorageS3Prefix !== original.assetsStorageS3Prefix)
						s3Patch.prefix = assetsStorageS3Prefix || null
					if (assetsStorageS3PresignedUrlTtl !== original.assetsStorageS3PresignedUrlTtl)
						s3Patch.presigned_url_ttl = asNumberOrNull(assetsStorageS3PresignedUrlTtl)
					storagePatch.s3 = s3Patch
				}
				assetsPatch.storage = storagePatch
			}

			data.assets = assetsPatch
		}

		if (
			mediaBaseUrl !== original.mediaBaseUrl ||
			mediaFaviconUrl !== original.mediaFaviconUrl ||
			mediaAppleTouchIconUrl !== original.mediaAppleTouchIconUrl ||
			mediaSidebarLogoUrl !== original.mediaSidebarLogoUrl ||
			mediaSplashLogoUrl !== original.mediaSplashLogoUrl
		) {
			data.media = {}
			if (mediaBaseUrl !== original.mediaBaseUrl) data.media.base_url = mediaBaseUrl || null
			if (mediaFaviconUrl !== original.mediaFaviconUrl)
				data.media.favicon_url = mediaFaviconUrl || null
			if (mediaAppleTouchIconUrl !== original.mediaAppleTouchIconUrl)
				data.media.apple_touch_icon_url = mediaAppleTouchIconUrl || null
			if (mediaSidebarLogoUrl !== original.mediaSidebarLogoUrl)
				data.media.sidebar_logo_url = mediaSidebarLogoUrl || null
			if (mediaSplashLogoUrl !== original.mediaSplashLogoUrl)
				data.media.splash_logo_url = mediaSplashLogoUrl || null
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

	onMount(() => {
		Promise.all([fetchSettings(), fetchAgents(), fetchModels()])
	})
</script>

<div class="flex min-h-0 flex-1 flex-col gap-6">
	<div class="flex shrink-0 flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
		<div>
			<h2 class="text-2xl font-bold tracking-tight">settings</h2>
			<p class="text-zinc-400">manage backend settings (admin only).</p>
		</div>
		<div class="flex items-center gap-2">
			<Button variant="secondary" onclick={fetchSettings} disabled={isFetching || isSaving}
				>reload</Button
			>
			<Button
				variant="secondary"
				onclick={resetDraft}
				disabled={!response || isFetching || isSaving || !hasChanges}>reset</Button
			>
			<Button onclick={save} disabled={!response || isFetching || isSaving || !hasChanges}
				>{isSaving ? 'saving…' : 'save'}</Button
			>
		</div>
	</div>

	<div class="min-h-0 flex-1 overflow-y-auto">
		<div class="flex min-h-0 flex-1 flex-col gap-6">
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
				<div class="space-y-6">
					<SettingsUI
						bind:defaultTheme={uiDefaultTheme}
						bind:defaultBackground={uiDefaultBackground}
						bind:authPagesBackground={uiAuthPagesBackground}
						bind:sidebarCollapsed={uiSidebarCollapsed}
					/>

					<SettingsAI
						bind:defaultAgentIds={aiDefaultAgentIds}
						bind:memoryEnable={aiMemoryEnable}
						bind:memorySimilarityThreshold={aiMemorySimilarityThreshold}
						bind:memoryTopK={aiMemoryTopK}
						bind:memoryMessagesToConsider={aiMemoryMessagesToConsider}
						bind:chatContextMode={aiChatContextMode}
						bind:chatContextTopK={aiChatContextTopK}
						bind:taskDefaultModelId={aiTaskDefaultModelId}
						bind:taskThreadMetadataModelId={aiTaskThreadMetadataModelId}
						bind:taskInputAutocompleteModelId={aiTaskInputAutocompleteModelId}
						bind:taskSummarizationModelId={aiTaskSummarizationModelId}
						bind:attachmentImageDecayTurns={aiAttachmentImageDecayTurns}
						bind:attachmentAudioDecayTurns={aiAttachmentAudioDecayTurns}
						bind:attachmentVideoDecayTurns={aiAttachmentVideoDecayTurns}
						bind:attachmentRevealDecayTurns={aiAttachmentRevealDecayTurns}
						bind:windowingEnabled={aiWindowingEnabled}
						bind:windowingMaxMessages={aiWindowingMaxMessages}
						bind:windowingTriggerRatio={aiWindowingTriggerRatio}
						bind:windowingHardRatio={aiWindowingHardRatio}
						bind:windowingSummaryBatchSize={aiWindowingSummaryBatchSize}
						bind:windowingMaxSummariesBeforeCondense={
							aiWindowingMaxSummariesBeforeCondense
						}
						bind:windowingToolResultMaxShare={aiWindowingToolResultMaxShare}
						bind:windowingToolResultHardCap={aiWindowingToolResultHardCap}
						bind:windowingToolResultsCombinedMaxShare={
							aiWindowingToolResultsCombinedMaxShare
						}
						bind:windowingResponseHeadroom={aiWindowingResponseHeadroom}
						{agents}
						{models}
						{isFetchingAgents}
						{isFetchingModels}
						{agentsError}
						{modelsError}
					/>

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
						appVersion={brandingAppVersion}
						analyticsKeyConfigured={brandingAnalyticsKeyConfigured}
					/>

					<SettingsMedia
						bind:baseUrl={mediaBaseUrl}
						bind:faviconUrl={mediaFaviconUrl}
						bind:appleTouchIconUrl={mediaAppleTouchIconUrl}
						bind:sidebarLogoUrl={mediaSidebarLogoUrl}
						bind:splashLogoUrl={mediaSplashLogoUrl}
					/>

					<SettingsAssets
						bind:defaultEmbeddingModelId={assetsDefaultEmbeddingModelId}
						bind:vectorDatabaseProvider={assetsVectorDatabaseProvider}
						bind:vectorDatabaseUrl={assetsVectorDatabaseUrl}
						bind:vectorDatabaseQdrantApiKey={assetsVectorDatabaseQdrantApiKey}
						bind:vectorDatabasePineconeApiKey={assetsVectorDatabasePineconeApiKey}
						bind:vectorDatabaseWeaviateApiKey={assetsVectorDatabaseWeaviateApiKey}
						bind:vectorDatabaseMilvusToken={assetsVectorDatabaseMilvusToken}
						bind:vectorDatabaseRedisPassword={assetsVectorDatabaseRedisPassword}
						bind:vectorDatabaseOpensearchApiKey={assetsVectorDatabaseOpensearchApiKey}
						bind:vectorCollectionTemplate={assetsVectorCollectionTemplate}
						bind:vectorSparseEnabled={assetsVectorSparseEnabled}
						bind:vectorPrefetchLimit={assetsVectorPrefetchLimit}
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
						bind:storageS3SecretAccessKey={assetsStorageS3SecretAccessKey}
						bind:storageS3Prefix={assetsStorageS3Prefix}
						bind:storageS3PresignedUrlTtl={assetsStorageS3PresignedUrlTtl}
						{models}
						{isFetchingModels}
						{modelsError}
					/>

					<SettingsLimits
						bind:maxThreadsPerUser={limitsMaxThreadsPerUser}
						bind:maxMessagesPerThread={limitsMaxMessagesPerThread}
						bind:maxFileSizeMb={limitsMaxFileSizeMb}
						bind:rateLimitRequestsPerMinute={limitsRateLimitRequestsPerMinute}
					/>

					<SettingsSoftDelete
						bind:threads={softDeleteThreads}
						bind:notes={softDeleteNotes}
						bind:files={softDeleteFiles}
					/>

					<SettingsSecurity
						bind:accessTokenExpireMinutes={securityAccessTokenExpireMinutes}
						bind:refreshTokenExpireDays={securityRefreshTokenExpireDays}
						bind:authCookieSecure={securityAuthCookieSecure}
						bind:sessionTimeoutMinutes={securitySessionTimeoutMinutes}
						bind:requireEmailVerification={securityRequireEmailVerification}
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
						jwtAlgorithm={securityJwtAlgorithm}
						enableOauth={securityEnableOauth}
						corsOrigins={securityCorsOrigins}
					/>

					<SettingsDefaultPermissions bind:value={defaultPermissions} />
				</div>
			{:else}
				<div class="rounded-lg border border-zinc-800 p-8 text-zinc-400">
					no settings loaded.
				</div>
			{/if}
		</div>
	</div>
</div>
