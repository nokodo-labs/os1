<script lang="ts">
	import { page } from '$app/state'
	import CalendarSidebar from '$lib/components/calendar/CalendarSidebar.svelte'
	import MasterDetailScaffold from '$lib/components/layouts/MasterDetailScaffold.svelte'
	import { accentStore } from '$lib/stores/accent.svelte'
	import { appNavigation } from '$lib/stores/appNavigation.svelte'
	import { pageTitleStore } from '$lib/stores/pageTitle.svelte'
	import type { Snippet } from 'svelte'

	let { children }: { children: Snippet } = $props()

	$effect(() => {
		pageTitleStore.pageTitle = 'calendar'
	})

	$effect(() => {
		accentStore.set('calendar')
	})

	$effect(() => {
		appNavigation.setLastVisited('calendar', page.url.pathname)
	})
</script>

<MasterDetailScaffold
	masterWidthClass="w-[clamp(260px,24vw,360px)] h-full"
	ariaLabel="calendar"
	detailBottomPaddingClass="pb-6"
>
	{#snippet master({ isMobile })}
		<CalendarSidebar {isMobile} />
	{/snippet}

	{@render children()}
</MasterDetailScaffold>
