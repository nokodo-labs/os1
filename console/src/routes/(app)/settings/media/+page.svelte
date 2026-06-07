<script lang="ts">
	import { api } from '$lib/api'
	import SettingsMedia from '$lib/components/settings/SettingsMedia.svelte'
	import { Button } from '$lib/components/ui/button'
	import { getSettingsContext } from '$lib/settings/context.svelte'
	import { toMediaAsset, toStringOrEmpty } from '$lib/settings/utils'
	import { RefreshCw, RotateCcw, Save } from '@lucide/svelte'

	type MediaAssetSource = 'default' | 'cdn' | 'custom'

	const ctx = getSettingsContext()

	let faviconSource = $state<MediaAssetSource>('default')
	let faviconUrl = $state('')
	let appleTouchIconSource = $state<MediaAssetSource>('default')
	let appleTouchIconUrl = $state('')
	let sidebarLogoSource = $state<MediaAssetSource>('default')
	let sidebarLogoUrl = $state('')
	let splashLogoSource = $state<MediaAssetSource>('default')
	let splashLogoUrl = $state('')
	// read-only from branding
	let publicCdnOrigin = $state('')

	type Original = {
		faviconSource: MediaAssetSource
		faviconUrl: string
		appleTouchIconSource: MediaAssetSource
		appleTouchIconUrl: string
		sidebarLogoSource: MediaAssetSource
		sidebarLogoUrl: string
		splashLogoSource: MediaAssetSource
		splashLogoUrl: string
	}
	let original = $state<Original | null>(null)

	$effect(() => {
		const r = ctx.response
		if (!r) return
		const favicon = toMediaAsset(r.data.media?.favicon)
		faviconSource = favicon.source
		faviconUrl = favicon.url
		const icon = toMediaAsset(r.data.media?.apple_touch_icon)
		appleTouchIconSource = icon.source
		appleTouchIconUrl = icon.url
		const sidebarLogo = toMediaAsset(r.data.media?.sidebar_logo)
		sidebarLogoSource = sidebarLogo.source
		sidebarLogoUrl = sidebarLogo.url
		const splashLogo = toMediaAsset(r.data.media?.splash_logo)
		splashLogoSource = splashLogo.source
		splashLogoUrl = splashLogo.url
		publicCdnOrigin = toStringOrEmpty(r.data.branding?.public_cdn_origin)
		original = {
			faviconSource,
			faviconUrl,
			appleTouchIconSource,
			appleTouchIconUrl,
			sidebarLogoSource,
			sidebarLogoUrl,
			splashLogoSource,
			splashLogoUrl,
		}
	})

	const hasChanges = $derived(
		original !== null &&
			(faviconSource !== original.faviconSource ||
				faviconUrl !== original.faviconUrl ||
				appleTouchIconSource !== original.appleTouchIconSource ||
				appleTouchIconUrl !== original.appleTouchIconUrl ||
				sidebarLogoSource !== original.sidebarLogoSource ||
				sidebarLogoUrl !== original.sidebarLogoUrl ||
				splashLogoSource !== original.splashLogoSource ||
				splashLogoUrl !== original.splashLogoUrl)
	)

	let isSaving = $state(false)
	let saveError = $state<string | null>(null)
	let saveSuccess = $state<string | null>(null)

	function resetDraft() {
		if (!original) return
		faviconSource = original.faviconSource
		faviconUrl = original.faviconUrl
		appleTouchIconSource = original.appleTouchIconSource
		appleTouchIconUrl = original.appleTouchIconUrl
		sidebarLogoSource = original.sidebarLogoSource
		sidebarLogoUrl = original.sidebarLogoUrl
		splashLogoSource = original.splashLogoSource
		splashLogoUrl = original.splashLogoUrl
		saveError = null
		saveSuccess = null
	}

	async function save() {
		if (!ctx.response || !hasChanges || !original) return
		isSaving = true
		saveError = null
		saveSuccess = null
		try {
			const mediaPatch: Record<string, unknown> = {}
			if (faviconSource !== original.faviconSource || faviconUrl !== original.faviconUrl) {
				mediaPatch.favicon = {
					source: faviconSource,
					url: faviconSource === 'custom' ? faviconUrl || null : null,
				}
			}
			if (
				appleTouchIconSource !== original.appleTouchIconSource ||
				appleTouchIconUrl !== original.appleTouchIconUrl
			) {
				mediaPatch.apple_touch_icon = {
					source: appleTouchIconSource,
					url: appleTouchIconSource === 'custom' ? appleTouchIconUrl || null : null,
				}
			}
			if (
				sidebarLogoSource !== original.sidebarLogoSource ||
				sidebarLogoUrl !== original.sidebarLogoUrl
			) {
				mediaPatch.sidebar_logo = {
					source: sidebarLogoSource,
					url: sidebarLogoSource === 'custom' ? sidebarLogoUrl || null : null,
				}
			}
			if (
				splashLogoSource !== original.splashLogoSource ||
				splashLogoUrl !== original.splashLogoUrl
			) {
				mediaPatch.splash_logo = {
					source: splashLogoSource,
					url: splashLogoSource === 'custom' ? splashLogoUrl || null : null,
				}
			}

			const result = await api.PATCH('/v1/settings', {
				body: {
					data: { media: mediaPatch },
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
			console.error('Failed to save media settings', e)
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

	<SettingsMedia
		bind:faviconSource
		bind:faviconUrl
		bind:appleTouchIconSource
		bind:appleTouchIconUrl
		bind:sidebarLogoSource
		bind:sidebarLogoUrl
		bind:splashLogoSource
		bind:splashLogoUrl
		{publicCdnOrigin}
	/>
</div>
