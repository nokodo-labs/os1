<script lang="ts">
	import { api } from '$lib/api'
	import SettingsSecurity from '$lib/components/settings/SettingsSecurity.svelte'
	import { Button } from '$lib/components/ui/button'
	import { getSettingsContext } from '$lib/settings/context.svelte'
	import { arrayEquals, parseCommaList, toBool, toStringOrEmpty } from '$lib/settings/utils'
	import { asNumberOrUndefined } from '$lib/utils/settingsNumbers'
	import { RefreshCw, RotateCcw, Save } from '@lucide/svelte'
	import { untrack } from 'svelte'

	const ctx = getSettingsContext()

	let accessTokenExpireMinutes = $state('')
	let refreshTokenExpireDays = $state('')
	let authCookieSecure = $state(false)
	let sessionTimeoutMinutes = $state('')
	let requireEmailVerification = $state(false)
	let allowedEmailDomains = $state('')
	let allowSignups = $state(true)
	let autoSignupRoleIds = $state<string[]>([])
	let oidcEnabled = $state(false)
	let oidcIssuerUrl = $state('')
	let oidcClientId = $state('')
	let oidcClientSecret = $state('')
	let oidcRedirectUri = $state('')
	let oidcScopes = $state('')
	let oidcOnly = $state(false)
	// read-only
	let secretKeyConfigured = $state(false)
	let secretKeyUsesDefault = $state(false)
	let jwtAlgorithm = $state('')
	let enableOauth = $state(false)
	let corsOrigins = $state('')

	type Original = {
		accessTokenExpireMinutes: string
		refreshTokenExpireDays: string
		authCookieSecure: boolean
		sessionTimeoutMinutes: string
		requireEmailVerification: boolean
		allowedEmailDomains: string
		allowSignups: boolean
		autoSignupRoleIds: string[]
		oidcEnabled: boolean
		oidcIssuerUrl: string
		oidcClientId: string
		oidcClientSecret: string
		oidcRedirectUri: string
		oidcScopes: string
		oidcOnly: boolean
	}
	let original = $state<Original | null>(null)

	$effect(() => {
		const r = ctx.response
		if (!r) return
		const sec = r.data.security
		accessTokenExpireMinutes = toStringOrEmpty(sec?.access_token_expire_minutes)
		refreshTokenExpireDays = toStringOrEmpty(sec?.refresh_token_expire_days)
		authCookieSecure = sec?.auth_cookie_secure ?? false
		sessionTimeoutMinutes = toStringOrEmpty(sec?.session_timeout_minutes)
		requireEmailVerification = sec?.require_email_verification ?? false
		allowedEmailDomains = (sec?.allowed_email_domains ?? []).join(', ')
		allowSignups = sec?.allow_signups ?? true
		autoSignupRoleIds = [...(sec?.auto_signup_role_ids ?? [])]
		const oidc = sec?.oidc
		oidcEnabled = oidc?.enabled ?? false
		oidcIssuerUrl = toStringOrEmpty(oidc?.issuer_url)
		oidcClientId = toStringOrEmpty(oidc?.client_id)
		oidcClientSecret = toStringOrEmpty(oidc?.client_secret)
		oidcRedirectUri = toStringOrEmpty(oidc?.redirect_uri)
		oidcScopes = (oidc?.scopes ?? []).join(', ')
		oidcOnly = oidc?.only ?? false
		secretKeyConfigured = Boolean(sec?.secret_key)
		secretKeyUsesDefault = sec?.secret_key_uses_default ?? false
		jwtAlgorithm = sec?.jwt_algorithm ?? ''
		enableOauth = toBool(sec?.enable_oauth)
		corsOrigins = (sec?.cors_origins ?? []).join(', ')

		untrack(() => {
			original = {
				accessTokenExpireMinutes,
				refreshTokenExpireDays,
				authCookieSecure,
				sessionTimeoutMinutes,
				requireEmailVerification,
				allowedEmailDomains,
				allowSignups,
				autoSignupRoleIds: [...autoSignupRoleIds],
				oidcEnabled,
				oidcIssuerUrl,
				oidcClientId,
				oidcClientSecret,
				oidcRedirectUri,
				oidcScopes,
				oidcOnly,
			}
		})
	})

	const hasChanges = $derived(
		original !== null &&
			(accessTokenExpireMinutes !== original.accessTokenExpireMinutes ||
				refreshTokenExpireDays !== original.refreshTokenExpireDays ||
				authCookieSecure !== original.authCookieSecure ||
				sessionTimeoutMinutes !== original.sessionTimeoutMinutes ||
				requireEmailVerification !== original.requireEmailVerification ||
				allowedEmailDomains !== original.allowedEmailDomains ||
				allowSignups !== original.allowSignups ||
				!arrayEquals(autoSignupRoleIds, original.autoSignupRoleIds) ||
				oidcEnabled !== original.oidcEnabled ||
				oidcIssuerUrl !== original.oidcIssuerUrl ||
				oidcClientId !== original.oidcClientId ||
				oidcClientSecret !== original.oidcClientSecret ||
				oidcRedirectUri !== original.oidcRedirectUri ||
				oidcScopes !== original.oidcScopes ||
				oidcOnly !== original.oidcOnly)
	)

	let isSaving = $state(false)
	let saveError = $state<string | null>(null)
	let saveSuccess = $state<string | null>(null)

	function resetDraft() {
		if (!original) return
		accessTokenExpireMinutes = original.accessTokenExpireMinutes
		refreshTokenExpireDays = original.refreshTokenExpireDays
		authCookieSecure = original.authCookieSecure
		sessionTimeoutMinutes = original.sessionTimeoutMinutes
		requireEmailVerification = original.requireEmailVerification
		allowedEmailDomains = original.allowedEmailDomains
		allowSignups = original.allowSignups
		autoSignupRoleIds = [...original.autoSignupRoleIds]
		oidcEnabled = original.oidcEnabled
		oidcIssuerUrl = original.oidcIssuerUrl
		oidcClientId = original.oidcClientId
		oidcClientSecret = original.oidcClientSecret
		oidcRedirectUri = original.oidcRedirectUri
		oidcScopes = original.oidcScopes
		oidcOnly = original.oidcOnly
		saveError = null
		saveSuccess = null
	}

	async function save() {
		if (!ctx.response || !hasChanges || !original) return
		isSaving = true
		saveError = null
		saveSuccess = null
		try {
			const secPatch: Record<string, unknown> = {}
			if (accessTokenExpireMinutes !== original.accessTokenExpireMinutes)
				secPatch.access_token_expire_minutes = asNumberOrUndefined(accessTokenExpireMinutes)
			if (refreshTokenExpireDays !== original.refreshTokenExpireDays)
				secPatch.refresh_token_expire_days = asNumberOrUndefined(refreshTokenExpireDays)
			if (authCookieSecure !== original.authCookieSecure)
				secPatch.auth_cookie_secure = authCookieSecure
			if (sessionTimeoutMinutes !== original.sessionTimeoutMinutes)
				secPatch.session_timeout_minutes = asNumberOrUndefined(sessionTimeoutMinutes)
			if (requireEmailVerification !== original.requireEmailVerification)
				secPatch.require_email_verification = requireEmailVerification
			if (allowedEmailDomains !== original.allowedEmailDomains)
				secPatch.allowed_email_domains = parseCommaList(allowedEmailDomains)
			if (allowSignups !== original.allowSignups) secPatch.allow_signups = allowSignups
			if (!arrayEquals(autoSignupRoleIds, original.autoSignupRoleIds))
				secPatch.auto_signup_role_ids = autoSignupRoleIds

			if (
				oidcEnabled !== original.oidcEnabled ||
				oidcIssuerUrl !== original.oidcIssuerUrl ||
				oidcClientId !== original.oidcClientId ||
				oidcClientSecret !== original.oidcClientSecret ||
				oidcRedirectUri !== original.oidcRedirectUri ||
				oidcScopes !== original.oidcScopes ||
				oidcOnly !== original.oidcOnly
			) {
				const oidcPatch: Record<string, unknown> = {}
				if (oidcEnabled !== original.oidcEnabled) oidcPatch.enabled = oidcEnabled
				if (oidcIssuerUrl !== original.oidcIssuerUrl)
					oidcPatch.issuer_url = oidcIssuerUrl || null
				if (oidcClientId !== original.oidcClientId)
					oidcPatch.client_id = oidcClientId || null
				if (oidcClientSecret !== original.oidcClientSecret)
					oidcPatch.client_secret = oidcClientSecret || null
				if (oidcRedirectUri !== original.oidcRedirectUri)
					oidcPatch.redirect_uri = oidcRedirectUri || null
				if (oidcScopes !== original.oidcScopes)
					oidcPatch.scopes = parseCommaList(oidcScopes)
				if (oidcOnly !== original.oidcOnly) oidcPatch.only = oidcOnly
				secPatch.oidc = oidcPatch
			}

			const result = await api.PATCH('/v1/settings', {
				body: {
					data: { security: secPatch },
					expected_versions: ctx.response.versions ?? null,
				},
			})
			if (result.error) {
				if (result.response.status === 409) {
					saveError = 'settings were updated elsewhere. reload and try again.'
				} else {
					const detail = result.error?.detail
					saveError = typeof detail === 'string' ? detail : 'failed to save settings'
				}
				return
			}
			ctx.setFromResponse(result.data!)
			saveSuccess = 'saved'
		} catch (e) {
			console.error('Failed to save security settings', e)
			saveError = 'failed to save settings'
		} finally {
			isSaving = false
		}
	}
