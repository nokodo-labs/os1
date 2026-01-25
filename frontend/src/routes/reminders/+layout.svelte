<script lang="ts">
	import { page } from '$app/state'
	import { pageTitleStore } from '$lib/stores/pageTitle.svelte'
	import type { Snippet } from 'svelte'

	let { children }: { children: Snippet } = $props()

	// Keep page title in sync
	$effect(() => {
		pageTitleStore.pageTitle = 'reminders'
	})

	// Track selected list from URL
	const selectedListId = $derived(page.params.listId ?? null)
</script>

<div class="min-h-0 w-full flex-1 px-[clamp(12px,3vw,36px)] pb-10">
	{@render children()}
</div>
