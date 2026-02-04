<script lang="ts">
	import { page } from '$app/state'
	import MasterDetailScaffold from '$lib/components/layouts/MasterDetailScaffold.svelte'
	import SettingsSidebar from '$lib/components/settings/SettingsSidebar.svelte'
	import { accentStore } from '$lib/stores/accent.svelte'
	import { pageTitleStore } from '$lib/stores/pageTitle.svelte'
	import type { Snippet } from 'svelte'

	let { children }: { children: Snippet } = $props()

	// keep page title in sync
	$effect(() => {
		pageTitleStore.pageTitle = 'settings'
	})

	// set accent color for auto accent colors feature
	$effect(() => {
		accentStore.set('gray')
	})

	// track selected section from URL
	const selectedSection = $derived.by(() => {
		const parts = page.url.pathname.split('/').filter(Boolean)
		if (parts[0] !== 'settings') return null
		if (parts.length === 1) return 'account'
		return parts[1] ?? null
	})
</script>

<MasterDetailScaffold masterWidthClass="w-[clamp(280px,28vw,420px)]" ariaLabel="settings sections">
	{#snippet master({ isMobile })}
		<SettingsSidebar {selectedSection} {isMobile} />
	{/snippet}

	{@render children()}
</MasterDetailScaffold>
