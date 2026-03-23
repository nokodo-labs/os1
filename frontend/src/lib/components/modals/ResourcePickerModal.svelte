<script lang="ts">
	import { resolve } from '$app/paths'
	import { searchStream, type SearchResult } from '$lib/api/streaming/searchStream'
	import ChatBubbles from '$lib/components/icons/ChatBubbles.svelte'
	import CheckBox from '$lib/components/icons/CheckBox.svelte'
	import Clip from '$lib/components/icons/Clip.svelte'
	import Document from '$lib/components/icons/Document.svelte'
	import Grid from '$lib/components/icons/Grid.svelte'
	import ListBullet from '$lib/components/icons/ListBullet.svelte'
	import Search from '$lib/components/icons/Search.svelte'
	import BaseModal from '$lib/components/modals/BaseModal.svelte'
	import Timestamp from '$lib/components/Timestamp.svelte'
	import { type ResourceFilterMode, type ResourceItem } from '$lib/components/widgets/types'
	import type { Thread } from '$lib/stores/chat.svelte'
	import { chat } from '$lib/stores/chat.svelte'
	import { apiFileToResource, files } from '$lib/stores/files.svelte'
	import { notes, type Note } from '$lib/stores/notes.svelte'
	import { reminders, type ReminderListWithCounts } from '$lib/stores/reminders.svelte'
	import { SvelteSet } from 'svelte/reactivity'

	interface Props {
		open: boolean
		onClose: () => void
		onSelect: (resource: ResourceItem) => void
		excludeIds?: Set<string>
		title?: string
	}

	let {
		open,
		onClose,
		onSelect,
		excludeIds = new Set(),
		title = 'add resource',
	}: Props = $props()

	let searchQuery = $state('')
	let activeFilter = $state<ResourceFilterMode>('all')
	let layout = $state<'grid' | 'list'>('list')
	let loading = $state(false)
	let searchResults = $state<ResourceItem[]>([])
	let localResults = $state<ResourceItem[]>([])
	let searchDebounce: ReturnType<typeof setTimeout> | null = null
	let abortController: AbortController | null = null

	const filterOptions: { value: ResourceFilterMode; label: string; icon?: typeof ChatBubbles }[] =
		[
			{ value: 'all', label: 'all' },
			{ value: 'threads', label: 'chats', icon: ChatBubbles },
			{ value: 'notes', label: 'notes', icon: Document },
			{ value: 'reminders', label: 'reminders', icon: CheckBox },
			{ value: 'files', label: 'files', icon: Clip },
		]

	function threadToResource(thread: Thread): ResourceItem {
		return {
			id: thread.id,
			type: 'thread',
			title: thread.title ?? 'untitled chat',
			href: resolve(`/c/${thread.id}`),
			updatedAt: new Date(thread.last_activity_at).getTime(),
			createdAt: new Date(thread.created_at).getTime(),
			meta: { tags: thread.tags },
		}
	}

	function noteToResource(note: Note): ResourceItem {
		return {
			id: note.id,
			type: 'note',
			title: note.title || 'untitled note',
			preview: note.content.slice(0, 120),
			href: resolve(`/notes/${note.id}`),
			updatedAt: note.updatedAt,
			createdAt: note.createdAt,
			meta: { labels: note.labels },
		}
	}

	function reminderListToResource(list: ReminderListWithCounts): ResourceItem {
		return {
			id: list.id,
			type: 'reminder_list',
			title: list.name,
			subtitle: list.description ?? undefined,
			href: resolve(`/reminders/lists/${list.id}`),
			updatedAt: new Date(list.updated_at).getTime(),
			createdAt: new Date(list.created_at).getTime(),
			meta: {
				total_count: list.total_count,
				pending_count: list.pending_count,
				completed_count: list.completed_count,
				color: list.color,
				icon: list.icon,
			},
		}
	}

	async function loadFileResources(): Promise<ResourceItem[]> {
		const allFiles = await files.load()
		const resources = allFiles.filter((f) => !excludeIds.has(f.id)).map(apiFileToResource)
		void files.loadThumbnails(resources.map((r) => r.id))
		return resources
	}

	function searchResultToResource(result: SearchResult): ResourceItem {
		const typeMap: Record<string, ResourceItem['type']> = {
			thread: 'thread',
			note: 'note',
			reminder: 'reminder_list',
		}
		const hrefMap: Record<string, string> = {
			thread: `/c/${result.id}`,
			note: `/notes/${result.id}`,
			reminder: `/reminders/lists/${result.id}`,
		}
		return {
			id: result.id,
			type: typeMap[result.type] ?? 'file',
			title: result.title,
			preview: result.preview ?? undefined,
			href: resolve((hrefMap[result.type] ?? '#') as `/c/${string}`),
			updatedAt: new Date(result.updated_at).getTime(),
			createdAt: new Date(result.created_at).getTime(),
		}
	}

	function buildLocalResults(): ResourceItem[] {
		const items: ResourceItem[] = []
		if (activeFilter === 'all' || activeFilter === 'threads') {
			for (const thread of chat.recentThreads) {
				if (!excludeIds.has(thread.id)) items.push(threadToResource(thread))
			}
		}
		if (activeFilter === 'all' || activeFilter === 'notes') {
			for (const note of notes.all) {
				if (!excludeIds.has(note.id)) items.push(noteToResource(note))
			}
		}
		if (activeFilter === 'all' || activeFilter === 'reminders') {
			for (const list of reminders.lists) {
				if (!excludeIds.has(list.id)) items.push(reminderListToResource(list))
			}
		}
		items.sort((a, b) => b.updatedAt - a.updatedAt)
		return items
	}

	async function buildLocalResultsWithFiles(): Promise<ResourceItem[]> {
		const items = buildLocalResults()
		if (activeFilter === 'all' || activeFilter === 'files') {
			const fileResources = await loadFileResources()
			items.push(...fileResources)
		}
		items.sort((a, b) => b.updatedAt - a.updatedAt)
		return items
	}

	async function runSearch(query: string) {
		abortController?.abort()
		if (!query.trim()) {
			searchResults = []
			loading = false
			return
		}

		loading = true
		abortController = new AbortController()

		// files filter: use local filtering on the API results
		if (activeFilter === 'files') {
			const fileItems = await loadFileResources()
			const lowerQ = query.toLowerCase()
			searchResults = fileItems.filter((f) => f.title.toLowerCase().includes(lowerQ))
			loading = false
			return
		}

		const typeMap: Record<string, string[]> = {
			all: ['thread', 'note', 'reminder'],
			threads: ['thread'],
			notes: ['note'],
			reminders: ['reminder'],
		}
		const types = typeMap[activeFilter] ?? ['thread', 'note', 'reminder']

		const seen = new SvelteSet<string>()
		const results: ResourceItem[] = []
		try {
			for await (const result of searchStream({
				query,
				types: types.length > 0 ? types : undefined,
				limit: 30,
				mode: 'full',
				signal: abortController.signal,
			})) {
				const key = `${result.type}:${result.id}`
				if (!seen.has(key) && !excludeIds.has(result.id)) {
					seen.add(key)
					results.push(searchResultToResource(result))
				}
			}
			searchResults = results
		} catch {
			// aborted or network error
		} finally {
			loading = false
		}
	}

	function handleSearchInput(value: string) {
		searchQuery = value
		if (searchDebounce) clearTimeout(searchDebounce)
		searchDebounce = setTimeout(() => {
			void runSearch(value)
		}, 250)
	}

	// deduplicate search results against local results
	const displayResults = $derived.by((): ResourceItem[] => {
		if (searchQuery.trim()) {
			const seen = new SvelteSet<string>()
			const merged: ResourceItem[] = []
			for (const r of searchResults) {
				const key = `${r.type}:${r.id}`
				if (!seen.has(key)) {
					seen.add(key)
					merged.push(r)
				}
			}
			// also include local matches not in search results
			const lowerQ = searchQuery.toLowerCase()
			for (const r of localResults) {
				const key = `${r.type}:${r.id}`
				if (!seen.has(key) && r.title.toLowerCase().includes(lowerQ)) {
					seen.add(key)
					merged.push(r)
				}
			}
			return merged
		}
		return localResults
	})

	function handleSelect(resource: ResourceItem) {
		onSelect(resource)
	}

	async function loadLocal() {
		loading = true
		await Promise.all([chat.refreshThreads(), notes.load(), reminders.loadListsAndCounts()])
		localResults = await buildLocalResultsWithFiles()
		loading = false
	}

	$effect(() => {
		if (open) {
			searchQuery = ''
			activeFilter = 'all'
			searchResults = []
			void loadLocal()
		} else {
			abortController?.abort()
		}
	})

	// rebuild local results when filter changes
	$effect(() => {
		if (open && !searchQuery.trim()) {
			void (async () => {
				localResults = await buildLocalResultsWithFiles()
			})()
		}
	})

	function getTypeIcon(type: ResourceItem['type']) {
		const map: Record<string, { icon: typeof ChatBubbles; color: string }> = {
			thread: { icon: ChatBubbles, color: 'text-emerald-400 bg-emerald-500/15' },
			note: { icon: Document, color: 'text-amber-400 bg-amber-500/15' },
			reminder_list: { icon: CheckBox, color: 'text-sky-400 bg-sky-500/15' },
			file: { icon: Clip, color: 'text-rose-400 bg-rose-500/15' },
		}
		return map[type] ?? { icon: Clip, color: 'text-foreground/50 bg-foreground/10' }
	}
