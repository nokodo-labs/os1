<script lang="ts">
	import { page } from '$app/state'
	import MasterDetailScaffold from '$lib/components/layouts/MasterDetailScaffold.svelte'
	import NotesSidebar from '$lib/components/notes/NotesSidebar.svelte'
	import { accentStore } from '$lib/stores/accent.svelte'
	import { appNavigation } from '$lib/stores/appNavigation.svelte'
	import { pageTitleStore } from '$lib/stores/pageTitle.svelte'
	import type { Snippet } from 'svelte'

	let { children }: { children: Snippet } = $props()

	$effect(() => {
		pageTitleStore.pageTitle = 'notes'
	})

	$effect(() => {
		accentStore.set('notes')
	})

	$effect(() => {
		appNavigation.setLastVisited('notes', page.url.pathname)
	})

	const selectedNoteId = $derived(page.params.id ?? null)
	const mobileFullBleed = $derived(page.url.pathname === '/notes')
</script>

<MasterDetailScaffold
	masterWidthClass="w-[clamp(280px,30vw,520px)] h-full"
	ariaLabel="notes"
	{mobileFullBleed}
>
	{#snippet master({ isMobile })}
		<NotesSidebar {selectedNoteId} {isMobile} />
	{/snippet}

	{@render children()}
</MasterDetailScaffold>
