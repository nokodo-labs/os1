<script lang="ts">
	import { browser } from '$app/environment'
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import { page } from '$app/state'
	import MasterDetailScaffold from '$lib/components/layouts/MasterDetailScaffold.svelte'
	import ReminderListsSidebar from '$lib/components/reminders/ReminderListsSidebar.svelte'
	import { accentStore } from '$lib/stores/accent.svelte'
	import { appNavigation } from '$lib/stores/appNavigation.svelte'
	import { pageTitleStore } from '$lib/stores/pageTitle.svelte'
	import { reminders } from '$lib/stores/reminders.svelte'
	import { untrack, type Snippet } from 'svelte'

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
	let listLoadToken = 0

	async function ensureListRoute(path: string, listId: string | null): Promise<void> {
		const token = ++listLoadToken
		isLoadingLists = true
		try {
			const lists = await reminders.loadLists()
			if (token !== listLoadToken) return

			const fallbackList = reminders.defaultList ?? lists[0] ?? null
			if (!fallbackList) return

			if (path === '/reminders') {
				await goto(resolve('/reminders/lists/[listId]', { listId: fallbackList.id }), {
					replaceState: true,
					keepFocus: true,
					noScroll: true,
				})
				return
			}

			if (listId && !lists.some((list) => list.id === listId)) {
				await goto(resolve('/reminders/lists/[listId]', { listId: fallbackList.id }), {
					replaceState: true,
					keepFocus: true,
					noScroll: true,
				})
			}
		} finally {
			if (token === listLoadToken) isLoadingLists = false
		}
	}

	// track last visited path/list for navigation continuity
	$effect(() => {
		if (!browser) return

		const path = page.url.pathname
		if (path.startsWith('/reminders/lists/') && selectedListId) {
			reminders.lastVisitedPath = path
			appNavigation.setLastVisited('reminders', path)
		}

		if (selectedListId) reminders.lastVisitedListId = selectedListId

		void untrack(() => ensureListRoute(path, selectedListId))
	})
</script>

<MasterDetailScaffold masterWidthClass="w-[clamp(280px,30vw,520px)]" ariaLabel="reminder lists">
	{#snippet master({ isMobile })}
		<ReminderListsSidebar {selectedListId} isLoading={isLoadingLists} {isMobile} />
	{/snippet}

	{@render children()}
</MasterDetailScaffold>
