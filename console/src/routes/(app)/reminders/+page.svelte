<script lang="ts">
	import { browser } from '$app/environment'
	import { api, unwrap, type Schemas } from '$lib/api'

	type ReminderListWithCounts = Schemas['ReminderListWithCounts']
	type SearchResultItem = Schemas['SearchResultItem']

	import NokodoLoader from '$lib/components/NokodoLoader.svelte'
	import ReminderListDetailsModal from '$lib/components/ReminderListDetailsModal.svelte'
	import { Button } from '$lib/components/ui/button'
	import UserDetailsModal from '$lib/components/UserDetailsModal.svelte'

	import { Input } from '$lib/components/ui/input'
	import { Select, SelectContent, SelectItem, SelectTrigger } from '$lib/components/ui/select'
	import {
		ArrowDown,
		ArrowUp,
		ChevronLeft,
		ChevronRight,
		Circle,
		CircleCheck,
		Clock,
		Hash,
		ListChecks,
		RefreshCw,
		Search,
		User,
	} from '@lucide/svelte'

	type ListSortKey = 'updated_at' | 'created_at' | 'name' | 'position'
	type SortDir = 'asc' | 'desc'

	const listSortOptions: Array<{ value: ListSortKey; label: string }> = [
		{ value: 'updated_at', label: 'updated at' },
		{ value: 'created_at', label: 'created at' },
		{ value: 'name', label: 'name' },
		{ value: 'position', label: 'position' },
	]
	const REMINDER_LIST_PAGE_LIMIT = 50

	function defaultSortDir(sort: ListSortKey): SortDir {
		if (sort === 'name') return 'asc'
		if (sort === 'position') return 'asc'
		return 'desc'
	}

	let sortKey = $state<ListSortKey>('updated_at')
	let sortDir = $state<SortDir>('desc')
	let searchQuery = $state('')
	let refreshToken = $state(0)

	let lists = $state<ReminderListWithCounts[]>([])
	let pageIndex = $state(0)
	let isLoading = $state(false)
	let error = $state<string | null>(null)
	let listRequestId = 0

	let searchResults = $state<SearchResultItem[]>([])
	let isSearching = $state(false)
	let searchError = $state<string | null>(null)
	let _searchTimer: ReturnType<typeof setTimeout> | undefined

	let isUserDetailsOpen = $state(false)
	let selectedUserId = $state<string | null>(null)

	let isListDetailsOpen = $state(false)
	let selectedListId = $state<string | null>(null)

	$effect(() => {
		const q = searchQuery.trim()
		clearTimeout(_searchTimer)
		if (!q) {
			searchResults = []
			searchError = null
			return
		}
		isSearching = true
		_searchTimer = setTimeout(() => {
			api.GET('/v1/reminder-lists/search', {
				params: { query: { q, limit: 20 } },
			})
				.then((r) => unwrap(r))
				.then((page) => {
					searchResults = page.items
				})
				.catch((e: unknown) => {
					searchError = e instanceof Error ? e.message : 'search failed'
					searchResults = []
				})
				.finally(() => {
					isSearching = false
				})
		}, 300)
		return () => clearTimeout(_searchTimer)
	})

	function openUser(userId: string) {
		selectedUserId = userId
		isUserDetailsOpen = true
	}

	function openList(listId: string) {
		selectedListId = listId
		isListDetailsOpen = true
	}

	function refresh() {
		refreshToken += 1
	}

	function setSort(next: ListSortKey) {
		sortKey = next
		sortDir = defaultSortDir(next)
		pageIndex = 0
	}

	function toggleSortDir() {
		sortDir = sortDir === 'asc' ? 'desc' : 'asc'
		pageIndex = 0
	}

	function pageOffset(index: number): number {
		return Math.max(0, Math.trunc(index)) * REMINDER_LIST_PAGE_LIMIT
	}

	function previousPage() {
		pageIndex = Math.max(0, pageIndex - 1)
	}

	function nextPage() {
		if (lists.length < REMINDER_LIST_PAGE_LIMIT) return
		pageIndex += 1
	}

	$effect(() => {
		if (!browser) return

		// depend on refreshToken to allow manual refresh
		void refreshToken

		isLoading = true
		error = null
		const requestId = ++listRequestId

		api.GET('/v1/reminder-lists', {
			params: {
				query: {
					include_counts: true,
					sort_by: sortKey,
					sort_dir: sortDir,
					skip: pageOffset(pageIndex),
					limit: REMINDER_LIST_PAGE_LIMIT,
				},
			},
		})
			.then((r) => unwrap(r))
			.then((listsResult) => {
				if (requestId !== listRequestId) return
				lists = listsResult
			})
			.catch((e: unknown) => {
				if (requestId !== listRequestId) return
				error = e instanceof Error ? e.message : 'failed to load reminder lists'
				lists = []
			})
			.finally(() => {
				if (requestId === listRequestId) isLoading = false
			})
	})
