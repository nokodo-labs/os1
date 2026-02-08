<script lang="ts">
	import {
		api,
		unwrap,
		type Agent,
		type DefaultPermissionsSettings,
		type DefaultPermissionsSettingsPatch,
		type SettingsResponse,
		type SettingsUpdateRequest,
	} from '$lib/api'
	import DefaultPermissionsEditor from '$lib/components/DefaultPermissionsEditor.svelte'
	import NokodoLoader from '$lib/components/NokodoLoader.svelte'
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
	import { Lock } from '@lucide/svelte'
	import { onMount } from 'svelte'

	type ThemeMode = 'light' | 'dark' | 'system'

	function themeLabel(v: ThemeMode): string {
		if (v === 'light') return 'light'
		if (v === 'dark') return 'dark'
		return 'system'
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

	// Read-only (env-only/write-locked) display values
	let brandingAppVersion = $state<string>('')
	let brandingAnalyticsKeyConfigured = $state<boolean>(false)
	let securitySecretKeyConfigured = $state<boolean>(false)
	let securityJwtAlgorithm = $state<string>('')
	let securityEnableOauth = $state<boolean>(false)
	let securityCorsOrigins = $state<string>('')

	// Editable form state (only fields supported by Settings*Patch models)
	let uiDefaultTheme = $state<ThemeMode>('system')
	let uiSidebarCollapsed = $state(false)

	type ChatContextMode = 'recent' | 'relevant' | 'pinned'

	let aiDefaultAgentId = $state<string>('')

	let aiMemoryEnable = $state(false)
	let aiMemorySimilarityThreshold = $state<string>('')
	let aiMemoryTopK = $state<string>('')
	let aiMemoryMessagesToConsider = $state<string>('')

	let aiChatContextMode = $state<ChatContextMode>('recent')
	let aiChatContextTopK = $state<string>('')

	let brandingSiteName = $state('')
	let brandingLogoUrl = $state('')
	let brandingFaviconUrl = $state('')
	let brandingPrimaryColor = $state('')
	let brandingPublicFrontendOrigin = $state('')
	let brandingPublicCdnOrigin = $state('')

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

	let defaultPermissions = $state<DefaultPermissionsSettings>({
		resource_access: {
			thread: null,
			project: null,
			file: null,
			note: null,
			group: null,
		},
		action_permissions: [],
	})

	// Original snapshots for change detection
	let original = $state({
		uiDefaultTheme: 'system' as ThemeMode,
		uiSidebarCollapsed: false,
		aiDefaultAgentId: '',
		aiMemoryEnable: false,
		aiMemorySimilarityThreshold: '',
		aiMemoryTopK: '',
		aiMemoryMessagesToConsider: '',
		aiChatContextMode: 'recent' as ChatContextMode,
		aiChatContextTopK: '',
		brandingSiteName: '',
		brandingLogoUrl: '',
		brandingFaviconUrl: '',
		brandingPrimaryColor: '',
		brandingPublicFrontendOrigin: '',
		brandingPublicCdnOrigin: '',
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
			uiSidebarCollapsed !== original.uiSidebarCollapsed ||
			aiDefaultAgentId !== original.aiDefaultAgentId ||
			aiMemoryEnable !== original.aiMemoryEnable ||
			aiMemorySimilarityThreshold !== original.aiMemorySimilarityThreshold ||
			aiMemoryTopK !== original.aiMemoryTopK ||
			aiMemoryMessagesToConsider !== original.aiMemoryMessagesToConsider ||
			aiChatContextMode !== original.aiChatContextMode ||
			aiChatContextTopK !== original.aiChatContextTopK ||
			brandingSiteName !== original.brandingSiteName ||
			brandingLogoUrl !== original.brandingLogoUrl ||
			brandingFaviconUrl !== original.brandingFaviconUrl ||
			brandingPrimaryColor !== original.brandingPrimaryColor ||
			brandingPublicFrontendOrigin !== original.brandingPublicFrontendOrigin ||
			brandingPublicCdnOrigin !== original.brandingPublicCdnOrigin ||
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
			defaultPermissionsKey(defaultPermissions) !== original.defaultPermissionsKey
	)

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

	const selectedAgentLabel = $derived(() => {
		if (!aiDefaultAgentId) return 'none'
		const a = agents.find((x) => x.id === aiDefaultAgentId)
		return a ? agentLabel(a) : aiDefaultAgentId
	})

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
		uiSidebarCollapsed = ui?.sidebar_collapsed ?? false

		const ai = r.data.ai
		aiDefaultAgentId = ai?.default_agent_id ?? ''

		const memory = ai?.memory
		aiMemoryEnable = memory?.enable_memory ?? false
		aiMemorySimilarityThreshold = toStringOrEmpty(memory?.similarity_threshold)
		aiMemoryTopK = toStringOrEmpty(memory?.top_k)
		aiMemoryMessagesToConsider = toStringOrEmpty(memory?.messages_to_consider)

		const chatContext = ai?.chat_context
		aiChatContextMode = (chatContext?.mode ?? 'recent') as ChatContextMode
		aiChatContextTopK = toStringOrEmpty(chatContext?.top_k)

		const branding = r.data.branding
		brandingSiteName = branding?.site_name ?? ''
		brandingLogoUrl = toStringOrEmpty(branding?.logo_url)
		brandingFaviconUrl = toStringOrEmpty(branding?.favicon_url)
		brandingPrimaryColor = branding?.primary_color ?? ''
		brandingPublicFrontendOrigin = toStringOrEmpty(branding?.public_frontend_origin)
		brandingPublicCdnOrigin = toStringOrEmpty(branding?.public_cdn_origin)

		brandingAppVersion = branding?.app_version ?? ''
		brandingAnalyticsKeyConfigured = Boolean(branding?.analytics_key)

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

		securitySecretKeyConfigured = Boolean(security?.secret_key)
		securityJwtAlgorithm = security?.jwt_algorithm ?? ''
		securityEnableOauth = toBool(security?.enable_oauth)
		securityCorsOrigins = (security?.cors_origins ?? []).join(', ')

		const defaults = r.data.default_permissions
		defaultPermissions = normalizeDefaultPermissions(
			defaults ?? { resource_access: {}, action_permissions: [] }
		)

		original = {
			uiDefaultTheme,
			uiSidebarCollapsed,
			aiDefaultAgentId,
			aiMemoryEnable,
			aiMemorySimilarityThreshold,
			aiMemoryTopK,
			aiMemoryMessagesToConsider,
			aiChatContextMode,
			aiChatContextTopK,
			brandingSiteName,
			brandingLogoUrl,
			brandingFaviconUrl,
			brandingPrimaryColor,
			brandingPublicFrontendOrigin,
			brandingPublicCdnOrigin,
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

	function resetDraft() {
		uiDefaultTheme = original.uiDefaultTheme
		uiSidebarCollapsed = original.uiSidebarCollapsed
		aiDefaultAgentId = original.aiDefaultAgentId
		aiMemoryEnable = original.aiMemoryEnable
		aiMemorySimilarityThreshold = original.aiMemorySimilarityThreshold
		aiMemoryTopK = original.aiMemoryTopK
		aiMemoryMessagesToConsider = original.aiMemoryMessagesToConsider
		aiChatContextMode = original.aiChatContextMode
		aiChatContextTopK = original.aiChatContextTopK
		brandingSiteName = original.brandingSiteName
		brandingLogoUrl = original.brandingLogoUrl
		brandingFaviconUrl = original.brandingFaviconUrl
		brandingPrimaryColor = original.brandingPrimaryColor
		brandingPublicFrontendOrigin = original.brandingPublicFrontendOrigin
		brandingPublicCdnOrigin = original.brandingPublicCdnOrigin
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
			},
			action_permissions: defaultPermissions.action_permissions ?? [],
		}
	}

	function buildUpdateRequest(): SettingsUpdateRequest {
		const data: NonNullable<SettingsUpdateRequest['data']> = {}

		if (
			uiDefaultTheme !== original.uiDefaultTheme ||
			uiSidebarCollapsed !== original.uiSidebarCollapsed
		) {
			data.ui = {}
			if (uiDefaultTheme !== original.uiDefaultTheme) data.ui.default_theme = uiDefaultTheme
			if (uiSidebarCollapsed !== original.uiSidebarCollapsed)
				data.ui.sidebar_collapsed = uiSidebarCollapsed
		}

		if (
			aiDefaultAgentId !== original.aiDefaultAgentId ||
			aiMemoryEnable !== original.aiMemoryEnable ||
			aiMemorySimilarityThreshold !== original.aiMemorySimilarityThreshold ||
			aiMemoryTopK !== original.aiMemoryTopK ||
			aiMemoryMessagesToConsider !== original.aiMemoryMessagesToConsider ||
			aiChatContextMode !== original.aiChatContextMode ||
			aiChatContextTopK !== original.aiChatContextTopK
		) {
			data.ai = {}
			if (aiDefaultAgentId !== original.aiDefaultAgentId)
				data.ai.default_agent_id = aiDefaultAgentId ? aiDefaultAgentId : null

			if (
				aiMemoryEnable !== original.aiMemoryEnable ||
				aiMemorySimilarityThreshold !== original.aiMemorySimilarityThreshold ||
				aiMemoryTopK !== original.aiMemoryTopK ||
				aiMemoryMessagesToConsider !== original.aiMemoryMessagesToConsider
			) {
				data.ai.memory = {}
				if (aiMemoryEnable !== original.aiMemoryEnable)
					data.ai.memory.enable_memory = aiMemoryEnable
				if (aiMemorySimilarityThreshold !== original.aiMemorySimilarityThreshold)
					data.ai.memory.similarity_threshold = asNumberOrNull(
						aiMemorySimilarityThreshold
					)
				if (aiMemoryTopK !== original.aiMemoryTopK)
					data.ai.memory.top_k = asNumberOrNull(aiMemoryTopK)
				if (aiMemoryMessagesToConsider !== original.aiMemoryMessagesToConsider)
					data.ai.memory.messages_to_consider = asNumberOrNull(aiMemoryMessagesToConsider)
			}

			if (
				aiChatContextMode !== original.aiChatContextMode ||
				aiChatContextTopK !== original.aiChatContextTopK
			) {
				data.ai.chat_context = {}
				if (aiChatContextMode !== original.aiChatContextMode)
					data.ai.chat_context.mode = aiChatContextMode
				if (aiChatContextTopK !== original.aiChatContextTopK)
					data.ai.chat_context.top_k = asNumberOrNull(aiChatContextTopK)
			}
		}

		if (
			brandingSiteName !== original.brandingSiteName ||
			brandingLogoUrl !== original.brandingLogoUrl ||
			brandingFaviconUrl !== original.brandingFaviconUrl ||
			brandingPrimaryColor !== original.brandingPrimaryColor ||
			brandingPublicFrontendOrigin !== original.brandingPublicFrontendOrigin ||
			brandingPublicCdnOrigin !== original.brandingPublicCdnOrigin
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
			securityAllowedEmailDomains !== original.securityAllowedEmailDomains
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
		Promise.all([fetchSettings(), fetchAgents()])
	})
</script>

<div class="space-y-6">
	<div class="flex flex-wrap items-start justify-between gap-3">
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

	{#if error}
		<div class="rounded-lg border border-red-900/40 bg-red-950/40 p-4 text-sm text-red-200">
			{error}
		</div>
	{/if}
	{#if saveError}
		<div class="rounded-lg border border-red-900/40 bg-red-950/40 p-4 text-sm text-red-200">
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
		<div class="flex items-center justify-center py-16">
			<NokodoLoader className="opacity-70" />
		</div>
	{:else if response}
		<div class="space-y-6">
			<Card class="border-zinc-800 bg-zinc-950">
				<CardHeader>
					<CardTitle>ui</CardTitle>
					<CardDescription>console UX defaults.</CardDescription>
				</CardHeader>
				<CardContent class="space-y-5">
					<div class="space-y-2">
						<Label for="default_theme">default theme</Label>
						<Select
							value={uiDefaultTheme}
							onValueChange={(v: string) => (uiDefaultTheme = v as ThemeMode)}
						>
							<SelectTrigger id="default_theme" class="rounded-xl">
								<span class="truncate text-left">{themeLabel(uiDefaultTheme)}</span>
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
							<p class="text-xs text-zinc-500">collapse sidebar by default.</p>
						</div>
						<Switch
							id="sidebar_collapsed"
							checked={uiSidebarCollapsed}
							onCheckedChange={(v: boolean) => (uiSidebarCollapsed = v)}
						/>
					</div>
				</CardContent>
			</Card>

			<Card class="border-zinc-800 bg-zinc-950">
				<CardHeader>
					<CardTitle>ai</CardTitle>
					<CardDescription>agent defaults and behavior.</CardDescription>
				</CardHeader>
				<CardContent class="space-y-6">
					<div class="space-y-2">
						<div class="flex items-center justify-between gap-2">
							<Label for="default_agent">default agent</Label>
							{#if isFetchingAgents}
								<span class="text-xs text-zinc-500">loading…</span>
							{/if}
						</div>
						<Select
							value={aiDefaultAgentId}
							onValueChange={(v: string) => (aiDefaultAgentId = v)}
						>
							<SelectTrigger id="default_agent" class="rounded-xl">
								<span class="truncate text-left">{selectedAgentLabel()}</span>
							</SelectTrigger>
							<SelectContent>
								<SelectItem value="">none</SelectItem>
								{#each agents as a (a.id)}
									<SelectItem value={a.id}>{agentLabel(a)}</SelectItem>
								{/each}
							</SelectContent>
						</Select>
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
								<Select
									value={aiChatContextMode}
									onValueChange={(v: string) =>
										(aiChatContextMode = v as ChatContextMode)}
								>
									<SelectTrigger id="ai_chat_mode" class="rounded-xl">
										<span class="truncate text-left">{aiChatContextMode}</span>
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
				</CardContent>
			</Card>

			<Card class="border-zinc-800 bg-zinc-950">
				<CardHeader>
					<CardTitle>branding</CardTitle>
					<CardDescription>public-facing brand configuration.</CardDescription>
				</CardHeader>
				<CardContent class="space-y-5">
					<div class="grid gap-4 md:grid-cols-2">
						<div class="space-y-2">
							<Label for="site_name">site name</Label>
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
							<p class="text-xs text-zinc-500">set via environment variables only.</p>
						</div>
					</div>

					<div class="grid gap-4 md:grid-cols-2">
						<div class="space-y-2">
							<Label for="primary_color">primary color</Label>
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
							<p class="text-xs text-zinc-500">set via environment variables only.</p>
						</div>
					</div>

					<div class="grid gap-4 md:grid-cols-2">
						<div class="space-y-2">
							<Label for="logo_url">logo url</Label>
							<Input
								id="logo_url"
								bind:value={brandingLogoUrl}
								placeholder="https://…"
								class="rounded-xl"
							/>
						</div>
						<div class="space-y-2">
							<Label for="favicon_url">favicon url</Label>
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
							<Label for="public_frontend_origin">public frontend origin</Label>
							<Input
								id="public_frontend_origin"
								bind:value={brandingPublicFrontendOrigin}
								placeholder="https://app.nokodo.net"
								class="rounded-xl"
							/>
						</div>
						<div class="space-y-2">
							<Label for="public_cdn_origin">public cdn origin</Label>
							<Input
								id="public_cdn_origin"
								bind:value={brandingPublicCdnOrigin}
								placeholder="https://cdn.nokodo.net"
								class="rounded-xl"
							/>
						</div>
					</div>
				</CardContent>
			</Card>

			<Card class="border-zinc-800 bg-zinc-950">
				<CardHeader>
					<CardTitle>limits</CardTitle>
					<CardDescription>protect the system with sane caps.</CardDescription>
				</CardHeader>
				<CardContent class="grid gap-4 md:grid-cols-2">
					<div class="space-y-2">
						<Label for="max_threads">max threads per user</Label>
						<Input
							id="max_threads"
							type="number"
							bind:value={limitsMaxThreadsPerUser}
							class="rounded-xl"
						/>
					</div>
					<div class="space-y-2">
						<Label for="max_messages">max messages per thread</Label>
						<Input
							id="max_messages"
							type="number"
							bind:value={limitsMaxMessagesPerThread}
							class="rounded-xl"
						/>
					</div>
					<div class="space-y-2">
						<Label for="max_file_size">max file size (MB)</Label>
						<Input
							id="max_file_size"
							type="number"
							bind:value={limitsMaxFileSizeMb}
							class="rounded-xl"
						/>
					</div>
					<div class="space-y-2">
						<Label for="rate_limit">rate limit (requests/min)</Label>
						<Input
							id="rate_limit"
							type="number"
							bind:value={limitsRateLimitRequestsPerMinute}
							class="rounded-xl"
						/>
					</div>
				</CardContent>
			</Card>

			<Card class="border-zinc-800 bg-zinc-950">
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
								value={securitySecretKeyConfigured ? '(configured)' : '(not set)'}
								disabled
								class="rounded-xl"
							/>
							<p class="text-xs text-zinc-500">set via environment variables only.</p>
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
							<p class="text-xs text-zinc-500">set via environment variables only.</p>
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
							<p class="text-xs text-zinc-500">set via environment variables only.</p>
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
							<p class="text-xs text-zinc-500">set via environment variables only.</p>
						</div>
					</div>

					<div class="grid gap-4 md:grid-cols-2">
						<div class="space-y-2">
							<Label for="access_expire">access token expire minutes</Label>
							<Input
								id="access_expire"
								type="number"
								bind:value={securityAccessTokenExpireMinutes}
								class="rounded-xl"
							/>
						</div>
						<div class="space-y-2">
							<Label for="refresh_expire">refresh token expire days</Label>
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
							<p class="text-xs text-zinc-500">comma-separated list.</p>
						</div>
					</div>

					<div class="flex items-center justify-between">
						<div class="space-y-0.5">
							<Label for="cookie_secure">auth cookie secure</Label>
							<p class="text-xs text-zinc-500">recommended true in production.</p>
						</div>
						<Switch
							id="cookie_secure"
							checked={securityAuthCookieSecure}
							onCheckedChange={(v: boolean) => (securityAuthCookieSecure = v)}
						/>
					</div>

					<div class="flex items-center justify-between">
						<div class="space-y-0.5">
							<Label for="email_verification">require email verification</Label>
						</div>
						<Switch
							id="email_verification"
							checked={securityRequireEmailVerification}
							onCheckedChange={(v: boolean) => (securityRequireEmailVerification = v)}
						/>
					</div>
				</CardContent>
			</Card>

			<Card class="border-zinc-800 bg-zinc-950">
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
		<div class="rounded-lg border border-zinc-800 p-8 text-zinc-400">no settings loaded.</div>
	{/if}
</div>
