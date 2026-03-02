<script lang="ts">
	import { browser } from '$app/environment'
	import { api, unwrap, type Schemas } from '$lib/api'

	type ReminderListWithCounts = Schemas['ReminderListWithCounts']
	type SearchResultItem = Schemas['SearchResultItem']

	import NokodoLoader from '$lib/components/NokodoLoader.svelte'
	import ReminderListDetailsModal from '$lib/components/ReminderListDetailsModal.svelte'
	import UserDetailsModal from '$lib/components/UserDetailsModal.svelte'
	import { Button } from '$lib/components/ui/button'
	import {
		Card,
		CardContent,
		CardDescription,
		CardHeader,
		CardTitle,
	} from '$lib/components/ui/card'
	import { Input } from '$lib/components/ui/input'
	import { Select, SelectContent, SelectItem, SelectTrigger } from '$lib/components/ui/select'
	import {
		ArrowDown,
		ArrowUp,
		Circle,
		CircleCheck,
		Clock,
		Hash,
		ListChecks,
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
	let isLoading = $state(false)
	let error = $state<string | null>(null)

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
			api.GET('/v1/reminders/search', { params: { query: { q } } })
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
	}

	function toggleSortDir() {
		sortDir = sortDir === 'asc' ? 'desc' : 'asc'
	}

	$effect(() => {
		if (!browser) return

		// depend on refreshToken to allow manual refresh
		void refreshToken

		isLoading = true
		error = null

		api.GET('/v1/reminders/lists', {
			params: {
				query: {
					include_counts: true,
					sort_by: sortKey,
					sort_dir: sortDir,
					limit: 200,
				},
			},
		})
			.then((r) => unwrap(r))
			.then((result) => {
				lists = result
			})
			.catch((e: unknown) => {
				error = e instanceof Error ? e.message : 'failed to load reminder lists'
				lists = []
			})
			.finally(() => {
				isLoading = false
			})
	})
</script>

<div class="flex min-h-0 flex-1 flex-col gap-6">
	<div class="flex shrink-0 flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
		<div>
			<h2 class="text-2xl font-bold tracking-tight">reminders</h2>
			<p class="text-zinc-400">all reminder lists and their reminders.</p>
		</div>
		<div class="flex flex-wrap items-center gap-2">
			<div class="relative">
				<Search
					class="pointer-events-none absolute top-1/2 left-2.5 h-3.5 w-3.5 -translate-y-1/2 text-zinc-500"
				/>
				<Input
					type="search"
					placeholder="search lists..."
					bind:value={searchQuery}
					class="h-9 w-50 pl-8 lg:w-75"
				/>
			</div>
			<Select value={sortKey} onValueChange={(v: string) => setSort(v as ListSortKey)}>
				<SelectTrigger class="w-56 rounded-xl">
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
				class="rounded-xl px-3"
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
			<Button
				variant="outline"
				class="rounded-xl"
				onclick={() => refresh()}
				disabled={isLoading}
			>
				{isLoading ? 'loading...' : 'refresh'}
			</Button>
		</div>
	</div>

	{#if error}
		<div
			class="shrink-0 rounded-2xl border border-red-900/50 bg-red-900/10 p-4 text-sm text-red-200"
		>
			{error}
		</div>
	{/if}

	<Card
		class="flex min-h-0 flex-1 flex-col rounded-2xl border-zinc-800 bg-zinc-900 text-zinc-100"
	>
		<CardHeader class="shrink-0">
			<CardTitle>{searchQuery.trim() ? 'reminders' : 'reminder lists'}</CardTitle>
			<CardDescription>
				{searchQuery.trim()
					? `${searchResults.length} result${searchResults.length === 1 ? '' : 's'}`
					: `${lists.length} list${lists.length === 1 ? '' : 's'}`}
			</CardDescription>
		</CardHeader>
		<CardContent class="flex min-h-0 flex-1 flex-col space-y-2 overflow-y-auto">
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
									{#if r.subtitle}
										<div class="line-clamp-1 text-sm text-zinc-400">
											{r.subtitle}
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
						class="cursor-pointer rounded-xl border border-zinc-800 bg-zinc-950 transition-colors hover:border-zinc-700"
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
						<div class="flex w-full items-start gap-3 p-4 text-left">
							<div class="min-w-0 flex-1 space-y-2">
								<div class="flex items-center gap-2">
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
									class="flex flex-wrap items-center gap-2 text-xs text-zinc-400"
								>
									<span
										class="inline-flex items-center gap-1 rounded-md bg-zinc-900 px-2 py-0.5"
									>
										<Hash class="h-3.5 w-3.5" />
										{list.id}
									</span>
									<span
										class="inline-flex items-center gap-1 rounded-md bg-zinc-900 px-2 py-0.5"
									>
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
										class="inline-flex items-center gap-1 rounded-md bg-zinc-900 px-2 py-0.5"
									>
										<ListChecks class="h-3.5 w-3.5" />
										total {list.total_count}
									</span>
									<span
										class="inline-flex items-center gap-1 rounded-md bg-zinc-900 px-2 py-0.5"
									>
										<Circle class="h-3.5 w-3.5" />
										pending {list.pending_count}
									</span>
									<span
										class="inline-flex items-center gap-1 rounded-md bg-zinc-900 px-2 py-0.5"
									>
										<CircleCheck class="h-3.5 w-3.5" />
										completed {list.completed_count}
									</span>
								</div>
							</div>
							<div class="shrink-0 text-xs text-zinc-500">
								<div class="flex items-center gap-1">
									<Clock class="h-3.5 w-3.5" />
									updated {new Date(list.updated_at).toLocaleString()}
								</div>
							</div>
						</div>
					</div>
				{/each}
			{/if}
		</CardContent>
	</Card>
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
