<script lang="ts">
	import { page } from '$app/state'
	import MasterDetailScaffold from '$lib/components/layouts/MasterDetailScaffold.svelte'
	import SettingsSidebar from '$lib/components/settings/SettingsSidebar.svelte'
	import { pageTitleStore } from '$lib/stores/pageTitle.svelte'
	import type { Snippet } from 'svelte'

	let { children }: { children: Snippet } = $props()

	// keep page title in sync
	$effect(() => {
		pageTitleStore.pageTitle = 'settings'
	})

	// track selected section from URL
	const selectedSection = $derived.by(() => {
		if (page.params.section) return page.params.section
		if (page.url.pathname === '/settings') return 'account'
		return null
	})
</script>

<MasterDetailScaffold masterWidthClass="w-[clamp(280px,28vw,420px)]" ariaLabel="settings sections">
	{#snippet master({ isMobile })}
		<SettingsSidebar {selectedSection} {isMobile} />
	{/snippet}

	{@render children()}
</MasterDetailScaffold>
