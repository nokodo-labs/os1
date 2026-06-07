<script lang="ts">
	import { browser } from '$app/environment'
	import { page } from '$app/state'
	import { api, unwrap, type Schemas } from '$lib/api'

	type Note = Schemas['Note']
	type SearchResultItem = Schemas['SearchResultItem']

	import NokodoLoader from '$lib/components/NokodoLoader.svelte'
	import NoteDetailsModal from '$lib/components/NoteDetailsModal.svelte'
	import UserDetailsModal from '$lib/components/UserDetailsModal.svelte'
	import { Button } from '$lib/components/ui/button'

	import { Input } from '$lib/components/ui/input'
	import { Select, SelectContent, SelectItem, SelectTrigger } from '$lib/components/ui/select'
	import {
		ArrowDown,
		ArrowUp,
		ChevronLeft,
		ChevronRight,
		Clock,
		FileText,
		Hash,
		RefreshCw,
		Search,
		Tag,
		User,
		X,
	} from '@lucide/svelte'
	import { SvelteURLSearchParams } from 'svelte/reactivity'

	type SortKey = 'updated_at' | 'created_at' | 'title'
	type SortDir = 'asc' | 'desc'

	const sortOptions: Array<{ value: SortKey; label: string }> = [
		{ value: 'updated_at', label: 'updated at' },
		{ value: 'created_at', label: 'created at' },
		{ value: 'title', label: 'title' },
	]

	function defaultSortDir(sort: SortKey): SortDir {
		if (sort === 'title') return 'asc'
		return 'desc'
	}

	const DEFAULT_SORT: SortKey = 'updated_at'
	const SORT_PARAM = 'sort'
	const SORT_DIR_PARAM = 'sort_dir'
	const USER_PARAM = 'user'

	let sortKey = $state<SortKey>(DEFAULT_SORT)
	let sortDir = $state<SortDir>(defaultSortDir(DEFAULT_SORT))
	let ownerIdFilter = $state<string | null>(null)
	let pageIndex = $state(0)
	let limit = $state(50)
	let refreshToken = $state(0)

	let notes = $state<Note[]>([])
	let searchQuery = $state('')
	let isLoading = $state(false)
	let hasNext = $state(false)
	let total = $state(0)
	let error = $state<string | null>(null)

	let searchResults = $state<SearchResultItem[]>([])
	let isSearching = $state(false)
	let searchError = $state<string | null>(null)
	let _searchTimer: ReturnType<typeof setTimeout> | undefined

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
			api.GET('/v1/notes/search', { params: { query: { q } } })
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

	let isUserDetailsOpen = $state(false)
	let selectedUserId = $state<string | null>(null)

	let isNoteDetailsOpen = $state(false)
	let selectedNote = $state<Note | null>(null)

	function openUser(userId: string) {
		selectedUserId = userId
		isUserDetailsOpen = true
	}

	function openNote(note: Note) {
		selectedNote = note
		isNoteDetailsOpen = true
	}

	function refresh() {
		refreshToken += 1
	}

	function replaceUrl(target: string) {
		if (!browser) return
		history.replaceState(history.state, '', target)
	}

	function updateQueryParams(updates: Record<string, string | null>) {
		if (!browser) return
		const url = page.url
		const params = new SvelteURLSearchParams(url.searchParams)
		for (const [key, value] of Object.entries(updates)) {
			if (!value) params.delete(key)
			else params.set(key, value)
		}
		const qs = params.toString()
		replaceUrl(qs ? `${url.pathname}?${qs}` : url.pathname)
	}

	function setSort(next: SortKey) {
		sortKey = next
		sortDir = defaultSortDir(next)
		pageIndex = 0
		updateQueryParams({ [SORT_PARAM]: next, [SORT_DIR_PARAM]: sortDir })
	}

	function toggleSortDir() {
		const next = sortDir === 'asc' ? 'desc' : 'asc'
		sortDir = next
		pageIndex = 0
		updateQueryParams({ [SORT_DIR_PARAM]: next })
	}

	function clearOwnerFilter() {
		ownerIdFilter = null
		pageIndex = 0
		updateQueryParams({ [USER_PARAM]: null })
	}

	$effect(() => {
		if (!browser) return

		const sp = page.url.searchParams
		const sort = sp.get(SORT_PARAM)
		const nextSort =
			sort && sortOptions.some((o) => o.value === (sort as SortKey))
				? (sort as SortKey)
				: DEFAULT_SORT
		const dir = sp.get(SORT_DIR_PARAM)
		const nextDir = dir === 'asc' || dir === 'desc' ? dir : defaultSortDir(nextSort)
		const user = sp.get(USER_PARAM)
		const nextOwner = user?.trim() || null

		if (sortKey !== nextSort || sortDir !== nextDir || ownerIdFilter !== nextOwner) {
			pageIndex = 0
		}

		sortKey = nextSort
		sortDir = nextDir
		ownerIdFilter = nextOwner
	})

	$effect(() => {
		if (!browser) return

		const skip = pageIndex * limit + refreshToken * 0

		isLoading = true
		error = null

		Promise.all([
			api
				.GET('/v1/notes', {
					params: {
						query: {
							owner_id: ownerIdFilter ?? undefined,
							include_deleted: true,
							skip,
							limit,
							sort_by: sortKey,
							sort_dir: sortDir,
						},
					},
				})
				.then((r) => unwrap(r)),
			api
				.GET('/v1/notes/count', {
					params: {
						query: { owner_id: ownerIdFilter ?? undefined, include_deleted: true },
					},
				})
				.then((r) => unwrap(r)),
		])
			.then(([result, count]) => {
				notes = result
				total = count
				hasNext = (pageIndex + 1) * limit < count
			})
			.catch((e: unknown) => {
				error = e instanceof Error ? e.message : 'failed to load notes'
				notes = []
				hasNext = false
			})
			.finally(() => {
				isLoading = false
			})
	})
