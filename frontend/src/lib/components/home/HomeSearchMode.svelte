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
	import ResourcesView from '$lib/components/ResourcesView.svelte'
	import type { ResourceItem, ResourceLayoutMode } from '$lib/components/widgets/types'
	import { searchProjectResources } from '$lib/resources/projectSearch'
	import { resourceItemKey, searchResultToResource } from '$lib/resources/searchResults'
	import { modals } from '$lib/stores/modals.svelte'
	import { projects } from '$lib/stores/projects.svelte'
	import { SvelteSet } from 'svelte/reactivity'

	interface Props {
		query: string
		types?: SearchResourceType[]
		/** search inside one project instead of everything (threads + notes). */
		projectId?: string | null
	}

	let { query, types = SEARCH_RESOURCE_TYPES, projectId = null }: Props = $props()

	let loading = $state(false)
	let error = $state(false)
	let results = $state<ResourceItem[]>([])
	let layout = $state<ResourceLayoutMode>('list')
	let debounceTimer: number | null = null
	let abortController: AbortController | null = null

	const trimmedQuery = $derived(query.trim())
	const effectiveTypes = $derived(types.length > 0 ? types : SEARCH_RESOURCE_TYPES)
	// a scoped search looks like a global one otherwise, so name the scope
	const scopeName = $derived(projectId ? (projects.getById(projectId)?.name ?? null) : null)

	$effect(() => {
		if (projectId) void projects.load()
	})

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
				const key = resourceItemKey(resource)
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

	/** scoped search is a plain fetch: the per-resource endpoints do not stream. */
	async function runProjectSearch(
		searchQuery: string,
		selectedTypes: SearchResourceType[],
		scopeProjectId: string,
		signal: AbortSignal
	): Promise<void> {
		error = false
		try {
			const scoped = await searchProjectResources({
				query: searchQuery,
				projectId: scopeProjectId,
				types: selectedTypes,
				signal,
			})
			if (!signal.aborted) results = scoped
		} catch {
			if (!signal.aborted) error = true
		} finally {
			if (!signal.aborted) loading = false
		}
	}

	function scheduleSearch(
		searchQuery: string,
		selectedTypes: SearchResourceType[],
		scopeProjectId: string | null
	): void {
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
			if (scopeProjectId) {
				void runProjectSearch(searchQuery, selectedTypes, scopeProjectId, controller.signal)
				return
			}
			void runHybridSearch(searchQuery, selectedTypes, controller.signal)
		}, 180) as unknown as number
	}

	$effect(() => {
		scheduleSearch(trimmedQuery, effectiveTypes, projectId)
	})

	function openResult(resource: ResourceItem): void {
		switch (resource.type) {
			case 'file':
				modals.open('file-details', { fileId: resource.id })
				return
			case 'thread': {
				void goto(
					resource.anchor?.type === 'message'
						? resolve(`/c/${resource.id}?message=${resource.anchor.id}`)
						: resolve(`/c/${resource.id}`)
				)
				return
			}
			case 'note':
				void goto(resolve(`/notes/${resource.id}`))
				return
			case 'reminder':
				return
			case 'reminder_list':
				void goto(
					resource.anchor?.type === 'reminder'
						? resolve(`/reminders/lists/${resource.id}?reminder=${resource.anchor.id}`)
						: resolve('/reminders/lists/[listId]', { listId: resource.id })
				)
				return
			case 'calendar_event':
				return
			case 'calendar':
				void goto(
					resource.anchor?.type === 'calendar_event'
						? resolve(`/calendar?event=${resource.anchor.id}&calendar=${resource.id}`)
						: resolve('/calendar')
				)
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
{:else}
	{#if scopeName}
		<p class="text-foreground/50 px-1 pb-2 text-xs">in {scopeName}</p>
	{/if}
	<ResourcesView
		resources={results}
		loading={loading && results.length === 0}
		bind:layout
		listVariant="pill"
		sort="none"
		showLayoutToggle
		showPagination={false}
		showOwnershipSections={false}
		showScrollTopButton={false}
		onItemClick={openResult}
		emptyMessage="no results found"
		class="w-full"
	/>
{/if}
