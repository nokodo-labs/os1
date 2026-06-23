<script lang="ts">
	import { browser } from '$app/environment'
	import { page } from '$app/state'
	import { api, unwrap, type Schemas } from '$lib/api'
	import CalendarDetailsModal from '$lib/components/CalendarDetailsModal.svelte'
	import NokodoLoader from '$lib/components/NokodoLoader.svelte'
	import { Button } from '$lib/components/ui/button'
	import { Input } from '$lib/components/ui/input'
	import { Select, SelectContent, SelectItem, SelectTrigger } from '$lib/components/ui/select'
	import UserDetailsModal from '$lib/components/UserDetailsModal.svelte'
	import {
		ArrowDown,
		ArrowUp,
		ChevronLeft,
		ChevronRight,
		Hash,
		RefreshCw,
		Search,
		User,
	} from '@lucide/svelte'
	import { SvelteURLSearchParams } from 'svelte/reactivity'

	type CalendarRecord = Schemas['Calendar']
	type SearchResultItem = Schemas['SearchResultItem']
	type SortKey = 'updated_at' | 'created_at' | 'name' | 'position'
	type SortDir = 'asc' | 'desc'

	const CALENDAR_PAGE_LIMIT = 50
	const CALENDAR_EVENT_SEARCH_LIMIT = 20
	const USER_PARAM = 'user'

	const sortOptions: Array<{ value: SortKey; label: string }> = [
		{ value: 'position', label: 'position' },
		{ value: 'name', label: 'name' },
		{ value: 'updated_at', label: 'updated at' },
		{ value: 'created_at', label: 'created at' },
	]

	function defaultSortDir(sort: SortKey): SortDir {
		if (sort === 'name') return 'asc'
		if (sort === 'position') return 'asc'
		return 'desc'
	}

	let calendars = $state<CalendarRecord[]>([])
	let sortKey = $state<SortKey>('position')
	let sortDir = $state<SortDir>('asc')
	let ownerIdFilter = $state<string | null>(null)
	let pageIndex = $state(0)
	let searchQuery = $state('')
	let refreshToken = $state(0)
	let isLoading = $state(false)
	let error = $state<string | null>(null)
	let total = $state(0)

	let searchResults = $state<SearchResultItem[]>([])
	let isSearching = $state(false)
	let searchError = $state<string | null>(null)
	let _searchTimer: ReturnType<typeof setTimeout> | undefined
	let lastSearchQuery = $state('')

	let isUserDetailsOpen = $state(false)
	let selectedUserId = $state<string | null>(null)
	let isCalendarDetailsOpen = $state(false)
	let selectedCalendarId = $state<string | null>(null)
	let highlightedEventId = $state<string | null>(null)

	let listRequestId = 0
	let searchRequestId = 0

	const isSearchMode = $derived(searchQuery.trim().length > 0)

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

	function setSort(next: string) {
		const option = sortOptions.find((item) => item.value === next)
		if (!option) return
		sortKey = option.value
		sortDir = defaultSortDir(option.value)
		pageIndex = 0
	}

	function toggleSortDir() {
		sortDir = sortDir === 'asc' ? 'desc' : 'asc'
		pageIndex = 0
	}

	function clearOwnerFilter() {
		ownerIdFilter = null
		pageIndex = 0
		updateQueryParams({ [USER_PARAM]: null })
	}

	function openUser(userId: string) {
		selectedUserId = userId
		isUserDetailsOpen = true
	}

	function openCalendar(calendarId: string, eventId: string | null = null) {
		selectedCalendarId = calendarId
		highlightedEventId = eventId
		isCalendarDetailsOpen = true
	}

	function pageOffset(index: number): number {
		return Math.max(0, Math.trunc(index)) * CALENDAR_PAGE_LIMIT
	}

	function eventSearchCalendarId(result: SearchResultItem): string | null {
		const value = result.metadata?.calendar_id
		return typeof value === 'string' && value.length > 0 ? value : null
	}

	function openSearchResult(result: SearchResultItem) {
		const calendarId = eventSearchCalendarId(result)
		if (!calendarId) return
		openCalendar(calendarId, String(result.id))
	}

	function previousPage() {
		pageIndex = Math.max(0, pageIndex - 1)
	}

	function nextPage() {
		if (calendars.length < CALENDAR_PAGE_LIMIT) return
		pageIndex += 1
	}

	function projectCount(calendar: CalendarRecord): number {
		return calendar.project_ids?.length ?? 0
	}

	function formatDate(value: string | null | undefined): string {
		if (!value) return 'never'
		const date = new Date(value)
		if (Number.isNaN(date.getTime())) return 'unknown'
		return new Intl.DateTimeFormat(undefined, {
			month: 'short',
			day: '2-digit',
			hour: '2-digit',
			minute: '2-digit',
		}).format(date)
	}

	function applyUpdatedCalendar(updated: CalendarRecord) {
		calendars = calendars.map((calendar) => (calendar.id === updated.id ? updated : calendar))
		searchResults = searchResults.map((result) =>
			String(result.id) === updated.id
				? {
						...result,
						title: updated.name,
						preview: updated.description ?? null,
						updated_at: updated.updated_at,
					}
				: result
		)
	}

	function removeCalendar(calendarId: string) {
		calendars = calendars.filter((calendar) => calendar.id !== calendarId)
		searchResults = searchResults.filter((result) => String(result.id) !== calendarId)
	}

	$effect(() => {
		const q = searchQuery.trim()
		if (q === lastSearchQuery) return
		lastSearchQuery = q
		searchResults = []
		pageIndex = 0
	})

	$effect(() => {
		if (!browser) return
		const user = page.url.searchParams.get(USER_PARAM)
		const nextOwner = user?.trim() || null
		if (ownerIdFilter !== nextOwner) pageIndex = 0
		ownerIdFilter = nextOwner
	})

	$effect(() => {
		if (!browser) return
		if (searchQuery.trim()) return
		void refreshToken

		const requestId = ++listRequestId
		isLoading = true
		error = null

		Promise.all([
			api
				.GET('/v1/calendars', {
					params: {
						query: {
							owner_id: ownerIdFilter ?? undefined,
							skip: pageOffset(pageIndex),
							limit: CALENDAR_PAGE_LIMIT,
							sort_by: sortKey,
							sort_dir: sortDir,
						},
					},
				})
				.then((result) => unwrap(result)),
			api
				.GET('/v1/calendars/count', {
					params: { query: { owner_id: ownerIdFilter ?? undefined } },
				})
				.then((result) => unwrap(result)),
		])
			.then(([loaded, count]) => {
				if (requestId !== listRequestId) return
				calendars = loaded
				total = count
			})
			.catch((err: unknown) => {
				if (requestId !== listRequestId) return
				error = err instanceof Error ? err.message : 'failed to load calendars'
				calendars = []
			})
			.finally(() => {
				if (requestId === listRequestId) isLoading = false
			})
	})

	$effect(() => {
		if (!browser) return
		const q = searchQuery.trim()
		void refreshToken
		clearTimeout(_searchTimer)

		if (!q) {
			searchResults = []
			searchError = null
			isSearching = false
			return
		}

		isSearching = true
		const requestId = ++searchRequestId
		_searchTimer = setTimeout(() => {
			api.GET('/v1/search', {
				params: {
					query: {
						q,
						types: ['calendar_event'],
						limit: CALENDAR_EVENT_SEARCH_LIMIT,
						mode: 'full',
					},
				},
			})
				.then((result) => unwrap(result))
				.then((results) => {
					if (requestId !== searchRequestId) return
					searchResults = results
					searchError = null
				})
				.catch((err: unknown) => {
					if (requestId !== searchRequestId) return
					searchError = err instanceof Error ? err.message : 'search failed'
					searchResults = []
				})
				.finally(() => {
					if (requestId === searchRequestId) isSearching = false
				})
		}, 300)

		return () => clearTimeout(_searchTimer)
	})