</script>

<div class="flex flex-col gap-6">
	<div class="flex shrink-0 flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
		<div>
			<h2 class="text-2xl font-bold tracking-tight">notes</h2>
			<p class="text-zinc-400">all notes in the system.</p>
		</div>
		<div class="flex w-full flex-col gap-2 sm:w-auto sm:flex-row sm:flex-wrap sm:items-center">
			<div class="relative w-full sm:w-auto sm:flex-1">
				<Search
					class="pointer-events-none absolute top-1/2 left-2.5 h-3.5 w-3.5 -translate-y-1/2 text-zinc-500"
				/>
				<Input
					type="search"
					placeholder="search notes..."
					bind:value={searchQuery}
					class="w-full pl-8 sm:w-50 lg:w-75"
				/>
			</div>
			<div class="flex w-full items-center gap-2 sm:w-auto">
				<Select value={sortKey} onValueChange={(v: string) => setSort(v as SortKey)}>
					<SelectTrigger class="w-full flex-1 rounded-xl sm:w-56">
						<span class="truncate text-left">
							{sortOptions.find((o) => o.value === sortKey)?.label ?? sortKey}
						</span>
					</SelectTrigger>
					<SelectContent>
						{#each sortOptions as opt (opt.value)}
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
				{#if ownerIdFilter}
					<Button
						variant="outline"
						class="flex-1 rounded-xl sm:flex-none"
						onclick={() => clearOwnerFilter()}
						disabled={isLoading}
					>
						<X class="mr-2 h-4 w-4" />
						owner: {ownerIdFilter}
					</Button>
				{/if}
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
		<div class="flex items-center justify-end">
			<div class="flex items-center gap-2">
				<Button
					variant="outline"
					class="rounded-xl"
					onclick={() => {
						pageIndex = Math.max(0, pageIndex - 1)
					}}
					disabled={pageIndex === 0 || isLoading}
				>
					<ChevronLeft class="mr-1.5 h-4 w-4" />
					prev
				</Button>
				<span class="text-xs text-zinc-400 tabular-nums">
					{total > 0
						? `items ${pageIndex * limit + 1}–${pageIndex * limit + notes.length} of ${total}`
						: ''}
				</span>
				<Button
					variant="outline"
					class="rounded-xl"
					onclick={() => {
						pageIndex += 1
					}}
					disabled={!hasNext || isLoading}
				>
					next
					<ChevronRight class="ml-1.5 h-4 w-4" />
				</Button>
			</div>
		</div>
		<div class="flex flex-col space-y-2">
			{#if searchQuery.trim()}
				<!-- search results mode -->
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
										<FileText class="h-4 w-4 text-zinc-500" />
										<span class="truncate font-medium">{r.title}</span>
									</div>
									{#if r.preview}
										<div class="line-clamp-1 text-sm text-zinc-400">
											{r.preview}
										</div>
									{/if}
									<div class="flex items-center gap-2 text-xs text-zinc-400">
										<span
											class="inline-flex items-center gap-1 rounded-md bg-zinc-900 px-2 py-0.5"
										>
											<Hash class="h-3.5 w-3.5" />
											{r.id}
										</span>
									</div>
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
				<!-- normal paginated list mode -->
				{#if isLoading && notes.length === 0}
					<div
						class="flex min-h-0 flex-1 items-center justify-center rounded-xl border border-zinc-800 bg-zinc-950 p-10"
					>
						<NokodoLoader />
					</div>
				{/if}

				{#if notes.length === 0 && !isLoading}
					<div
						class="rounded-xl border border-dashed border-zinc-800 p-10 text-center text-sm text-zinc-500"
					>
						no notes found
					</div>
				{/if}

				{#each notes as n (n.id)}
					<!-- svelte-ignore a11y_click_events_have_key_events -->
					<!-- svelte-ignore a11y_no_static_element_interactions -->
					<div
						class="flex w-full cursor-pointer items-center justify-between gap-4 rounded-2xl border border-zinc-800 bg-zinc-900 p-4 text-left transition-colors hover:border-zinc-700 hover:bg-zinc-800/50"
						onclick={() => openNote(n)}
					>
						<div class="flex min-w-0 flex-1 items-center gap-4">
							<div
								class="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-amber-500/15 text-amber-400"
							>
								<FileText class="h-5 w-5" />
							</div>
							<div class="min-w-0 flex-1 space-y-1">
								<div class="flex flex-wrap items-center gap-2">
									<span class="truncate text-base font-medium text-zinc-100"
										>{n.title}</span
									>
									{#if n.deleted_at}
										<span
											class="inline-flex items-center gap-1 rounded-md bg-red-500/10 px-2 py-0.5 text-[10px] font-medium tracking-wider text-red-400 uppercase"
										>
											deleted
										</span>
									{/if}
								</div>
								{#if n.content}
									<div class="line-clamp-2 text-sm text-zinc-400">
										{n.content}
									</div>
								{/if}
								<div
									class="flex flex-wrap items-center gap-3 text-xs text-zinc-500"
								>
									<span
										class="inline-flex items-center gap-1.5 font-mono text-[10px] opacity-50"
									>
										<Hash class="h-3 w-3" />
										{n.id}
									</span>
									<span class="inline-flex items-center gap-1">
										<User class="h-3.5 w-3.5" />
										<button
											type="button"
											class="underline underline-offset-4 hover:text-zinc-200"
											onclick={(e) => {
												e.stopPropagation()
												openUser(n.user_id)
											}}
										>
											{n.user_id}
										</button>
									</span>
									{#if (n.labels ?? []).length > 0}
										{#each n.labels ?? [] as label (label)}
											<span
												class="inline-flex items-center gap-1 rounded-md bg-zinc-800 px-2 py-0.5 text-[10px] font-medium tracking-wider text-zinc-300 uppercase"
											>
												<Tag class="h-3 w-3" />
												{label}
											</span>
										{/each}
									{/if}
								</div>
							</div>
						</div>
						<div class="shrink-0 text-xs text-zinc-500">
							<div class="flex items-center gap-1.5 whitespace-nowrap">
								<Clock class="h-3.5 w-3.5" />
								{new Date(n.updated_at).toLocaleString()}
							</div>
							<div class="mt-1 flex items-center gap-1.5 whitespace-nowrap">
								<Clock class="h-3.5 w-3.5" />
								{new Date(n.created_at).toLocaleString()}
							</div>
						</div>
					</div>
				{/each}
			{/if}
		</div>
	</div>
</div>

<UserDetailsModal bind:open={isUserDetailsOpen} userId={selectedUserId} />
<NoteDetailsModal
	bind:open={isNoteDetailsOpen}
	note={selectedNote}
	onViewUser={(userId) => openUser(userId)}
	onUpdated={(n) => {
		notes = notes.map((x) => (x.id === n.id ? n : x))
		selectedNote = n
	}}
	onDeleted={(id) => {
		notes = notes.filter((n) => n.id !== id)
		isNoteDetailsOpen = false
	}}
/>
