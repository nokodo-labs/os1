<script lang="ts">
	import { page } from '$app/state'
	import MasterDetailScaffold from '$lib/components/layouts/MasterDetailScaffold.svelte'
	import NotesSidebar from '$lib/components/notes/NotesSidebar.svelte'
	import { accentStore } from '$lib/stores/accent.svelte'
	import { pageTitleStore } from '$lib/stores/pageTitle.svelte'
	import type { Snippet } from 'svelte'

	let { children }: { children: Snippet } = $props()

	$effect(() => {
		pageTitleStore.pageTitle = 'notes'
	})

	$effect(() => {
		accentStore.set('notes')
	})

	const selectedNoteId = $derived(page.params.id ?? null)
</script>

<MasterDetailScaffold masterWidthClass="w-[clamp(280px,30vw,520px)]" ariaLabel="notes">
	{#snippet master({ isMobile })}
		<NotesSidebar {selectedNoteId} {isMobile} />
	{/snippet}

	{@render children()}
</MasterDetailScaffold>
