<script lang="ts">
	import { resolve } from '$app/paths'
	import { searchStream, type SearchResultType } from '$lib/api/streaming/searchStream'
	import Grid from '$lib/components/icons/Grid.svelte'
	import Search from '$lib/components/icons/Search.svelte'
	import BaseModal from '$lib/components/modals/BaseModal.svelte'
	import ResourcesView from '$lib/components/ResourcesView.svelte'
	import { type ResourceFilterMode, type ResourceItem } from '$lib/components/widgets/types'
	import {
		resourceAccentStyle,
		resourceVisual,
		type ResourceIconComponent,
	} from '$lib/resources/resourceVisuals'
	import { searchResultToResource } from '$lib/resources/searchResults'
	import { calendars, type Calendar as CalendarRecord } from '$lib/stores/calendars.svelte'
	import type { Thread } from '$lib/stores/chat.svelte'
	import { chat } from '$lib/stores/chat.svelte'
	import { apiFileToResource, files } from '$lib/stores/files.svelte'
	import { notes, type Note } from '$lib/stores/notes.svelte'
	import { projects, type Project } from '$lib/stores/projects.svelte'
	import { reminders, type ReminderListWithCounts } from '$lib/stores/reminders.svelte'
	import { session } from '$lib/stores/session.svelte'
	import { SvelteSet } from 'svelte/reactivity'

	interface Props {
		open: boolean
		onClose: () => void
		onSelect: (resource: ResourceItem) => void
		excludeIds?: Set<string>
		allowedTypes?: ResourceItem['type'][]
		title?: string
	}

	let {
		open,
		onClose,
		onSelect,
		excludeIds = new Set(),
		allowedTypes,
		title = 'add resource',
	}: Props = $props()

	let searchQuery = $state('')
	let activeFilter = $state<ResourceFilterMode>('all')
	let loading = $state(false)
	let loadingMore = $state(false)
	let searchResults = $state<ResourceItem[]>([])
	let localResults = $state<ResourceItem[]>([])
	let searchDebounce: ReturnType<typeof setTimeout> | null = null
	let abortController: AbortController | null = null
	const currentUserId = $derived(session.currentUserId)

	type FilterOption = {
		value: ResourceFilterMode
		label: string
		icon: ResourceIconComponent
		resourceType?: ResourceItem['type']
	}

	const allFilterOptions: FilterOption[] = [
		{ value: 'all', label: 'all', icon: Grid },
		{
			value: 'threads',
			label: resourceVisual('thread').pluralLabel,
			icon: resourceVisual('thread').icon,
			resourceType: 'thread',
		},
		{
			value: 'notes',
			label: resourceVisual('note').pluralLabel,
			icon: resourceVisual('note').icon,
			resourceType: 'note',
		},
		{
			value: 'reminders',
			label: resourceVisual('reminder_list').pluralLabel,
			icon: resourceVisual('reminder_list').icon,
			resourceType: 'reminder_list',
		},
		{
			value: 'files',
			label: resourceVisual('file').pluralLabel,
			icon: resourceVisual('file').icon,
			resourceType: 'file',
		},
		{
			value: 'projects',
			label: resourceVisual('project').pluralLabel,
			icon: resourceVisual('project').icon,
			resourceType: 'project',
		},
		{
			value: 'calendars',
			label: resourceVisual('calendar').pluralLabel,
			icon: resourceVisual('calendar').icon,
			resourceType: 'calendar',
		},
	]
	const allowedTypeSet = $derived(
		allowedTypes ? new Set<ResourceItem['type']>(allowedTypes) : null
	)
	const filterOptions = $derived(
		allFilterOptions.filter(
			(option) =>
				!option.resourceType || !allowedTypeSet || allowedTypeSet.has(option.resourceType)
		)
	)
	const canLoadMoreLocal = $derived(
		!loading &&
			!searchQuery.trim() &&
			((isAllowedType('thread') &&
				(activeFilter === 'all' || activeFilter === 'threads') &&
				chat.hasMoreThreads) ||
				(isAllowedType('file') &&
					(activeFilter === 'all' || activeFilter === 'files') &&
					files.hasMore))
	)
	const isLoadingMoreLocal = $derived(
		loadingMore || chat.isLoadingMoreThreads || files.loadingMore
	)

	function isAllowedType(type: ResourceItem['type']): boolean {
		return !allowedTypeSet || allowedTypeSet.has(type)
	}

	function threadToResource(thread: Thread): ResourceItem {
		return {
			id: thread.id,
			type: 'thread',
			title: thread.title ?? 'untitled chat',
			href: resolve(`/c/${thread.id}`),
			updatedAt: new Date(thread.last_activity_at).getTime(),
			createdAt: new Date(thread.created_at).getTime(),
			meta: { tags: thread.tags, owner_id: thread.owner_id },
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
			meta: { labels: note.labels, owner_id: note.userId },
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
				owner_id: list.owner_id,
			},
		}
	}

	function projectToResource(project: Project): ResourceItem {
		return {
			id: project.id,
			type: 'project',
			title: project.name || 'untitled project',
			subtitle: project.description ?? undefined,
			href: resolve(`/projects/${project.id}`),
			updatedAt: new Date(project.updated_at).getTime(),
			createdAt: new Date(project.created_at).getTime(),
			meta: { owner_id: project.owner_id },
		}
	}

	function calendarToResource(calendar: CalendarRecord): ResourceItem {
		return {
			id: calendar.id,
			type: 'calendar',
			title: calendar.name || 'untitled calendar',
			subtitle: calendar.description ?? undefined,
			href: resolve('/calendar'),
			updatedAt: new Date(calendar.updated_at).getTime(),
			createdAt: new Date(calendar.created_at).getTime(),
			meta: {
				owner_id: calendar.owner_id,
				project_ids: calendar.project_ids ?? [],
				color: calendar.color,
			},
		}
	}

	async function loadFileResources(): Promise<ResourceItem[]> {
		const allFiles = await files.load()
		const resources = allFiles.filter((f) => !excludeIds.has(f.id)).map(apiFileToResource)
		void files.loadThumbnails(resources.map((r) => r.id))
		return resources
	}

	function buildLocalResults(): ResourceItem[] {
		const items: ResourceItem[] = []
		if (isAllowedType('thread') && (activeFilter === 'all' || activeFilter === 'threads')) {
			for (const thread of chat.recentThreads) {
				if (!excludeIds.has(thread.id)) items.push(threadToResource(thread))
			}
		}
		if (isAllowedType('note') && (activeFilter === 'all' || activeFilter === 'notes')) {
			for (const note of notes.all) {
				if (!excludeIds.has(note.id)) items.push(noteToResource(note))
			}
		}
		if (
			isAllowedType('reminder_list') &&
			(activeFilter === 'all' || activeFilter === 'reminders')
		) {
			for (const list of reminders.lists) {
				if (!excludeIds.has(list.id)) items.push(reminderListToResource(list))
			}
		}
		if (isAllowedType('project') && (activeFilter === 'all' || activeFilter === 'projects')) {
			for (const project of projects.list) {
				if (!excludeIds.has(project.id)) items.push(projectToResource(project))
			}
		}
		if (isAllowedType('calendar') && (activeFilter === 'all' || activeFilter === 'calendars')) {
			for (const calendar of calendars.all) {
				if (!excludeIds.has(calendar.id)) items.push(calendarToResource(calendar))
			}
		}
		items.sort((a, b) => b.updatedAt - a.updatedAt)
		return items
	}

	async function buildLocalResultsWithFiles(): Promise<ResourceItem[]> {
		const items = buildLocalResults()
		if (isAllowedType('file') && (activeFilter === 'all' || activeFilter === 'files')) {
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

		if (
			activeFilter === 'files' ||
			activeFilter === 'projects' ||
			activeFilter === 'calendars'
		) {
			const fileItems = await buildLocalResultsWithFiles()
			const lowerQ = query.toLowerCase()
			searchResults = fileItems.filter((f) => f.title.toLowerCase().includes(lowerQ))
			loading = false
			return
		}

		const typeMap: Record<string, SearchResultType[]> = {
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
				const resource = searchResultToResource(result)
				if (!seen.has(key) && !excludeIds.has(result.id) && isAllowedType(resource.type)) {
					seen.add(key)
					results.push(resource)
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
				if (!isAllowedType(r.type)) continue
				const key = `${r.type}:${r.id}`
				if (!seen.has(key)) {
					seen.add(key)
					merged.push(r)
				}
			}
			// also include local matches not in search results
			const lowerQ = searchQuery.toLowerCase()
			for (const r of localResults) {
				if (!isAllowedType(r.type)) continue
				const key = `${r.type}:${r.id}`
				if (!seen.has(key) && r.title.toLowerCase().includes(lowerQ)) {
					seen.add(key)
					merged.push(r)
				}
			}
			return merged
		}
		return localResults.filter((resource) => isAllowedType(resource.type))
	})

	$effect(() => {
		if (!filterOptions.some((option) => option.value === activeFilter)) {
			activeFilter = 'all'
		}
	})

	$effect(() => {
		if (!open || !currentUserId) return
		const ownerIds = displayResults
			.map(resourceOwnerId)
			.filter((ownerId): ownerId is string => Boolean(ownerId && ownerId !== currentUserId))
		if (ownerIds.length > 0) void session.ensureUsers(ownerIds)
	})

	function resourceOwnerId(resource: ResourceItem): string | null {
		const ownerId = resource.meta?.owner_id
		return typeof ownerId === 'string' && ownerId.length > 0 ? ownerId : null
	}

	function handleSelect(resource: ResourceItem) {
		onSelect(resource)
	}

	async function loadLocal() {
		loading = true
		await Promise.all([chat.refreshThreads(), notes.load(), reminders.loadListsAndCounts()])
		await Promise.all([projects.load(), calendars.load()])
		localResults = await buildLocalResultsWithFiles()
		loading = false
	}

	async function loadMoreLocal() {
		if (loadingMore || loading || searchQuery.trim()) return
		const tasks: Promise<void>[] = []
		if (
			isAllowedType('thread') &&
			(activeFilter === 'all' || activeFilter === 'threads') &&
			chat.hasMoreThreads
		) {
			tasks.push(chat.loadMoreThreads())
		}
		if (
			isAllowedType('file') &&
			(activeFilter === 'all' || activeFilter === 'files') &&
			files.hasMore
		) {
			tasks.push(files.loadMore())
		}
		if (tasks.length === 0) return

		loadingMore = true
		try {
			await Promise.all(tasks)
			localResults = await buildLocalResultsWithFiles()
		} finally {
			loadingMore = false
		}
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
</script>

<BaseModal
	{open}
	{title}
	onClose={() => {
		abortController?.abort()
		onClose()
	}}
	widthClassName="max-w-5xl"
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
				placeholder="search resources"
				value={searchQuery}
				oninput={(e) => handleSearchInput(e.currentTarget.value)}
			/>
		</div>

		<!-- filter tabs -->
		<div class="flex items-center gap-2">
			<div class="scrollbar-none flex flex-1 gap-1 overflow-x-auto">
				{#each filterOptions as opt (opt.value)}
					{@const Icon = opt.icon}
					{@const optionStyle = opt.resourceType
						? resourceAccentStyle(opt.resourceType)
						: ''}
					<button
						type="button"
						style={optionStyle}
						class="rounded-pill flex shrink-0 cursor-pointer items-center gap-1.5 border px-3 py-1.5 text-xs font-semibold transition-colors duration-150 {activeFilter ===
						opt.value
							? opt.resourceType
								? 'border-[color-mix(in_oklch,var(--resource-accent)_32%,transparent)] bg-[color-mix(in_oklch,var(--resource-accent)_14%,transparent)] text-(--accent-primary)'
								: 'border-foreground/20 bg-foreground/12 text-foreground/90'
							: opt.resourceType
								? 'border-[color-mix(in_oklch,var(--resource-accent)_18%,transparent)] bg-[color-mix(in_oklch,var(--resource-accent)_8%,transparent)] text-(--accent-primary) hover:bg-[color-mix(in_oklch,var(--resource-accent)_12%,transparent)]'
								: 'border-foreground/8 text-foreground/50 hover:bg-foreground/5 hover:text-foreground/70 bg-transparent'}"
						onclick={() => {
							activeFilter = opt.value
							if (searchQuery.trim()) void runSearch(searchQuery)
						}}
					>
						<Icon class="size-3.5 shrink-0" />
						{opt.label}
					</button>
				{/each}
			</div>
		</div>

		<!-- results list -->
		<div class="h-[min(34rem,68dvh)] min-h-[min(18rem,52dvh)]">
			<ResourcesView
				resources={displayResults}
				{loading}
				layout="pill"
				sort="none"
				showLayoutToggle={false}
				showPagination={false}
				showOwnershipSections={false}
				showScrollTopButton={false}
				{currentUserId}
				onLoadMore={loadMoreLocal}
				hasMore={canLoadMoreLocal}
				loadingMore={isLoadingMoreLocal}
				emptyMessage={searchQuery.trim()
					? 'no matching resources found'
					: 'no resources available'}
				onItemClick={handleSelect}
				class="h-full overflow-y-auto pr-1"
			/>
		</div>
	</div>
</BaseModal>