</script>

<div class="flex flex-col gap-6">
	<div class="flex shrink-0 flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
		<div>
			<h2 class="text-2xl font-bold tracking-tight">calendars</h2>
			<p class="text-zinc-400">all calendars.</p>
		</div>
		<div class="flex w-full flex-col gap-2 sm:w-auto sm:flex-row sm:flex-wrap sm:items-center">
			<div class="relative w-full sm:w-auto sm:flex-1">
				<Search
					class="pointer-events-none absolute top-1/2 left-2.5 h-3.5 w-3.5 -translate-y-1/2 text-zinc-500"
				/>
				<Input
					type="search"
					placeholder="search events..."
					bind:value={searchQuery}
					class="w-full pl-8 sm:w-50 lg:w-75"
				/>
			</div>
			<Select value={sortKey} onValueChange={setSort} disabled={isSearchMode}>
				<SelectTrigger class="w-full rounded-xl sm:w-48">
					<span class="truncate text-left">
						{sortOptions.find((option) => option.value === sortKey)?.label ?? sortKey}
					</span>
				</SelectTrigger>
				<SelectContent>
					{#each sortOptions as option (option.value)}
						<SelectItem value={option.value}>{option.label}</SelectItem>
					{/each}
				</SelectContent>
			</Select>
			{#if ownerIdFilter}
				<Button
					variant="outline"
					class="rounded-xl"
					onclick={clearOwnerFilter}
					disabled={isLoading || isSearching}
				>
					owner: {ownerIdFilter}
				</Button>
			{/if}
			<Button
				variant="outline"
				class="rounded-xl px-3"
				onclick={toggleSortDir}
				disabled={isLoading || isSearchMode}
				aria-label="toggle sort direction"
				title="toggle sort direction"
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
				onclick={refresh}
				disabled={isLoading || isSearching}
			>
				<RefreshCw
					class="mr-1.5 h-4 w-4 {isLoading || isSearching ? 'animate-spin' : ''}"
				/>
				{isLoading || isSearching ? 'loading...' : 'refresh'}
			</Button>
		</div>
	</div>

	{#if error}
		<div class="rounded-2xl border border-red-900/50 bg-red-900/10 p-4 text-sm text-red-200">
			{error}
		</div>
	{/if}
	{#if searchError}
		<div class="rounded-2xl border border-red-900/50 bg-red-900/10 p-4 text-sm text-red-200">
			{searchError}
		</div>
	{/if}
	<section class="space-y-4">
		<div class="flex items-center justify-end">
			<div class="flex items-center gap-2">
				{#if isSearchMode}
					<span class="text-xs text-zinc-400 tabular-nums">
						{searchResults.length} event result{searchResults.length === 1 ? '' : 's'}
					</span>
				{:else}
					<Button
						variant="outline"
						class="rounded-xl"
						onclick={previousPage}
						disabled={pageIndex === 0 || isLoading}
					>
						<ChevronLeft class="mr-1.5 h-4 w-4" />
						prev
					</Button>
					<span class="text-xs text-zinc-400 tabular-nums">
						{total > 0
							? `items ${pageIndex * CALENDAR_PAGE_LIMIT + 1}–${pageIndex * CALENDAR_PAGE_LIMIT + calendars.length} of ${total}`
							: ''}
					</span>
					<Button
						variant="outline"
						class="rounded-xl"
						onclick={nextPage}
						disabled={calendars.length < CALENDAR_PAGE_LIMIT || isLoading}
					>
						next
						<ChevronRight class="ml-1.5 h-4 w-4" />
					</Button>
				{/if}
			</div>
		</div>

		{#if (isLoading && calendars.length === 0 && !isSearchMode) || (isSearching && searchResults.length === 0)}
			<div
				class="flex items-center justify-center rounded-xl border border-zinc-800 bg-zinc-950 p-10"
			>
				<NokodoLoader />
			</div>
		{:else if isSearchMode && searchResults.length === 0}
			<div
				class="rounded-xl border border-dashed border-zinc-800 p-10 text-center text-sm text-zinc-500"
			>
				no events found
			</div>
		{:else if !isSearchMode && calendars.length === 0}
			<div
				class="rounded-xl border border-dashed border-zinc-800 p-10 text-center text-sm text-zinc-500"
			>
				no calendars found
			</div>
		{:else if isSearchMode}
			<div class="flex flex-col gap-2">
				{#each searchResults as result (result.id)}
					{@const resultCalendarId = eventSearchCalendarId(result)}
					<div
						role="button"
						tabindex="0"
						class="flex w-full items-start justify-between gap-4 rounded-2xl border border-zinc-800 bg-zinc-900 p-4 text-left transition-colors hover:border-zinc-700 hover:bg-zinc-800/50"
						onclick={() => openSearchResult(result)}
						onkeydown={(event) => {
							if (event.key !== 'Enter' && event.key !== ' ') return
							event.preventDefault()
							openSearchResult(result)
						}}
					>
						<div class="min-w-0 space-y-1">
							<div class="truncate font-medium">{result.title}</div>
							{#if result.preview}
								<div class="line-clamp-2 text-sm text-zinc-400">
									{result.preview}
								</div>
							{/if}
							<div class="flex flex-wrap items-center gap-3 text-xs text-zinc-500">
								{#if resultCalendarId}
									<span>calendar {resultCalendarId}</span>
								{/if}
								<span
									class="inline-flex items-center gap-1.5 font-mono text-[10px] opacity-60"
								>
									<Hash class="h-3 w-3" />
									{result.id}
								</span>
								{#if result.score !== null && result.score !== undefined}
									<span>score {result.score.toFixed(3)}</span>
								{/if}
							</div>
						</div>
						<div class="shrink-0 text-right text-xs text-zinc-500">
							updated {formatDate(result.updated_at)}
						</div>
					</div>
				{/each}
			</div>
		{:else}
			<div class="flex flex-col gap-2">
				{#each calendars as calendar (calendar.id)}
					{@const calendarProjectCount = projectCount(calendar)}
					<div
						role="button"
						tabindex="0"
						class="flex w-full items-start justify-between gap-4 rounded-2xl border border-zinc-800 bg-zinc-900 p-4 text-left transition-colors hover:border-zinc-700 hover:bg-zinc-800/50"
						onclick={() => openCalendar(calendar.id)}
						onkeydown={(event) => {
							if (event.key !== 'Enter' && event.key !== ' ') return
							event.preventDefault()
							openCalendar(calendar.id)
						}}
					>
						<div class="flex min-w-0 gap-4">
							<span
								class="mt-1 h-4 w-4 shrink-0 rounded-full border border-zinc-700"
								style="background-color: {calendar.color}"
							></span>
							<div class="min-w-0 space-y-1">
								<div class="flex flex-wrap items-center gap-2">
									<span class="truncate font-medium">{calendar.name}</span>
									{#if calendar.is_default}
										<span
											class="rounded-md bg-emerald-500/10 px-2 py-0.5 text-[10px] font-medium tracking-wider text-emerald-400 uppercase"
											>default</span
										>
									{/if}
								</div>
								{#if calendar.description}
									<div class="line-clamp-1 text-sm text-zinc-400">
										{calendar.description}
									</div>
								{/if}
								<div
									class="flex flex-wrap items-center gap-3 text-xs text-zinc-500"
								>
									<span
										class="inline-flex items-center gap-1.5 font-mono text-[10px] opacity-60"
									>
										<Hash class="h-3 w-3" />
										{calendar.id}
									</span>
									<span class="inline-flex items-center gap-1">
										<User class="h-3.5 w-3.5" />
										<button
											type="button"
											class="cursor-pointer bg-transparent p-0 text-left text-xs text-zinc-500 underline underline-offset-4 hover:text-zinc-300"
											onclick={(event) => {
												event.stopPropagation()
												openUser(calendar.owner_id)
											}}>{calendar.owner_id}</button
										>
									</span>
									{#if calendar.timezone}
										<span>{calendar.timezone}</span>
									{/if}
									<span>
										{calendarProjectCount} project{calendarProjectCount === 1
											? ''
											: 's'}
									</span>
								</div>
							</div>
						</div>
						<div class="shrink-0 text-right text-xs text-zinc-500">
							updated {formatDate(calendar.updated_at)}
						</div>
					</div>
				{/each}
			</div>
		{/if}
	</section>
</div>

<CalendarDetailsModal
	bind:open={isCalendarDetailsOpen}
	calendarId={selectedCalendarId}
	highlightEventId={highlightedEventId}
	onUpdated={applyUpdatedCalendar}
	onDeleted={removeCalendar}
	onViewUser={openUser}
/>
<UserDetailsModal bind:open={isUserDetailsOpen} userId={selectedUserId} />
