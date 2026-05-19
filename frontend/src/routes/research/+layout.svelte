<script lang="ts">
	import { page } from '$app/state'
	import { accentStore } from '$lib/stores/accent.svelte'
	import { appNavigation } from '$lib/stores/appNavigation.svelte'
	import { pageTitleStore } from '$lib/stores/pageTitle.svelte'
	import type { Snippet } from 'svelte'

	let { children }: { children: Snippet } = $props()

	$effect(() => {
		pageTitleStore.pageTitle = 'research'
	})

	$effect(() => {
		accentStore.set('petrol')
	})

	$effect(() => {
		appNavigation.setLastVisited('research', page.url.pathname)
	})
</script>

{@render children()}
