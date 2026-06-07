<script lang="ts">
	import { api } from '$lib/api'
	import SettingsBranding from '$lib/components/settings/SettingsBranding.svelte'
	import { Button } from '$lib/components/ui/button'
	import { getSettingsContext } from '$lib/settings/context.svelte'
	import type { PwaManifestAssetsDraft } from '$lib/settings/types'
	import {
		clonePwaAssets,
		defaultPwaAssets,
		pwaAssetsFromResponse,
		pwaAssetsKey,
		pwaAssetsToPatch,
		toStringOrEmpty,
	} from '$lib/settings/utils'
	import { RefreshCw, RotateCcw, Save } from '@lucide/svelte'
	import { untrack } from 'svelte'

	const ctx = getSettingsContext()

	let siteName = $state('')
	let logoUrl = $state('')
	let faviconUrl = $state('')
	let primaryColor = $state('')
	let supportEmail = $state('')
	let adminEmail = $state('')
	let publicFrontendOrigin = $state('')
	let publicCdnOrigin = $state('')
	let publicConsoleOrigin = $state('')
	let pwaManifestUrl = $state('')
	let pwaAssets = $state<PwaManifestAssetsDraft>(defaultPwaAssets())
	// read-only
	let appVersion = $state('')
	let analyticsKeyConfigured = $state(false)

	type Original = {
		siteName: string
		logoUrl: string
		faviconUrl: string
		primaryColor: string
		supportEmail: string
		adminEmail: string
		publicFrontendOrigin: string
		publicCdnOrigin: string
		publicConsoleOrigin: string
		pwaManifestUrl: string
		pwaAssets: PwaManifestAssetsDraft
	}
	let original = $state<Original | null>(null)

	$effect(() => {
		const r = ctx.response
		if (!r) return
		const b = r.data.branding
		siteName = toStringOrEmpty(b?.site_name)
		logoUrl = toStringOrEmpty(b?.logo_url)
		faviconUrl = toStringOrEmpty(b?.favicon_url)
		primaryColor = toStringOrEmpty(b?.primary_color)
		supportEmail = toStringOrEmpty(b?.support_email)
		adminEmail = toStringOrEmpty(b?.admin_email)
		publicFrontendOrigin = toStringOrEmpty(b?.public_frontend_origin)
		publicCdnOrigin = toStringOrEmpty(b?.public_cdn_origin)
		publicConsoleOrigin = toStringOrEmpty(b?.public_console_origin)
		pwaManifestUrl = toStringOrEmpty(b?.pwa_manifest_url)
		pwaAssets = pwaAssetsFromResponse(b?.pwa_assets)
		appVersion = b?.app_version ?? ''
		analyticsKeyConfigured = Boolean(b?.analytics_key)
		untrack(() => {
			original = {
				siteName,
				logoUrl,
				faviconUrl,
				primaryColor,
				supportEmail,
				adminEmail,
				publicFrontendOrigin,
				publicCdnOrigin,
				publicConsoleOrigin,
				pwaManifestUrl,
				pwaAssets: clonePwaAssets(pwaAssets),
			}
		})
	})

	const hasChanges = $derived(
		original !== null &&
			(siteName !== original.siteName ||
				logoUrl !== original.logoUrl ||
				faviconUrl !== original.faviconUrl ||
				primaryColor !== original.primaryColor ||
				supportEmail !== original.supportEmail ||
				adminEmail !== original.adminEmail ||
				publicFrontendOrigin !== original.publicFrontendOrigin ||
				publicCdnOrigin !== original.publicCdnOrigin ||
				publicConsoleOrigin !== original.publicConsoleOrigin ||
				pwaManifestUrl !== original.pwaManifestUrl ||
				pwaAssetsKey(pwaAssets) !== pwaAssetsKey(original.pwaAssets))
	)

	let isSaving = $state(false)
	let saveError = $state<string | null>(null)
	let saveSuccess = $state<string | null>(null)

	function resetDraft() {
		if (!original) return
		siteName = original.siteName
		logoUrl = original.logoUrl
		faviconUrl = original.faviconUrl
		primaryColor = original.primaryColor
		supportEmail = original.supportEmail
		adminEmail = original.adminEmail
		publicFrontendOrigin = original.publicFrontendOrigin
		publicCdnOrigin = original.publicCdnOrigin
		publicConsoleOrigin = original.publicConsoleOrigin
		pwaManifestUrl = original.pwaManifestUrl
		pwaAssets = clonePwaAssets(original.pwaAssets)
		saveError = null
		saveSuccess = null
	}

	async function save() {
		if (!ctx.response || !hasChanges || !original) return
		isSaving = true
		saveError = null
		saveSuccess = null
		try {
			const brandingPatch: Record<string, unknown> = {}
			if (siteName !== original.siteName) brandingPatch.site_name = siteName
			if (logoUrl !== original.logoUrl) brandingPatch.logo_url = logoUrl || null
			if (faviconUrl !== original.faviconUrl) brandingPatch.favicon_url = faviconUrl || null
			if (primaryColor !== original.primaryColor) brandingPatch.primary_color = primaryColor
			if (supportEmail !== original.supportEmail)
				brandingPatch.support_email = supportEmail || null
			if (adminEmail !== original.adminEmail) brandingPatch.admin_email = adminEmail || null
			if (publicFrontendOrigin !== original.publicFrontendOrigin)
				brandingPatch.public_frontend_origin = publicFrontendOrigin || null
			if (publicCdnOrigin !== original.publicCdnOrigin)
				brandingPatch.public_cdn_origin = publicCdnOrigin || null
			if (publicConsoleOrigin !== original.publicConsoleOrigin)
				brandingPatch.public_console_origin = publicConsoleOrigin || null
			if (pwaManifestUrl !== original.pwaManifestUrl)
				brandingPatch.pwa_manifest_url = pwaManifestUrl || null
			if (pwaAssetsKey(pwaAssets) !== pwaAssetsKey(original.pwaAssets))
				brandingPatch.pwa_assets = pwaAssetsToPatch(pwaAssets)

			const result = await api.PATCH('/v1/settings', {
				body: {
					data: { branding: brandingPatch },
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
			console.error('Failed to save branding settings', e)
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

	<SettingsBranding
		bind:siteName
		bind:logoUrl
		bind:faviconUrl
		bind:primaryColor
		bind:supportEmail
		bind:adminEmail
		bind:publicFrontendOrigin
		bind:publicCdnOrigin
		bind:publicConsoleOrigin
		bind:pwaManifestUrl
		bind:pwaAssets
		{appVersion}
		{analyticsKeyConfigured}
	/>
</div>