</script>

<div class="flex flex-col gap-4">
	<div class="flex items-center justify-between gap-2">
		<div>
			{#if saveError}
				<p class="text-sm text-red-400">{saveError}</p>
			{:else if saveSuccess}
				<p class="text-sm text-emerald-400">{saveSuccess}</p>
			{/if}
		</div>
		<div class="flex items-center gap-2">
			<Button
				variant="secondary"
				class="rounded-xl"
				onclick={ctx.fetchSettings}
				disabled={ctx.isFetching || isSaving}
			>
				<RefreshCw class="mr-1.5 h-4 w-4" />
				reload
			</Button>
			<Button
				variant="secondary"
				class="rounded-xl"
				onclick={resetDraft}
				disabled={!hasChanges || isSaving}
			>
				<RotateCcw class="mr-1.5 h-4 w-4" />
				reset
			</Button>
			<Button class="rounded-xl" onclick={save} disabled={!hasChanges || isSaving}>
				<Save class="mr-1.5 h-4 w-4" />
				{isSaving ? 'saving...' : 'save'}
			</Button>
		</div>
	</div>

	<SettingsSecurity
		bind:accessTokenExpireMinutes
		bind:refreshTokenExpireDays
		bind:authCookieSecure
		bind:sessionTimeoutMinutes
		bind:requireEmailVerification
		bind:allowedEmailDomains
		bind:allowSignups
		bind:autoSignupRoleIds
		bind:oidcEnabled
		bind:oidcIssuerUrl
		bind:oidcClientId
		bind:oidcClientSecret
		bind:oidcRedirectUri
		bind:oidcScopes
		bind:oidcOnly
		{secretKeyConfigured}
		{secretKeyUsesDefault}
		{jwtAlgorithm}
		{enableOauth}
		{corsOrigins}
	/>
</div>