</script>

<BaseModal
	{open}
	{title}
	onClose={() => {
		abortController?.abort()
		onClose()
	}}
	widthClassName="max-w-2xl"
>
	<div class="flex flex-col gap-3">
		<!-- search bar -->
		<div class="relative">
			<Search
				class="text-foreground/40 pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2"
			/>
			<input
				type="text"
				class="rounded-pill border-foreground/10 bg-foreground/5 text-foreground/90 placeholder:text-foreground/40 focus:border-foreground/20 focus:bg-foreground/8 w-full border py-2.5 pr-3 pl-9 text-sm transition-colors outline-none"
				placeholder="search resources..."
				value={searchQuery}
				oninput={(e) => handleSearchInput(e.currentTarget.value)}
			/>
		</div>

		<!-- filter tabs + layout toggle -->
		<div class="flex items-center gap-2">
			<div class="scrollbar-none flex flex-1 gap-1 overflow-x-auto">
				{#each filterOptions as opt (opt.value)}
					<button
						type="button"
						class="rounded-pill shrink-0 cursor-pointer border px-3 py-1.5 text-xs transition-colors duration-150 {activeFilter ===
						opt.value
							? 'border-foreground/20 bg-foreground/12 text-foreground/90'
							: 'border-foreground/8 text-foreground/50 hover:bg-foreground/5 hover:text-foreground/70 bg-transparent'}"
						onclick={() => {
							activeFilter = opt.value
							if (searchQuery.trim()) void runSearch(searchQuery)
						}}
					>
						{opt.label}
					</button>
				{/each}
			</div>
			<div class="flex gap-0.5">
				<button
					type="button"
					class="flex size-7 cursor-pointer items-center justify-center rounded-lg border-none bg-transparent transition-colors {layout ===
					'grid'
						? 'text-foreground/80'
						: 'text-foreground/30 hover:text-foreground/50'}"
					onclick={() => (layout = 'grid')}
					aria-label="grid view"
				>
					<Grid class="size-3.5" />
				</button>
				<button
					type="button"
					class="flex size-7 cursor-pointer items-center justify-center rounded-lg border-none bg-transparent transition-colors {layout ===
					'list'
						? 'text-foreground/80'
						: 'text-foreground/30 hover:text-foreground/50'}"
					onclick={() => (layout = 'list')}
					aria-label="list view"
				>
					<ListBullet class="size-3.5" />
				</button>
			</div>
		</div>

		<!-- results list -->
		<div class="max-h-96 min-h-48 overflow-y-auto">
			{#if loading}
				<div class="flex items-center justify-center py-12">
					<div
						class="border-foreground/20 size-5 animate-spin rounded-full border-2 border-t-white/60"
					></div>
				</div>
			{:else if displayResults.length === 0}
				<div class="flex flex-col items-center justify-center py-12 text-center">
					<p class="text-foreground/40 text-sm">
						{searchQuery.trim()
							? 'no matching resources found'
							: 'no resources available'}
					</p>
				</div>
			{:else if layout === 'list'}
				<div class="flex flex-col gap-1">
					{#each displayResults as resource (resource.id)}
						{@const typeInfo = getTypeIcon(resource.type)}
						<button
							type="button"
							class="rounded-pill hover:bg-foreground/8 flex w-full cursor-pointer items-center gap-3 border-none bg-transparent px-3 py-2.5 text-left transition-colors duration-150 active:scale-[0.99]"
							onclick={() => handleSelect(resource)}
						>
							{#if files.hasThumbnail(resource.id)}
								<img
									src={files.getThumbnailUrl(resource.id)}
									alt={resource.title}
									class="size-8 shrink-0 rounded-lg object-cover"
									draggable="false"
								/>
							{:else}
								<div
									class="flex size-8 shrink-0 items-center justify-center rounded-lg {typeInfo.color}"
								>
									<typeInfo.icon class="size-4" />
								</div>
							{/if}
							<div class="min-w-0 flex-1">
								<div class="text-foreground/90 truncate text-sm font-medium">
									{resource.title}
								</div>
								{#if resource.subtitle || resource.preview}
									<div class="text-foreground/50 truncate text-xs">
										{resource.subtitle ?? resource.preview}
									</div>
								{/if}
							</div>
							<Timestamp
								timestamp={new Date(resource.updatedAt)}
								mode="relative"
								className="shrink-0 text-xs text-foreground/35"
							/>
						</button>
					{/each}
				</div>
			{:else}
				<div class="grid grid-cols-[repeat(auto-fill,minmax(200px,1fr))] gap-2">
					{#each displayResults as resource (resource.id)}
						{@const typeInfo = getTypeIcon(resource.type)}
						<button
							type="button"
							class="border-foreground/8 bg-foreground/4 hover:bg-foreground/8 flex cursor-pointer flex-col gap-2 rounded-2xl border p-4 text-left transition-all duration-150 active:scale-[0.98]"
							onclick={() => handleSelect(resource)}
						>
							<div class="flex items-center gap-2">
								{#if files.hasThumbnail(resource.id)}
									<img
										src={files.getThumbnailUrl(resource.id)}
										alt={resource.title}
										class="size-8 shrink-0 rounded-lg object-cover"
										draggable="false"
									/>
								{:else}
									<div
										class="flex size-8 items-center justify-center rounded-lg {typeInfo.color}"
									>
										<typeInfo.icon class="size-4" />
									</div>
								{/if}
								<span class="text-foreground/40 text-[11px]"
									>{resource.type.replace('_', ' ')}</span
								>
							</div>
							<div class="text-foreground/90 truncate text-sm font-medium">
								{resource.title}
							</div>
							{#if resource.subtitle || resource.preview}
								<div class="text-foreground/50 line-clamp-2 text-xs">
									{resource.subtitle ?? resource.preview}
								</div>
							{/if}
							<Timestamp
								timestamp={new Date(resource.updatedAt)}
								mode="relative"
								className="mt-auto text-[11px] text-foreground/35"
							/>
						</button>
					{/each}
				</div>
			{/if}
		</div>
	</div>
</BaseModal>
