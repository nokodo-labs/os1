<script lang="ts">
	import { browser } from '$app/environment'
	import { page } from '$app/state'
	import MasterDetailScaffold from '$lib/components/layouts/MasterDetailScaffold.svelte'
	import ReminderListsSidebar from '$lib/components/reminders/ReminderListsSidebar.svelte'
	import { accentStore } from '$lib/stores/accent.svelte'
	import { device } from '$lib/stores/device.svelte'
	import { pageTitleStore } from '$lib/stores/pageTitle.svelte'
	import { reminders } from '$lib/stores/reminders.svelte'
	import type { Snippet } from 'svelte'

	let { children }: { children: Snippet } = $props()

	// keep page title in sync
	$effect(() => {
		pageTitleStore.pageTitle = 'reminders'
	})

	// set accent color for auto accent colors feature
	$effect(() => {
		accentStore.set('reminders')
	})

	// track selected list from URL
	const selectedListId = $derived(page.params.listId ?? null)

	// loading state for desktop sidebar
	let isLoadingLists = $state(false)

	// track last visited path/list for navigation continuity
	$effect(() => {
		if (!browser) return

		const path = page.url.pathname
		if (path.startsWith('/reminders')) {
			reminders.lastVisitedPath = path
		}

		if (selectedListId) reminders.lastVisitedListId = selectedListId

		// ensure the master sidebar has data (desktop only)
		if (device.isMobile) return
		isLoadingLists = true
		void reminders.loadListsAndCounts().finally(() => {
			isLoadingLists = false
		})
	})
</script>

<MasterDetailScaffold masterWidthClass="w-[clamp(280px,30vw,520px)]" ariaLabel="reminder lists">
	{#snippet master({ isMobile })}
		<ReminderListsSidebar {selectedListId} isLoading={isLoadingLists} {isMobile} />
	{/snippet}

	{@render children()}
</MasterDetailScaffold>
