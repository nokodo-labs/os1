<script lang="ts">
	import { api, type BackgroundType } from '$lib/api'
	import SettingsUI from '$lib/components/settings/SettingsUI.svelte'
	import { Button } from '$lib/components/ui/button'
	import { getSettingsContext } from '$lib/settings/context.svelte'
	import { RefreshCw, RotateCcw, Save } from '@lucide/svelte'

	type ThemeMode = 'light' | 'dark' | 'system'

	const ctx = getSettingsContext()

	let defaultTheme = $state<ThemeMode>('system')
	let defaultBackground = $state<BackgroundType | null>(null)
	let authPagesBackground = $state<BackgroundType | null>(null)
	let sidebarCollapsed = $state(false)

	type Original = {
		defaultTheme: ThemeMode
		defaultBackground: BackgroundType | null
		authPagesBackground: BackgroundType | null
		sidebarCollapsed: boolean
	}
	let original = $state<Original | null>(null)

	$effect(() => {
		const r = ctx.response
		if (!r) return
		const ui = r.data.ui
		defaultTheme = (ui?.default_theme as ThemeMode) ?? 'system'
		defaultBackground = ui?.default_background ?? null
		authPagesBackground = ui?.auth_pages_background ?? null
		sidebarCollapsed = ui?.sidebar_collapsed ?? false
		original = { defaultTheme, defaultBackground, authPagesBackground, sidebarCollapsed }
	})

	const hasChanges = $derived(
		original !== null &&
			(defaultTheme !== original.defaultTheme ||
				defaultBackground !== original.defaultBackground ||
				authPagesBackground !== original.authPagesBackground ||
				sidebarCollapsed !== original.sidebarCollapsed)
	)

	let isSaving = $state(false)
	let saveError = $state<string | null>(null)
	let saveSuccess = $state<string | null>(null)

	function resetDraft() {
		if (!original) return
		defaultTheme = original.defaultTheme
		defaultBackground = original.defaultBackground
		authPagesBackground = original.authPagesBackground
		sidebarCollapsed = original.sidebarCollapsed
		saveError = null
		saveSuccess = null
	}

	async function save() {
		if (!ctx.response || !hasChanges) return
		isSaving = true
		saveError = null
		saveSuccess = null
		try {
			const data: Record<string, unknown> = {}
			if (original) {
				const uiPatch: Record<string, unknown> = {}
				if (defaultTheme !== original.defaultTheme) uiPatch.default_theme = defaultTheme
				if (defaultBackground !== original.defaultBackground)
					uiPatch.default_background = defaultBackground ?? 'none'
				if (authPagesBackground !== original.authPagesBackground)
					uiPatch.auth_pages_background = authPagesBackground ?? 'none'
				if (sidebarCollapsed !== original.sidebarCollapsed)
					uiPatch.sidebar_collapsed = sidebarCollapsed
				data.ui = uiPatch
			}
			const result = await api.PATCH('/v1/settings', {
				body: { data, expected_versions: ctx.response.versions ?? null },
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
			console.error('Failed to save UI settings', e)
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

	<SettingsUI
		bind:defaultTheme
		bind:defaultBackground
		bind:authPagesBackground
		bind:sidebarCollapsed
	/>
</div>
