<script lang="ts">
	import { api, unwrap, type BackgroundType, type Schemas } from '$lib/api'

	type Agent = Schemas['Agent']
	type DefaultPermissionsSettings = Schemas['DefaultPermissionsSettings']
	type DefaultPermissionsSettingsPatch = Schemas['DefaultPermissionsSettingsPatch']
	type Model = Schemas['Model']
	type SettingsResponse = Schemas['SettingsResponse']
	type SettingsUpdateRequest = Schemas['SettingsUpdateRequest']

	import DefaultPermissionsEditor from '$lib/components/DefaultPermissionsEditor.svelte'
	import NokodoLoader from '$lib/components/NokodoLoader.svelte'
	import RolePicker from '$lib/components/RolePicker.svelte'
	import { Button } from '$lib/components/ui/button'
	import {
		Card,
		CardContent,
		CardDescription,
		CardHeader,
		CardTitle,
	} from '$lib/components/ui/card'
	import { Input } from '$lib/components/ui/input'
	import { Label } from '$lib/components/ui/label'
	import { Select, SelectContent, SelectItem, SelectTrigger } from '$lib/components/ui/select'
	import { Switch } from '$lib/components/ui/switch'
	import { ChevronDown, ChevronUp, Lock, X } from '@lucide/svelte'
	import { onMount } from 'svelte'

	type ThemeMode = 'light' | 'dark' | 'system'

	function themeLabel(v: ThemeMode): string {
		if (v === 'light') return 'light'
		if (v === 'dark') return 'dark'
		return 'system'
	}

	const backgroundOptions: { value: BackgroundType; label: string }[] = [
		{ value: 'galaxy', label: 'galaxy' },
		{ value: 'darkveil', label: 'dark veil' },
		{ value: 'lightbends', label: 'light bends' },
		{ value: 'lightrays', label: 'light rays' },
		{ value: 'silk', label: 'silk' },
		{ value: 'static', label: 'static' },
		{ value: 'none', label: 'none' },
	]

	function backgroundLabel(v: string): string {
		return backgroundOptions.find((o) => o.value === v)?.label ?? v
	}

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

	// branding extras
	let brandingPublicConsoleOrigin = $state('')

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
		brandingSiteName: '',
		brandingLogoUrl: '',
		brandingFaviconUrl: '',
		brandingPrimaryColor: '',
		brandingPublicFrontendOrigin: '',
		brandingPublicCdnOrigin: '',
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
		brandingPublicConsoleOrigin: '',
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
			brandingSiteName !== original.brandingSiteName ||
			brandingLogoUrl !== original.brandingLogoUrl ||
			brandingFaviconUrl !== original.brandingFaviconUrl ||
			brandingPrimaryColor !== original.brandingPrimaryColor ||
			brandingPublicFrontendOrigin !== original.brandingPublicFrontendOrigin ||
			brandingPublicCdnOrigin !== original.brandingPublicCdnOrigin ||
			brandingPwaManifestUrl !== original.brandingPwaManifestUrl ||
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
			brandingPublicConsoleOrigin !== original.brandingPublicConsoleOrigin ||
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

	function agentLabel(a: Agent): string {
		return a.name || a.id
	}

	function modelLabel(m: Model): string {
		return m.display_name || m.name || m.id
	}

	function getModelLabel(modelId: string): string {
		if (!modelId) return 'none'
		const m = models.find((x) => x.id === modelId)
		return m ? modelLabel(m) : modelId
	}

	const selectedAgentLabel = $derived(() => {
		if (aiDefaultAgentIds.length === 0) return 'none'
		return aiDefaultAgentIds
			.map((id) => {
				const a = agents.find((x) => x.id === id)
				return a ? agentLabel(a) : id
			})
			.join(', ')
	})

	const availableAgentsToAdd = $derived(agents.filter((a) => !aiDefaultAgentIds.includes(a.id)))

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

		const branding = r.data.branding
		brandingSiteName = branding?.site_name ?? ''
		brandingLogoUrl = toStringOrEmpty(branding?.logo_url)
		brandingFaviconUrl = toStringOrEmpty(branding?.favicon_url)
		brandingPrimaryColor = branding?.primary_color ?? ''
		brandingPublicFrontendOrigin = toStringOrEmpty(branding?.public_frontend_origin)
		brandingPublicCdnOrigin = toStringOrEmpty(branding?.public_cdn_origin)
		brandingPublicConsoleOrigin = toStringOrEmpty(branding?.public_console_origin)
		brandingPwaManifestUrl = toStringOrEmpty(branding?.pwa_manifest_url)

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
			brandingSiteName,
			brandingLogoUrl,
			brandingFaviconUrl,
			brandingPrimaryColor,
			brandingPublicFrontendOrigin,
			brandingPublicCdnOrigin,
			brandingPublicConsoleOrigin,
			brandingPwaManifestUrl,
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
			models = [...list].sort((a, b) => modelLabel(a).localeCompare(modelLabel(b)))
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
		brandingSiteName = original.brandingSiteName
		brandingLogoUrl = original.brandingLogoUrl
		brandingFaviconUrl = original.brandingFaviconUrl
		brandingPrimaryColor = original.brandingPrimaryColor
		brandingPublicFrontendOrigin = original.brandingPublicFrontendOrigin
		brandingPublicCdnOrigin = original.brandingPublicCdnOrigin
		brandingPublicConsoleOrigin = original.brandingPublicConsoleOrigin
		brandingPwaManifestUrl = original.brandingPwaManifestUrl
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
		brandingPublicConsoleOrigin = original.brandingPublicConsoleOrigin
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
			aiTaskInputAutocompleteModelId !== original.aiTaskInputAutocompleteModelId
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
				aiTaskInputAutocompleteModelId !== original.aiTaskInputAutocompleteModelId
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
			brandingPwaManifestUrl !== original.brandingPwaManifestUrl
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
			assetsRerankTopK !== original.assetsRerankTopK
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
					<Card class="border-zinc-800 bg-zinc-900">
						<CardHeader>
							<CardTitle>ui</CardTitle>
							<CardDescription>console UX defaults.</CardDescription>
						</CardHeader>
						<CardContent class="space-y-5">
							<div class="space-y-2">
								<Label for="default_theme">default theme</Label>
								<p class="text-xs text-zinc-500">
									color scheme applied to the frontend app by default.
								</p>
								<Select
									value={uiDefaultTheme}
									onValueChange={(v: string) => (uiDefaultTheme = v as ThemeMode)}
								>
									<SelectTrigger id="default_theme" class="rounded-xl">
										<span class="truncate text-left"
											>{themeLabel(uiDefaultTheme)}</span
										>
									</SelectTrigger>
									<SelectContent>
										<SelectItem value="system">system</SelectItem>
										<SelectItem value="light">light</SelectItem>
										<SelectItem value="dark">dark</SelectItem>
									</SelectContent>
								</Select>
							</div>

							<div class="flex items-center justify-between">
								<div class="space-y-0.5">
									<Label for="sidebar_collapsed">sidebar collapsed</Label>
									<p class="text-xs text-zinc-500">
										collapse sidebar by default.
									</p>
								</div>
								<Switch
									id="sidebar_collapsed"
									checked={uiSidebarCollapsed}
									onCheckedChange={(v: boolean) => (uiSidebarCollapsed = v)}
								/>
							</div>

							<div class="space-y-2">
								<Label for="default_background">default background</Label>
								<p class="text-xs text-zinc-500">
									animated background shown in the main app interface.
								</p>
								<Select
									value={uiDefaultBackground || 'darkveil'}
									onValueChange={(v: string) =>
										(uiDefaultBackground = v as BackgroundType)}
								>
									<SelectTrigger id="default_background" class="rounded-xl">
										<span class="truncate text-left"
											>{backgroundLabel(
												uiDefaultBackground || 'darkveil'
											)}</span
										>
									</SelectTrigger>
									<SelectContent>
										{#each backgroundOptions as opt (opt.value)}
											<SelectItem value={opt.value}>{opt.label}</SelectItem>
										{/each}
									</SelectContent>
								</Select>
							</div>

							<div class="space-y-2">
								<Label for="auth_pages_background">auth pages background</Label>
								<p class="text-xs text-zinc-500">
									animated background shown on login and signup pages.
								</p>
								<Select
									value={uiAuthPagesBackground || 'lightrays'}
									onValueChange={(v: string) =>
										(uiAuthPagesBackground = v as BackgroundType)}
								>
									<SelectTrigger id="auth_pages_background" class="rounded-xl">
										<span class="truncate text-left"
											>{backgroundLabel(
												uiAuthPagesBackground || 'lightrays'
											)}</span
										>
									</SelectTrigger>
									<SelectContent>
										{#each backgroundOptions as opt (opt.value)}
											<SelectItem value={opt.value}>{opt.label}</SelectItem>
										{/each}
									</SelectContent>
								</Select>
							</div>
						</CardContent>
					</Card>

					<Card class="border-zinc-800 bg-zinc-900">
						<CardHeader>
							<CardTitle>ai</CardTitle>
							<CardDescription>agent defaults and behavior.</CardDescription>
						</CardHeader>
						<CardContent class="space-y-6">
							<div class="space-y-2">
								<div class="flex items-center justify-between gap-2">
									<div>
										<Label for="default_agents">default agents</Label>
										<p class="text-xs text-zinc-500">
											tried in order; first available agent is used.
										</p>
									</div>
									{#if isFetchingAgents}
										<span class="text-xs text-zinc-500">loading…</span>
									{/if}
								</div>
								{#if aiDefaultAgentIds.length > 0}
									<ul class="space-y-1">
										{#each aiDefaultAgentIds as agentId, idx (agentId)}
											{@const label = agents.find((x) => x.id === agentId)}
											<li
												class="flex items-center gap-2 rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2 text-sm"
											>
												<span
													class="w-5 shrink-0 font-mono text-xs text-zinc-500"
													>{idx + 1}.</span
												>
												<span class="flex-1 truncate"
													>{label ? agentLabel(label) : agentId}</span
												>
												<button
													class="text-zinc-500 hover:text-zinc-300 disabled:opacity-30"
													disabled={idx === 0}
													onclick={() => {
														const copy = [...aiDefaultAgentIds]
														;[copy[idx - 1], copy[idx]] = [
															copy[idx],
															copy[idx - 1],
														]
														aiDefaultAgentIds = copy
													}}
													title="move up"
												>
													<ChevronUp class="h-4 w-4" />
												</button>
												<button
													class="text-zinc-500 hover:text-zinc-300 disabled:opacity-30"
													disabled={idx === aiDefaultAgentIds.length - 1}
													onclick={() => {
														const copy = [...aiDefaultAgentIds]
														;[copy[idx], copy[idx + 1]] = [
															copy[idx + 1],
															copy[idx],
														]
														aiDefaultAgentIds = copy
													}}
													title="move down"
												>
													<ChevronDown class="h-4 w-4" />
												</button>
												<button
													class="text-zinc-500 hover:text-red-400"
													onclick={() => {
														aiDefaultAgentIds =
															aiDefaultAgentIds.filter(
																(_, i) => i !== idx
															)
													}}
													title="remove"
												>
													<X class="h-4 w-4" />
												</button>
											</li>
										{/each}
									</ul>
								{:else}
									<p class="text-xs text-zinc-500 italic">
										no default agents configured
									</p>
								{/if}
								{#if availableAgentsToAdd.length > 0}
									<Select
										value=""
										onValueChange={(v: string) => {
											if (v) aiDefaultAgentIds = [...aiDefaultAgentIds, v]
										}}
									>
										<SelectTrigger id="default_agents" class="rounded-xl">
											<span class="text-zinc-500">add agent…</span>
										</SelectTrigger>
										<SelectContent>
											{#each availableAgentsToAdd as a (a.id)}
												<SelectItem value={a.id}>{agentLabel(a)}</SelectItem
												>
											{/each}
										</SelectContent>
									</Select>
								{/if}
								{#if agentsError}
									<p class="text-xs text-red-300">{agentsError}</p>
								{/if}
							</div>

							<div class="rounded-xl border border-zinc-800 bg-zinc-950 p-4">
								<div class="mb-4 flex items-center justify-between">
									<div>
										<p class="text-sm font-medium">memory</p>
										<p class="text-xs text-zinc-500">
											retrieval and consolidation settings.
										</p>
									</div>
									<Switch
										id="ai_memory_enable"
										checked={aiMemoryEnable}
										onCheckedChange={(v: boolean) => (aiMemoryEnable = v)}
									/>
								</div>
								<div class="grid gap-4 md:grid-cols-2">
									<div class="space-y-2">
										<Label for="ai_similarity">similarity threshold</Label>
										<p class="text-xs text-zinc-500">
											minimum cosine similarity for a memory to be retrieved
											(0 = any, 1 = exact).
										</p>
										<Input
											id="ai_similarity"
											type="number"
											step="0.01"
											min="0"
											max="1"
											bind:value={aiMemorySimilarityThreshold}
											class="rounded-xl"
										/>
									</div>
									<div class="space-y-2">
										<Label for="ai_top_k">top k</Label>
										<p class="text-xs text-zinc-500">
											max memories retrieved per conversation turn.
										</p>
										<Input
											id="ai_top_k"
											type="number"
											min="1"
											bind:value={aiMemoryTopK}
											class="rounded-xl"
										/>
									</div>
									<div class="space-y-2">
										<Label for="ai_messages">messages to consider</Label>
										<p class="text-xs text-zinc-500">
											recent messages scanned when retrieving or consolidating
											memories.
										</p>
										<Input
											id="ai_messages"
											type="number"
											min="1"
											bind:value={aiMemoryMessagesToConsider}
											class="rounded-xl"
										/>
									</div>
								</div>
							</div>

							<div class="rounded-xl border border-zinc-800 bg-zinc-950 p-4">
								<p class="mb-1 text-sm font-medium">chat context</p>
								<p class="mb-4 text-xs text-zinc-500">
									how prior chats are added to context.
								</p>
								<div class="grid gap-4 md:grid-cols-2">
									<div class="space-y-2">
										<Label for="ai_chat_mode">mode</Label>
										<p class="text-xs text-zinc-500">
											determines which past chats are included in the agent's
											context window.
										</p>
										<Select
											value={aiChatContextMode}
											onValueChange={(v: string) =>
												(aiChatContextMode = v as ChatContextMode)}
										>
											<SelectTrigger id="ai_chat_mode" class="rounded-xl">
												<span class="truncate text-left"
													>{aiChatContextMode}</span
												>
											</SelectTrigger>
											<SelectContent>
												<SelectItem value="recent">recent</SelectItem>
												<SelectItem value="relevant">relevant</SelectItem>
												<SelectItem value="pinned">pinned</SelectItem>
											</SelectContent>
										</Select>
									</div>
									<div class="space-y-2">
										<Label for="ai_chat_top_k">top k</Label>
										<p class="text-xs text-zinc-500">
											number of past chats to include in context per turn.
										</p>
										<Input
											id="ai_chat_top_k"
											type="number"
											min="1"
											bind:value={aiChatContextTopK}
											class="rounded-xl"
										/>
									</div>
								</div>
							</div>

							<div class="rounded-xl border border-zinc-800 bg-zinc-950 p-4">
								<div class="mb-4 flex items-center justify-between">
									<div>
										<p class="text-sm font-medium">task models</p>
										<p class="text-xs text-zinc-500">
											overrides for background task runs.
										</p>
									</div>
									{#if isFetchingModels}
										<span class="text-xs text-zinc-500">loading…</span>
									{/if}
								</div>
								<div class="grid gap-4 md:grid-cols-2">
									<div class="space-y-2">
										<Label for="task_default_model">default model</Label>
										<p class="text-xs text-zinc-500">
											fallback model used when no task-specific model is set.
										</p>
										<Select
											value={aiTaskDefaultModelId}
											onValueChange={(v: string) =>
												(aiTaskDefaultModelId = v)}
										>
											<SelectTrigger
												id="task_default_model"
												class="rounded-xl"
											>
												<span class="truncate text-left"
													>{getModelLabel(aiTaskDefaultModelId)}</span
												>
											</SelectTrigger>
											<SelectContent>
												<SelectItem value="">none</SelectItem>
												{#each models as model (model.id)}
													<SelectItem value={model.id}>
														{modelLabel(model)}
													</SelectItem>
												{/each}
											</SelectContent>
										</Select>
									</div>
									<div class="space-y-2">
										<Label for="task_thread_metadata_model"
											>thread metadata model</Label
										>
										<p class="text-xs text-zinc-500">
											model used to generate thread titles and tags
											automatically.
										</p>
										<Select
											value={aiTaskThreadMetadataModelId}
											onValueChange={(v: string) =>
												(aiTaskThreadMetadataModelId = v)}
										>
											<SelectTrigger
												id="task_thread_metadata_model"
												class="rounded-xl"
											>
												<span class="truncate text-left"
													>{getModelLabel(
														aiTaskThreadMetadataModelId
													)}</span
												>
											</SelectTrigger>
											<SelectContent>
												<SelectItem value="">none</SelectItem>
												{#each models as model (model.id)}
													<SelectItem value={model.id}>
														{modelLabel(model)}
													</SelectItem>
												{/each}
											</SelectContent>
										</Select>
									</div>
									<div class="space-y-2">
										<Label for="task_input_autocomplete_model">
											input autocomplete model
										</Label>
										<p class="text-xs text-zinc-500">
											model used to suggest completions as the user types.
										</p>
										<Select
											value={aiTaskInputAutocompleteModelId}
											onValueChange={(v: string) =>
												(aiTaskInputAutocompleteModelId = v)}
										>
											<SelectTrigger
												id="task_input_autocomplete_model"
												class="rounded-xl"
											>
												<span class="truncate text-left"
													>{getModelLabel(
														aiTaskInputAutocompleteModelId
													)}</span
												>
											</SelectTrigger>
											<SelectContent>
												<SelectItem value="">none</SelectItem>
												{#each models as model (model.id)}
													<SelectItem value={model.id}>
														{modelLabel(model)}
													</SelectItem>
												{/each}
											</SelectContent>
										</Select>
									</div>
								</div>
								{#if modelsError}
									<p class="mt-3 text-xs text-red-300">{modelsError}</p>
								{/if}
							</div>
						</CardContent>
					</Card>

					<Card class="border-zinc-800 bg-zinc-900">
						<CardHeader>
							<CardTitle>branding</CardTitle>
							<CardDescription>public-facing brand configuration.</CardDescription>
						</CardHeader>
						<CardContent class="space-y-5">
							<div class="grid gap-4 md:grid-cols-2">
								<div class="space-y-2">
									<Label for="site_name">site name</Label>
									<p class="text-xs text-zinc-500">
										display name shown in the browser tab, emails, and UI.
									</p>
									<Input
										id="site_name"
										bind:value={brandingSiteName}
										class="rounded-xl"
									/>
								</div>
								<div class="space-y-2">
									<div class="flex items-center justify-between gap-2">
										<Label for="app_version">app version</Label>
										<span
											class="inline-flex items-center gap-1 rounded-md border border-zinc-800 bg-zinc-900 px-2 py-0.5 text-xs text-zinc-300"
										>
											<Lock class="h-3 w-3" />
											env-only
										</span>
									</div>
									<Input
										id="app_version"
										value={brandingAppVersion}
										disabled
										class="rounded-xl"
									/>
									<p class="text-xs text-zinc-500">
										set via environment variables only.
									</p>
								</div>
							</div>

							<div class="grid gap-4 md:grid-cols-2">
								<div class="space-y-2">
									<Label for="primary_color">primary color</Label>
									<p class="text-xs text-zinc-500">
										accent color used throughout the frontend (CSS hex value).
									</p>
									<Input
										id="primary_color"
										bind:value={brandingPrimaryColor}
										placeholder="#6366f1"
										class="rounded-xl"
									/>
								</div>
								<div class="space-y-2">
									<div class="flex items-center justify-between gap-2">
										<Label for="analytics_key">analytics key</Label>
										<span
											class="inline-flex items-center gap-1 rounded-md border border-zinc-800 bg-zinc-900 px-2 py-0.5 text-xs text-zinc-300"
										>
											<Lock class="h-3 w-3" />
											env-only
										</span>
									</div>
									<Input
										id="analytics_key"
										value={brandingAnalyticsKeyConfigured
											? '(configured)'
											: '(not set)'}
										disabled
										class="rounded-xl"
									/>
									<p class="text-xs text-zinc-500">
										set via environment variables only.
									</p>
								</div>
							</div>

							<div class="grid gap-4 md:grid-cols-2">
								<div class="space-y-2">
									<Label for="logo_url">logo url</Label>
									<p class="text-xs text-zinc-500">
										URL for the app logo used in the sidebar and outgoing
										emails.
									</p>
									<Input
										id="logo_url"
										bind:value={brandingLogoUrl}
										placeholder="https://…"
										class="rounded-xl"
									/>
								</div>
								<div class="space-y-2">
									<Label for="favicon_url">favicon url</Label>
									<p class="text-xs text-zinc-500">
										URL for the browser tab favicon.
									</p>
									<Input
										id="favicon_url"
										bind:value={brandingFaviconUrl}
										placeholder="https://…"
										class="rounded-xl"
									/>
								</div>
							</div>

							<div class="grid gap-4 md:grid-cols-2">
								<div class="space-y-2">
									<Label for="public_frontend_origin"
										>public frontend origin</Label
									>
									<p class="text-xs text-zinc-500">
										base URL of the user-facing frontend; used to build absolute
										links in emails and OIDC.
									</p>
									<Input
										id="public_frontend_origin"
										bind:value={brandingPublicFrontendOrigin}
										placeholder="https://app.nokodo.net"
										class="rounded-xl"
									/>
								</div>
								<div class="space-y-2">
									<Label for="public_cdn_origin">public cdn origin</Label>
									<p class="text-xs text-zinc-500">
										base URL for CDN-hosted static assets.
									</p>
									<Input
										id="public_cdn_origin"
										bind:value={brandingPublicCdnOrigin}
										placeholder="https://cdn.nokodo.net"
										class="rounded-xl"
									/>
								</div>
							</div>

							<div class="space-y-2">
								<Label for="public_console_origin">public console origin</Label>
								<p class="text-xs text-zinc-500">
									base URL of this admin console; used for OIDC redirect URIs and
									internal links.
								</p>
								<Input
									id="public_console_origin"
									bind:value={brandingPublicConsoleOrigin}
									placeholder="https://console.nokodo.net"
									class="rounded-xl"
								/>
							</div>

							<div class="space-y-2">
								<Label for="pwa_manifest_url">pwa manifest url</Label>
								<Input
									id="pwa_manifest_url"
									bind:value={brandingPwaManifestUrl}
									placeholder="https://cdn.example.com/manifest.json"
									class="rounded-xl"
								/>
								<p class="text-xs text-zinc-500">
									external manifest.json for PWA configuration. served directly in
									the frontend HTML.
								</p>
							</div>
						</CardContent>
					</Card>

					<Card class="border-zinc-800 bg-zinc-900">
						<CardHeader>
							<CardTitle>media</CardTitle>
							<CardDescription
								>URL overrides for individual frontend media assets. these take
								precedence over the base URL.</CardDescription
							>
						</CardHeader>
						<CardContent class="space-y-5">
							<div class="space-y-2">
								<Label for="media_base_url">base url</Label>
								<p class="text-xs text-zinc-500">
									fallback base URL for all media assets not explicitly overridden
									below.
								</p>
								<Input
									id="media_base_url"
									bind:value={mediaBaseUrl}
									placeholder="https://cdn.nokodo.net/media"
									class="rounded-xl"
								/>
							</div>
							<div class="grid gap-4 md:grid-cols-2">
								<div class="space-y-2">
									<Label for="media_favicon_url">favicon url</Label>
									<p class="text-xs text-zinc-500">
										overrides the branding favicon for frontend pages.
									</p>
									<Input
										id="media_favicon_url"
										bind:value={mediaFaviconUrl}
										placeholder="https://…"
										class="rounded-xl"
									/>
								</div>
								<div class="space-y-2">
									<Label for="media_apple_touch_icon_url"
										>apple touch icon url</Label
									>
									<p class="text-xs text-zinc-500">
										icon used when adding the app to an iOS home screen.
									</p>
									<Input
										id="media_apple_touch_icon_url"
										bind:value={mediaAppleTouchIconUrl}
										placeholder="https://…"
										class="rounded-xl"
									/>
								</div>
								<div class="space-y-2">
									<Label for="media_sidebar_logo_url">sidebar logo url</Label>
									<p class="text-xs text-zinc-500">
										logo shown in the frontend sidebar.
									</p>
									<Input
										id="media_sidebar_logo_url"
										bind:value={mediaSidebarLogoUrl}
										placeholder="https://…"
										class="rounded-xl"
									/>
								</div>
								<div class="space-y-2">
									<Label for="media_splash_logo_url">splash logo url</Label>
									<p class="text-xs text-zinc-500">
										logo shown on the splash/loading screen.
									</p>
									<Input
										id="media_splash_logo_url"
										bind:value={mediaSplashLogoUrl}
										placeholder="https://…"
										class="rounded-xl"
									/>
								</div>
							</div>
						</CardContent>
					</Card>

					<Card class="border-zinc-800 bg-zinc-900">
						<CardHeader>
							<CardTitle>assets</CardTitle>
							<CardDescription
								>vector database, embeddings, and reranking configuration.</CardDescription
							>
						</CardHeader>
						<CardContent class="space-y-6">
							<div class="grid gap-4 md:grid-cols-2">
								<div class="space-y-2">
									<Label for="assets_embedding_model"
										>default embedding model</Label
									>
									<p class="text-xs text-zinc-500">
										model used to embed text when no per-request override is
										set.
									</p>
									<Select
										type="single"
										value={assetsDefaultEmbeddingModelId}
										onValueChange={(v: string) => {
											assetsDefaultEmbeddingModelId = v ?? ''
										}}
									>
										<SelectTrigger class="rounded-xl">
											{getModelLabel(assetsDefaultEmbeddingModelId)}
										</SelectTrigger>
										<SelectContent>
											<SelectItem value="">none</SelectItem>
											{#each models as m (m.id)}
												<SelectItem value={m.id}>{modelLabel(m)}</SelectItem
												>
											{/each}
										</SelectContent>
									</Select>
								</div>
								<div class="space-y-2">
									<Label for="assets_vector_db_provider"
										>vector database provider</Label
									>
									<p class="text-xs text-zinc-500">
										backend used for storing and querying vector embeddings.
									</p>
									<Select
										type="single"
										value={assetsVectorDatabaseProvider}
										onValueChange={(v: string) => {
											assetsVectorDatabaseProvider = (v ??
												'qdrant') as VectorDatabaseProvider
										}}
									>
										<SelectTrigger class="rounded-xl">
											{assetsVectorDatabaseProvider}
										</SelectTrigger>
										<SelectContent>
											<SelectItem value="qdrant">qdrant</SelectItem>
											<SelectItem value="pinecone">pinecone</SelectItem>
											<SelectItem value="weaviate">weaviate</SelectItem>
											<SelectItem value="milvus">milvus</SelectItem>
											<SelectItem value="pgvector">pgvector</SelectItem>
											<SelectItem value="redis">redis</SelectItem>
											<SelectItem value="opensearch">opensearch</SelectItem>
										</SelectContent>
									</Select>
								</div>
							</div>
							<div class="space-y-2">
								<Label for="assets_vector_db_url">vector database endpoint</Label>
								<p class="text-xs text-zinc-500">
									connection URL or host for the selected vector database.
								</p>
								<Input
									id="assets_vector_db_url"
									bind:value={assetsVectorDatabaseUrl}
									placeholder="http://localhost:6333"
									class="rounded-xl"
								/>
							</div>

							<h4 class="pt-2 text-sm font-medium text-zinc-400">
								vector database API keys
							</h4>
							<div class="grid gap-4 md:grid-cols-2">
								<div class="space-y-2">
									<Label for="assets_qdrant_api_key">qdrant api key</Label>
									<Input
										id="assets_qdrant_api_key"
										bind:value={assetsVectorDatabaseQdrantApiKey}
										type="password"
										class="rounded-xl"
									/>
								</div>
								<div class="space-y-2">
									<Label for="assets_pinecone_api_key">pinecone api key</Label>
									<Input
										id="assets_pinecone_api_key"
										bind:value={assetsVectorDatabasePineconeApiKey}
										type="password"
										class="rounded-xl"
									/>
								</div>
								<div class="space-y-2">
									<Label for="assets_weaviate_api_key">weaviate api key</Label>
									<Input
										id="assets_weaviate_api_key"
										bind:value={assetsVectorDatabaseWeaviateApiKey}
										type="password"
										class="rounded-xl"
									/>
								</div>
								<div class="space-y-2">
									<Label for="assets_milvus_token">milvus token</Label>
									<Input
										id="assets_milvus_token"
										bind:value={assetsVectorDatabaseMilvusToken}
										type="password"
										class="rounded-xl"
									/>
								</div>
								<div class="space-y-2">
									<Label for="assets_redis_password">redis password</Label>
									<Input
										id="assets_redis_password"
										bind:value={assetsVectorDatabaseRedisPassword}
										type="password"
										class="rounded-xl"
									/>
								</div>
								<div class="space-y-2">
									<Label for="assets_opensearch_api_key">opensearch api key</Label
									>
									<Input
										id="assets_opensearch_api_key"
										bind:value={assetsVectorDatabaseOpensearchApiKey}
										type="password"
										class="rounded-xl"
									/>
								</div>
							</div>

							<h4 class="pt-2 text-sm font-medium text-zinc-400">vector settings</h4>
							<div class="grid gap-4 md:grid-cols-2">
								<div class="space-y-2">
									<Label for="assets_collection_template"
										>collection name template</Label
									>
									<Input
										id="assets_collection_template"
										bind:value={assetsVectorCollectionTemplate}
										placeholder="{'{model}'}_bm25"
										class="rounded-xl"
									/>
									<p class="text-xs text-zinc-500">
										template for auto-generated collection names. use {'{model}'}
										as a placeholder.
									</p>
								</div>
								<div class="space-y-2">
									<Label for="assets_prefetch_limit">prefetch limit</Label>
									<p class="text-xs text-zinc-500">
										maximum candidates fetched before score fusion and
										reranking.
									</p>
									<Input
										id="assets_prefetch_limit"
										type="number"
										bind:value={assetsVectorPrefetchLimit}
										placeholder="256"
										class="rounded-xl"
									/>
								</div>
							</div>
							<div class="grid gap-4 md:grid-cols-2">
								<div
									class="flex items-center justify-between gap-2 rounded-xl border border-zinc-800 p-3"
								>
									<Label for="assets_sparse_enabled">sparse vectors (BM25)</Label>
									<Switch
										id="assets_sparse_enabled"
										checked={assetsVectorSparseEnabled}
										onCheckedChange={(v) => {
											assetsVectorSparseEnabled = v
										}}
									/>
								</div>
								<div
									class="flex items-center justify-between gap-2 rounded-xl border border-zinc-800 p-3"
								>
									<Label for="assets_normalize_scores">normalize scores</Label>
									<Switch
										id="assets_normalize_scores"
										checked={assetsVectorNormalizeScores}
										onCheckedChange={(v) => {
											assetsVectorNormalizeScores = v
										}}
									/>
								</div>
							</div>
							<div class="grid gap-4 md:grid-cols-2">
								<div class="space-y-2">
									<Label for="assets_fusion_algorithm">fusion algorithm</Label>
									<p class="text-xs text-zinc-500">
										algorithm used to combine dense and sparse search scores.
									</p>
									<Select
										type="single"
										value={assetsVectorFusionAlgorithm}
										onValueChange={(v: string) => {
											assetsVectorFusionAlgorithm = v ?? 'rrf'
										}}
									>
										<SelectTrigger class="rounded-xl">
											{assetsVectorFusionAlgorithm === 'rrf'
												? 'reciprocal rank fusion (RRF)'
												: 'distribution-based score fusion (DBSF)'}
										</SelectTrigger>
										<SelectContent>
											<SelectItem value="rrf"
												>reciprocal rank fusion (RRF)</SelectItem
											>
											<SelectItem value="dbsf"
												>distribution-based score fusion (DBSF)</SelectItem
											>
										</SelectContent>
									</Select>
								</div>
							</div>

							<h4 class="pt-2 text-sm font-medium text-zinc-400">embeddings</h4>
							<div class="grid gap-4 md:grid-cols-2">
								<div class="space-y-2">
									<Label for="assets_vector_size">vector size (dimensions)</Label>
									<p class="text-xs text-zinc-500">
										dimensions of the embedding vectors; must match the chosen
										model.
									</p>
									<Input
										id="assets_vector_size"
										type="number"
										bind:value={assetsEmbeddingsVectorSize}
										placeholder="1536"
										class="rounded-xl"
									/>
								</div>
								<div class="space-y-2">
									<Label for="assets_batch_size">batch size</Label>
									<p class="text-xs text-zinc-500">
										texts embedded per API call during bulk vectorization.
									</p>
									<Input
										id="assets_batch_size"
										type="number"
										bind:value={assetsEmbeddingsBatchSize}
										placeholder="64"
										class="rounded-xl"
									/>
								</div>
							</div>

							<h4 class="pt-2 text-sm font-medium text-zinc-400">reranking</h4>
							<div class="grid gap-4 md:grid-cols-2">
								<div class="space-y-2">
									<Label for="assets_rerank_strategy">default strategy</Label>
									<p class="text-xs text-zinc-500">
										controls when and how results are reranked after retrieval.
									</p>
									<Select
										type="single"
										value={assetsRerankDefaultStrategy}
										onValueChange={(v: string) => {
											assetsRerankDefaultStrategy = v ?? 'native'
										}}
									>
										<SelectTrigger class="rounded-xl">
											{assetsRerankDefaultStrategy}
										</SelectTrigger>
										<SelectContent>
											<SelectItem value="none">none</SelectItem>
											<SelectItem value="native">native</SelectItem>
											<SelectItem value="external">external</SelectItem>
										</SelectContent>
									</Select>
								</div>
								<div class="space-y-2">
									<Label for="assets_rerank_top_k">rerank top-k</Label>
									<p class="text-xs text-zinc-500">
										final results kept after reranking.
									</p>
									<Input
										id="assets_rerank_top_k"
										type="number"
										bind:value={assetsRerankTopK}
										placeholder="10"
										class="rounded-xl"
									/>
								</div>
							</div>
						</CardContent>
					</Card>

					<Card class="border-zinc-800 bg-zinc-900">
						<CardHeader>
							<CardTitle>limits</CardTitle>
							<CardDescription>protect the system with sane caps.</CardDescription>
						</CardHeader>
						<CardContent class="grid gap-4 md:grid-cols-2">
							<div class="space-y-2">
								<Label for="max_threads">max threads per user</Label>
								<p class="text-xs text-zinc-500">
									hard cap on threads per account; prevents runaway data growth.
								</p>
								<Input
									id="max_threads"
									type="number"
									bind:value={limitsMaxThreadsPerUser}
									class="rounded-xl"
								/>
							</div>
							<div class="space-y-2">
								<Label for="max_messages">max messages per thread</Label>
								<p class="text-xs text-zinc-500">
									hard cap on messages per thread.
								</p>
								<Input
									id="max_messages"
									type="number"
									bind:value={limitsMaxMessagesPerThread}
									class="rounded-xl"
								/>
							</div>
							<div class="space-y-2">
								<Label for="max_file_size">max file size (MB)</Label>
								<p class="text-xs text-zinc-500">
									maximum allowed size for a single file upload.
								</p>
								<Input
									id="max_file_size"
									type="number"
									bind:value={limitsMaxFileSizeMb}
									class="rounded-xl"
								/>
							</div>
							<div class="space-y-2">
								<Label for="rate_limit">rate limit (requests/min)</Label>
								<p class="text-xs text-zinc-500">
									API requests allowed per minute per authenticated user.
								</p>
								<Input
									id="rate_limit"
									type="number"
									bind:value={limitsRateLimitRequestsPerMinute}
									class="rounded-xl"
								/>
							</div>
						</CardContent>
					</Card>

					<Card class="border-zinc-800 bg-zinc-900">
						<CardHeader>
							<CardTitle>soft delete</CardTitle>
							<CardDescription
								>when enabled, deleting a resource marks it as deleted rather than
								permanently removing it from the database.</CardDescription
							>
						</CardHeader>
						<CardContent class="space-y-3">
							<div class="flex items-center justify-between">
								<div class="space-y-0.5">
									<Label for="soft_delete_threads">threads</Label>
									<p class="text-xs text-zinc-500">
										soft-delete threads instead of permanently removing them.
									</p>
								</div>
								<Switch
									id="soft_delete_threads"
									checked={softDeleteThreads}
									onCheckedChange={(v: boolean) => (softDeleteThreads = v)}
								/>
							</div>
							<div class="flex items-center justify-between">
								<div class="space-y-0.5">
									<Label for="soft_delete_notes">notes</Label>
									<p class="text-xs text-zinc-500">
										soft-delete notes instead of permanently removing them.
									</p>
								</div>
								<Switch
									id="soft_delete_notes"
									checked={softDeleteNotes}
									onCheckedChange={(v: boolean) => (softDeleteNotes = v)}
								/>
							</div>
							<div class="flex items-center justify-between">
								<div class="space-y-0.5">
									<Label for="soft_delete_files">files</Label>
									<p class="text-xs text-zinc-500">
										soft-delete files instead of permanently removing them.
									</p>
								</div>
								<Switch
									id="soft_delete_files"
									checked={softDeleteFiles}
									onCheckedChange={(v: boolean) => (softDeleteFiles = v)}
								/>
							</div>
						</CardContent>
					</Card>

					<Card class="border-zinc-800 bg-zinc-900">
						<CardHeader>
							<CardTitle>security</CardTitle>
							<CardDescription>authentication and session behavior.</CardDescription>
						</CardHeader>
						<CardContent class="space-y-5">
							<div class="grid gap-4 md:grid-cols-2">
								<div class="space-y-2">
									<div class="flex items-center justify-between gap-2">
										<Label for="secret_key">secret key</Label>
										<span
											class="inline-flex items-center gap-1 rounded-md border border-zinc-800 bg-zinc-900 px-2 py-0.5 text-xs text-zinc-300"
										>
											<Lock class="h-3 w-3" />
											env-only
										</span>
									</div>
									<Input
										id="secret_key"
										value={securitySecretKeyConfigured
											? '(configured)'
											: '(not set)'}
										disabled
										class="rounded-xl"
									/>
									<p class="text-xs text-zinc-500">
										set via environment variables only.
									</p>
								</div>
								<div class="space-y-2">
									<div class="flex items-center justify-between gap-2">
										<Label for="jwt_algorithm">jwt algorithm</Label>
										<span
											class="inline-flex items-center gap-1 rounded-md border border-zinc-800 bg-zinc-900 px-2 py-0.5 text-xs text-zinc-300"
										>
											<Lock class="h-3 w-3" />
											env-only
										</span>
									</div>
									<Input
										id="jwt_algorithm"
										value={securityJwtAlgorithm || '(not set)'}
										disabled
										class="rounded-xl"
									/>
									<p class="text-xs text-zinc-500">
										set via environment variables only.
									</p>
								</div>
							</div>

							<div class="grid gap-4 md:grid-cols-2">
								<div class="space-y-2">
									<div class="flex items-center justify-between gap-2">
										<Label for="enable_oauth">enable oauth</Label>
										<span
											class="inline-flex items-center gap-1 rounded-md border border-zinc-800 bg-zinc-900 px-2 py-0.5 text-xs text-zinc-300"
										>
											<Lock class="h-3 w-3" />
											env-only
										</span>
									</div>
									<Input
										id="enable_oauth"
										value={securityEnableOauth ? 'true' : 'false'}
										disabled
										class="rounded-xl"
									/>
									<p class="text-xs text-zinc-500">
										set via environment variables only.
									</p>
								</div>
								<div class="space-y-2">
									<div class="flex items-center justify-between gap-2">
										<Label for="cors_origins">cors origins</Label>
										<span
											class="inline-flex items-center gap-1 rounded-md border border-zinc-800 bg-zinc-900 px-2 py-0.5 text-xs text-zinc-300"
										>
											<Lock class="h-3 w-3" />
											env-only
										</span>
									</div>
									<Input
										id="cors_origins"
										value={securityCorsOrigins || '(not set)'}
										disabled
										class="rounded-xl"
									/>
									<p class="text-xs text-zinc-500">
										set via environment variables only.
									</p>
								</div>
							</div>

							<div class="grid gap-4 md:grid-cols-2">
								<div class="space-y-2">
									<Label for="access_expire">access token expire minutes</Label>
									<p class="text-xs text-zinc-500">
										how long access tokens remain valid before the client must
										refresh.
									</p>
									<Input
										id="access_expire"
										type="number"
										bind:value={securityAccessTokenExpireMinutes}
										class="rounded-xl"
									/>
								</div>
								<div class="space-y-2">
									<Label for="refresh_expire">refresh token expire days</Label>
									<p class="text-xs text-zinc-500">
										how long refresh tokens remain valid; controls maximum
										session length.
									</p>
									<Input
										id="refresh_expire"
										type="number"
										bind:value={securityRefreshTokenExpireDays}
										class="rounded-xl"
									/>
								</div>
							</div>

							<div class="grid gap-4 md:grid-cols-2">
								<div class="space-y-2">
									<Label for="session_timeout">session timeout minutes</Label>
									<p class="text-xs text-zinc-500">
										idle timeout after which the user is automatically logged
										out.
									</p>
									<Input
										id="session_timeout"
										type="number"
										bind:value={securitySessionTimeoutMinutes}
										class="rounded-xl"
									/>
								</div>
								<div class="space-y-2">
									<Label for="allowed_domains">allowed email domains</Label>
									<Input
										id="allowed_domains"
										bind:value={securityAllowedEmailDomains}
										placeholder="example.com, example.org"
										class="rounded-xl"
									/>
									<p class="text-xs text-zinc-500">
										only emails from these domains can register. leave empty to
										allow all.
									</p>
								</div>
							</div>

							<div class="flex items-center justify-between">
								<div class="space-y-0.5">
									<Label for="allow_signups">allow new user signups</Label>
									<p class="text-xs text-zinc-500">
										when off, admins or users with users:manage only.
									</p>
								</div>
								<Switch
									id="allow_signups"
									checked={securityAllowSignups}
									onCheckedChange={(v: boolean) => (securityAllowSignups = v)}
								/>
							</div>

							<div class="space-y-2">
								<Label>auto-apply roles</Label>
								<RolePicker bind:value={securityAutoSignupRoleIds} />
								<p class="text-xs text-zinc-500">
									roles automatically assigned to new users on signup.
								</p>
							</div>

							<div class="flex items-center justify-between">
								<div class="space-y-0.5">
									<Label for="cookie_secure">auth cookie secure</Label>
									<p class="text-xs text-zinc-500">
										recommended true in production.
									</p>
								</div>
								<Switch
									id="cookie_secure"
									checked={securityAuthCookieSecure}
									onCheckedChange={(v: boolean) => (securityAuthCookieSecure = v)}
								/>
							</div>

							<div class="flex items-center justify-between">
								<div class="space-y-0.5">
									<Label for="email_verification"
										>require email verification</Label
									>
									<p class="text-xs text-zinc-500">
										require users to verify their email address before accessing
										the app.
									</p>
								</div>
								<Switch
									id="email_verification"
									checked={securityRequireEmailVerification}
									onCheckedChange={(v: boolean) =>
										(securityRequireEmailVerification = v)}
								/>
							</div>

							<div class="rounded-xl border border-zinc-800 bg-zinc-950 p-4">
								<p class="mb-1 text-sm font-medium">oidc</p>
								<p class="mb-4 text-xs text-zinc-500">
									openid connect provider settings for single sign-on.
								</p>

								<div class="mb-4 flex items-center justify-between">
									<div class="space-y-0.5">
										<Label for="oidc_enabled">enable oidc</Label>
										<p class="text-xs text-zinc-500">
											allow users to sign in with an oidc provider.
										</p>
									</div>
									<Switch
										id="oidc_enabled"
										checked={securityOidcEnabled}
										onCheckedChange={(v: boolean) => (securityOidcEnabled = v)}
									/>
								</div>

								<div class="grid gap-4 md:grid-cols-2">
									<div class="space-y-2">
										<Label for="oidc_issuer">issuer url</Label>
										<Input
											id="oidc_issuer"
											bind:value={securityOidcIssuerUrl}
											placeholder="https://issuer.example.com"
											class="rounded-xl"
										/>
									</div>
									<div class="space-y-2">
										<Label for="oidc_client_id">client id</Label>
										<Input
											id="oidc_client_id"
											bind:value={securityOidcClientId}
											class="rounded-xl"
										/>
									</div>
									<div class="space-y-2">
										<Label for="oidc_client_secret">client secret</Label>
										<Input
											id="oidc_client_secret"
											type="password"
											bind:value={securityOidcClientSecret}
											class="rounded-xl"
										/>
									</div>
									<div class="space-y-2">
										<Label for="oidc_redirect">redirect uri</Label>
										<Input
											id="oidc_redirect"
											bind:value={securityOidcRedirectUri}
											placeholder="https://app.example.com/oidc/callback"
											class="rounded-xl"
										/>
									</div>
									<div class="space-y-2 md:col-span-2">
										<Label for="oidc_scopes">scopes</Label>
										<Input
											id="oidc_scopes"
											bind:value={securityOidcScopes}
											placeholder="openid, profile, email"
											class="rounded-xl"
										/>
										<p class="text-xs text-zinc-500">comma-separated list.</p>
									</div>
								</div>

								<div class="mt-4 flex items-center justify-between">
									<div class="space-y-0.5">
										<Label for="oidc_only">oidc only</Label>
										<p class="text-xs text-zinc-500">
											disable password login. requires oidc to be enabled
											&amp; configured.
										</p>
									</div>
									<Switch
										id="oidc_only"
										checked={securityOidcOnly}
										onCheckedChange={(v: boolean) => (securityOidcOnly = v)}
									/>
								</div>
							</div>
						</CardContent>
					</Card>

					<Card class="border-zinc-800 bg-zinc-900">
						<CardHeader>
							<CardTitle>default permissions</CardTitle>
							<CardDescription>
								global defaults applied when no role or explicit rule grants access.
							</CardDescription>
						</CardHeader>
						<CardContent>
							<DefaultPermissionsEditor
								bind:value={defaultPermissions}
								allowInherit={false}
							/>
						</CardContent>
					</Card>
				</div>
			{:else}
				<div class="rounded-lg border border-zinc-800 p-8 text-zinc-400">
					no settings loaded.
				</div>
			{/if}
		</div>
	</div>
</div>