</script>

<div class="flex flex-col gap-6">
	<div class="flex shrink-0 flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
		<div>
			<h2 class="text-2xl font-bold tracking-tight">reminders</h2>
			<p class="text-zinc-400">all reminder lists and their reminders.</p>
		</div>
		<div class="flex w-full flex-col gap-2 sm:w-auto sm:flex-row sm:flex-wrap sm:items-center">
			<div class="relative w-full sm:w-auto sm:flex-1">
				<Search
					class="pointer-events-none absolute top-1/2 left-2.5 h-3.5 w-3.5 -translate-y-1/2 text-zinc-500"
				/>
				<Input
					type="search"
					placeholder="search lists..."
					bind:value={searchQuery}
					class="w-full pl-8 sm:w-50 lg:w-75"
				/>
			</div>
			<div class="flex w-full items-center gap-2 sm:w-auto">
				<Select value={sortKey} onValueChange={(v: string) => setSort(v as ListSortKey)}>
					<SelectTrigger class="w-full flex-1 rounded-xl sm:w-56">
						<span class="truncate text-left">
							{listSortOptions.find((o) => o.value === sortKey)?.label ?? sortKey}
						</span>
					</SelectTrigger>
					<SelectContent>
						{#each listSortOptions as opt (opt.value)}
							<SelectItem value={opt.value}>{opt.label}</SelectItem>
						{/each}
					</SelectContent>
				</Select>
				<Button
					variant="outline"
					class="shrink-0 rounded-xl px-3"
					onclick={() => toggleSortDir()}
					disabled={isLoading}
					title="toggle sort direction"
					aria-label="toggle sort direction"
				>
					{#if sortDir === 'asc'}
						<ArrowUp class="h-4 w-4" />
					{:else}
						<ArrowDown class="h-4 w-4" />
					{/if}
				</Button>
			</div>
			<div class="flex w-full items-center gap-2 sm:w-auto">
				<Button
					variant="outline"
					class="flex-1 rounded-xl sm:flex-none"
					onclick={() => refresh()}
					disabled={isLoading}
				>
					<RefreshCw class="mr-2 h-4 w-4 {isLoading ? 'animate-spin' : ''}" />
					{isLoading ? 'loading...' : 'refresh'}
				</Button>
			</div>
		</div>
	</div>

	{#if error}
		<div
			class="shrink-0 rounded-2xl border border-red-900/50 bg-red-900/10 p-4 text-sm text-red-200"
		>
			{error}
		</div>
	{/if}

	<div class="flex flex-col gap-4">
		<div class="flex items-center justify-between gap-3">
			<div class="text-sm text-zinc-400">
				{searchQuery.trim()
					? `${searchResults.length} result${searchResults.length === 1 ? '' : 's'}`
					: `page ${pageIndex + 1} · ${lists.length} list${lists.length === 1 ? '' : 's'}`}
			</div>
			{#if !searchQuery.trim()}
				<div class="flex items-center gap-2">
					<Button
						variant="outline"
						class="rounded-xl"
						onclick={previousPage}
						disabled={pageIndex === 0 || isLoading}
					>
						<ChevronLeft class="mr-1.5 h-4 w-4" />
						prev
					</Button>
					<Button
						variant="outline"
						class="rounded-xl"
						onclick={nextPage}
						disabled={lists.length < REMINDER_LIST_PAGE_LIMIT || isLoading}
					>
						next
						<ChevronRight class="ml-1.5 h-4 w-4" />
					</Button>
				</div>
			{/if}
		</div>
		<div class="flex flex-col space-y-2">
			{#if searchQuery.trim()}
				<!-- search results mode: individual reminders -->
				{#if isSearching}
					<div
						class="flex min-h-0 flex-1 items-center justify-center rounded-xl border border-zinc-800 bg-zinc-950 p-10"
					>
						<NokodoLoader />
					</div>
				{:else if searchError}
					<div
						class="shrink-0 rounded-2xl border border-red-900/50 bg-red-900/10 p-4 text-sm text-red-200"
					>
						{searchError}
					</div>
				{:else if searchResults.length === 0}
					<div
						class="rounded-xl border border-dashed border-zinc-800 p-10 text-center text-sm text-zinc-500"
					>
						no results found
					</div>
				{:else}
					{#each searchResults as r (r.id)}
						<div
							class="rounded-xl border border-zinc-800 bg-zinc-950 p-4 transition-colors hover:border-zinc-700"
						>
							<div
								class="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between"
							>
								<div class="min-w-0 flex-1 space-y-1">
									<div class="flex items-center gap-2">
										<Circle class="h-4 w-4 text-zinc-500" />
										<span class="truncate font-medium">{r.title}</span>
									</div>
									{#if r.preview}
										<div class="line-clamp-1 text-sm text-zinc-400">
											{r.preview}
										</div>
									{/if}
									<span
										class="inline-flex items-center gap-1 rounded-md bg-zinc-900 px-2 py-0.5 text-xs text-zinc-400"
									>
										<Hash class="h-3.5 w-3.5" />
										{r.id}
									</span>
								</div>
								{#if r.score != null}
									<span class="shrink-0 text-xs text-zinc-500"
										>{(r.score * 100).toFixed(1)}%</span
									>
								{/if}
							</div>
						</div>
					{/each}
				{/if}
			{:else}
				<!-- normal list view -->
				{#if isLoading && lists.length === 0}
					<div
						class="flex min-h-0 flex-1 items-center justify-center rounded-xl border border-zinc-800 bg-zinc-950 p-10"
					>
						<NokodoLoader />
					</div>
				{/if}

				{#if lists.length === 0 && !isLoading}
					<div
						class="rounded-xl border border-dashed border-zinc-800 p-10 text-center text-sm text-zinc-500"
					>
						no reminder lists found
					</div>
				{/if}

				{#each lists as list (list.id)}
					<div
						role="button"
						tabindex="0"
						class="flex w-full items-center justify-between gap-4 rounded-2xl border border-zinc-800 bg-zinc-900 p-4 text-left transition-colors hover:border-zinc-700 hover:bg-zinc-800/50"
						onclick={(e: MouseEvent) => {
							if (
								(e.target as HTMLElement).closest('button:not([data-row-click])') ==
								null
							) {
								openList(list.id)
							}
						}}
						onkeydown={(e: KeyboardEvent) => {
							if (e.key === 'Enter' || e.key === ' ') {
								e.preventDefault()
								openList(list.id)
							}
						}}
					>
						<div class="flex min-w-0 flex-1 items-center gap-4">
							<div
								class="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-sky-500/15 text-sky-400"
							>
								<ListChecks class="h-5 w-5" />
							</div>
							<div class="min-w-0 flex-1 space-y-1">
								<div class="flex flex-wrap items-center gap-2">
									{#if list.color}
										<span
											class="inline-block h-3 w-3 rounded-full"
											style="background-color: {list.color}"
										></span>
									{/if}
									<span class="truncate font-medium">{list.name}</span>
								</div>
								{#if list.description}
									<div class="line-clamp-1 text-sm text-zinc-400">
										{list.description}
									</div>
								{/if}
								<div
									class="flex flex-wrap items-center gap-3 text-xs text-zinc-500"
								>
									<span
										class="inline-flex items-center gap-1.5 font-mono text-[10px] opacity-50"
									>
										<Hash class="h-3 w-3" />
										{list.id}
									</span>
									<span class="inline-flex items-center gap-1">
										<User class="h-3.5 w-3.5" />
										<button
											type="button"
											class="underline underline-offset-4 hover:text-zinc-200"
											onclick={(e: MouseEvent) => {
												e.stopPropagation()
												openUser(list.owner_id)
											}}
										>
											{list.owner_id}
										</button>
									</span>
									<span
										class="inline-flex items-center gap-1 rounded-md bg-zinc-800 px-2 py-0.5 text-[10px] font-medium tracking-wider text-zinc-300 uppercase"
									>
										<ListChecks class="h-3 w-3" />
										total {list.total_count}
									</span>
									<span
										class="inline-flex items-center gap-1 rounded-md bg-amber-500/10 px-2 py-0.5 text-[10px] font-medium tracking-wider text-amber-400 uppercase"
									>
										<Circle class="h-3 w-3" />
										pending {list.pending_count}
									</span>
									<span
										class="inline-flex items-center gap-1 rounded-md bg-emerald-500/10 px-2 py-0.5 text-[10px] font-medium tracking-wider text-emerald-400 uppercase"
									>
										<CircleCheck class="h-3 w-3" />
										completed {list.completed_count}
									</span>
								</div>
							</div>
						</div>
						<div class="shrink-0 text-xs text-zinc-500">
							<div class="flex items-center gap-1.5 whitespace-nowrap">
								<Clock class="h-3.5 w-3.5" />
								{new Date(list.updated_at).toLocaleString()}
							</div>
						</div>
					</div>
				{/each}
			{/if}
		</div>
	</div>
</div>

<UserDetailsModal bind:open={isUserDetailsOpen} userId={selectedUserId} />
<ReminderListDetailsModal
	bind:open={isListDetailsOpen}
	listId={selectedListId}
	onViewUser={(userId) => openUser(userId)}
	onUpdated={(l) => {
		lists = lists.map((x) => (x.id === l.id ? { ...x, ...l } : x))
	}}
	onDeleted={(id) => {
		lists = lists.filter((x) => x.id !== id)
		isListDetailsOpen = false
	}}
/>
