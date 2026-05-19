<script lang="ts">
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import {
		SEARCH_RESOURCE_TYPES,
		searchStream,
		type SearchResourceType,
	} from '$lib/api/streaming'
	import EmptyState from '$lib/components/EmptyState.svelte'
	import Search from '$lib/components/icons/Search.svelte'
	import NokodoLoader from '$lib/components/NokodoLoader.svelte'
	import ResourcesView from '$lib/components/ResourcesView.svelte'
	import type { ResourceItem, ResourceLayoutMode } from '$lib/components/widgets/types'
	import { searchResultToResource } from '$lib/resources/searchResults'
	import { modals } from '$lib/stores/modals.svelte'
	import { SvelteSet } from 'svelte/reactivity'
	import { fade } from 'svelte/transition'

	interface Props {
		query: string
		types?: SearchResourceType[]
	}

	let { query, types = SEARCH_RESOURCE_TYPES }: Props = $props()

	let loading = $state(false)
	let error = $state(false)
	let results = $state<ResourceItem[]>([])
	let layout = $state<ResourceLayoutMode>('list')
	let debounceTimer: number | null = null
	let abortController: AbortController | null = null

	const trimmedQuery = $derived(query.trim())
	const effectiveTypes = $derived(types.length > 0 ? types : SEARCH_RESOURCE_TYPES)

	async function runHybridSearch(
		searchQuery: string,
		selectedTypes: SearchResourceType[],
		signal: AbortSignal
	): Promise<void> {
		const nextResults: ResourceItem[] = []
		const seen = new SvelteSet<string>()
		error = false
		try {
			for await (const result of searchStream({
				query: searchQuery,
				types: selectedTypes,
				limit: 40,
				mode: 'hybrid',
				signal,
			})) {
				if (signal.aborted) break
				const resource = searchResultToResource(result)
				const key = `${resource.type}:${resource.id}`
				if (seen.has(key)) continue
				seen.add(key)
				nextResults.push(resource)
				results = [...nextResults]
			}
		} catch {
			if (!signal.aborted) error = true
		} finally {
			if (!signal.aborted) loading = false
		}
	}

	function scheduleSearch(searchQuery: string, selectedTypes: SearchResourceType[]): void {
		if (debounceTimer !== null) {
			window.clearTimeout(debounceTimer)
			debounceTimer = null
		}
		abortController?.abort()
		abortController = null

		if (!searchQuery) {
			loading = false
			error = false
			results = []
			return
		}

		loading = true
		results = []
		const controller = new AbortController()
		abortController = controller
		debounceTimer = window.setTimeout(() => {
			debounceTimer = null
			void runHybridSearch(searchQuery, selectedTypes, controller.signal)
		}, 180) as unknown as number
	}

	$effect(() => {
		scheduleSearch(trimmedQuery, effectiveTypes)
	})

	function openResult(resource: ResourceItem): void {
		switch (resource.type) {
			case 'file':
				modals.open('file-details', { fileId: resource.id })
				return
			case 'thread':
				void goto(resolve(`/c/${resource.id}`))
				return
			case 'note':
				void goto(resolve(`/notes/${resource.id}`))
				return
			case 'reminder_list':
				void goto(resolve(`/reminders/lists/${resource.id}`))
				return
			case 'calendar':
				void goto(resolve('/calendar'))
				return
			case 'project':
				void goto(resolve(`/projects/${resource.id}`))
				return
		}
	}
</script>

{#if error}
	<EmptyState label="search failed" class="min-h-[45vh]" compact>
		{#snippet icon()}<Search class="size-5" strokeWidth="2" />{/snippet}
	</EmptyState>
{:else if loading && results.length === 0}
	<div
		class="pointer-events-none absolute inset-0 flex items-center justify-center"
		in:fade={{ duration: 120 }}
		out:fade={{ duration: 260 }}
	>
		<NokodoLoader className="text-foreground/65 text-sm font-semibold" />
	</div>
{:else}
	<ResourcesView
		resources={results}
		loading={false}
		bind:layout
		listVariant="pill"
		sort="none"
		showLayoutToggle
		showPagination={false}
		showOwnershipSections={false}
		onItemClick={openResult}
		scrollTopButtonBottom="calc(6.5rem + env(safe-area-inset-bottom, 0px))"
		emptyMessage="no results found"
		class="w-full"
	/>
{/if}
