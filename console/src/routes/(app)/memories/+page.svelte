<script lang="ts">
	import { browser } from '$app/environment'
	import { replaceState } from '$app/navigation'
	import { page } from '$app/state'
	import { MemoriesService, type Memory } from '$lib/api'
	import MemoryDetailsModal from '$lib/components/MemoryDetailsModal.svelte'
	import NokodoLoader from '$lib/components/NokodoLoader.svelte'
	import UserDetailsModal from '$lib/components/UserDetailsModal.svelte'
	import { Button } from '$lib/components/ui/button'
	import {
		Card,
		CardContent,
		CardDescription,
		CardHeader,
		CardTitle,
	} from '$lib/components/ui/card'
	import { Select, SelectContent, SelectItem, SelectTrigger } from '$lib/components/ui/select'
	import { ArrowDown, ArrowUp } from '@lucide/svelte'
	import { SvelteURLSearchParams } from 'svelte/reactivity'

	type SortKey = 'updated_at' | 'created_at' | 'last_accessed_at' | 'confidence' | 'category'
	type SortDir = 'asc' | 'desc'

	const sortOptions: Array<{ value: SortKey; label: string }> = [
		{ value: 'updated_at', label: 'updated at' },
		{ value: 'created_at', label: 'created at' },
		{ value: 'last_accessed_at', label: 'last accessed at' },
		{ value: 'confidence', label: 'confidence' },
		{ value: 'category', label: 'category' },
	]

	function defaultSortDir(sort: SortKey): SortDir {
		if (sort === 'category') return 'asc'
		return 'desc'
	}

	const DEFAULT_SORT: SortKey = 'updated_at'
	const SORT_PARAM = 'sort'
	const SORT_DIR_PARAM = 'sort_dir'
	const USER_PARAM = 'user'

	let sortKey = $state<SortKey>(DEFAULT_SORT)
	let sortDir = $state<SortDir>(defaultSortDir(DEFAULT_SORT))
	let userIdFilter = $state<string | null>(null)
	let pageIndex = $state(0)
	let limit = $state(20)
	let refreshToken = $state(0)

	let memories = $state<Memory[]>([])
	let isLoading = $state(false)
	let error = $state<string | null>(null)
	let hasNext = $state(false)

	let isUserDetailsOpen = $state(false)
	let selectedUserId = $state<string | null>(null)
	let isMemoryDetailsOpen = $state(false)
	let selectedMemoryId = $state<string | null>(null)

	function replaceUrl(target: string) {
		if (!browser) return
		window.history.replaceState(window.history.state, '', target)
		replaceState('', {})
	}

	function openUser(userId: string) {
		selectedUserId = userId
		isUserDetailsOpen = true
	}

	function openMemory(memoryId: string) {
		selectedMemoryId = memoryId
		isMemoryDetailsOpen = true
	}

	function refresh() {
		refreshToken += 1
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

	function clearUserFilter() {
		userIdFilter = null
		pageIndex = 0
		memories = []
		updateQueryParams({ [USER_PARAM]: null })
	}

	function preview(text: string, maxLen = 120) {
		const normalized = text.replace(/\s+/g, ' ').trim()
		if (normalized.length <= maxLen) return normalized
		return normalized.slice(0, maxLen) + '…'
	}

	// Sync sort and user filter from URL params
	$effect(() => {
		if (!browser) return

		const sp = page.url.searchParams
		const sort = sp.get(SORT_PARAM)
		const nextSort =
			sort && sortOptions.some((o) => o.value === sort) ? (sort as SortKey) : DEFAULT_SORT
		const dir = sp.get(SORT_DIR_PARAM)
		const nextDir = dir === 'asc' || dir === 'desc' ? dir : defaultSortDir(nextSort)
		const user = sp.get(USER_PARAM)
		const nextUser = user?.trim() ? user : null

		if (sortKey !== nextSort || sortDir !== nextDir || userIdFilter !== nextUser) {
			pageIndex = 0
		}

		sortKey = nextSort
		sortDir = nextDir
		userIdFilter = nextUser
	})

	// Load memories when user filter is set
	$effect(() => {
		if (!browser) return

		// Memories API requires user_id, so only fetch when we have one
		if (!userIdFilter) {
			memories = []
			hasNext = false
			return
		}

		const skip = pageIndex * limit + refreshToken * 0

		isLoading = true
		error = null
		MemoriesService.listMemoriesMemoriesGet(userIdFilter, skip, limit, sortKey, sortDir)
			.then((result) => {
				memories = result
				hasNext = result.length === limit
			})
			.catch((e: unknown) => {
				error = e instanceof Error ? e.message : 'failed to load memories'
				memories = []
				hasNext = false
			})
			.finally(() => {
				isLoading = false
			})
	})
</script>

<div class="space-y-6">
	<div class="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
		<div>
			<h2 class="text-2xl font-bold tracking-tight">memories</h2>
			<p class="text-zinc-400">user-scoped memories (use filters; start from a user).</p>
		</div>
		<div class="flex flex-wrap items-center gap-2">
			<Select value={sortKey} onValueChange={(v: string) => setSort(v as SortKey)}>
				<SelectTrigger class="w-56 rounded-xl">
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
				class="rounded-xl px-3"
				onclick={() => toggleSortDir()}
				disabled={isLoading || !userIdFilter}
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
				disabled={isLoading || !userIdFilter}
			>
				{isLoading ? 'loading...' : 'refresh'}
			</Button>
			{#if userIdFilter}
				<Button variant="outline" class="rounded-xl" onclick={() => clearUserFilter()}>
					user: {userIdFilter} · clear
				</Button>
			{/if}
		</div>
	</div>

	{#if error}
		<div class="rounded-2xl border border-red-900/50 bg-red-900/10 p-4 text-sm text-red-200">
			{error}
		</div>
	{/if}

	<!-- Memories List -->
	<Card class="rounded-2xl border-zinc-800 bg-zinc-900 text-zinc-100">
		<CardHeader class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
			<div>
				<CardTitle>list</CardTitle>
				<CardDescription>
					{#if userIdFilter}
						page {pageIndex + 1} · showing {memories.length}{hasNext ? '+' : ''}
					{:else}
						open a user and click “memories” to filter.
					{/if}
				</CardDescription>
			</div>
			{#if userIdFilter}
				<div class="flex items-center gap-2">
					<Button
						variant="outline"
						class="rounded-xl"
						onclick={() => {
							pageIndex = Math.max(0, pageIndex - 1)
						}}
						disabled={pageIndex === 0 || isLoading}
					>
						prev
					</Button>
					<Button
						variant="outline"
						class="rounded-xl"
						onclick={() => {
							pageIndex += 1
						}}
						disabled={!hasNext || isLoading}
					>
						next
					</Button>
				</div>
			{/if}
		</CardHeader>
		<CardContent class="space-y-2">
			{#if !userIdFilter}
				<div
					class="rounded-xl border border-dashed border-zinc-800 p-10 text-center text-sm text-zinc-500"
				>
					open a user and use the “memories” button to filter.
				</div>
			{:else if isLoading && memories.length === 0}
				<div
					class="flex items-center justify-center rounded-xl border border-zinc-800 bg-zinc-950 p-10"
				>
					<NokodoLoader />
				</div>
			{:else if memories.length === 0 && !isLoading}
				<div
					class="rounded-xl border border-dashed border-zinc-800 p-10 text-center text-sm text-zinc-500"
				>
					no memories found for this user
				</div>
			{:else}
				{#each memories as m (m.id)}
					<div
						role="button"
						tabindex="0"
						class="rounded-xl border border-zinc-800 bg-zinc-950 p-4 text-left transition-colors hover:border-zinc-700"
						onclick={() => openMemory(m.id)}
						onkeydown={(e) => {
							if (e.key === 'Enter' || e.key === ' ') {
								e.preventDefault()
								openMemory(m.id)
							}
						}}
					>
						<div
							class="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between"
						>
							<div class="min-w-0 flex-1">
								<div class="flex items-center gap-2">
									{#if m.category}
										<span
											class="rounded-md bg-zinc-800 px-2 py-0.5 text-xs text-zinc-300"
										>
											{m.category}
										</span>
									{/if}
									{#if m.confidence !== null && m.confidence !== undefined}
										<span class="text-xs text-zinc-500">
											{(m.confidence * 100).toFixed(0)}% confidence
										</span>
									{/if}
								</div>
								<div class="mt-2 font-mono text-sm text-zinc-100">
									{preview(m.content)}
								</div>
								<div
									class="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-zinc-400"
								>
									<div>id: {m.id}</div>
									<div>
										user:
										<button
											type="button"
											class="ml-1 underline underline-offset-4 hover:text-zinc-200"
											onclick={(e) => {
												e.stopPropagation()
												openUser(m.user_id)
											}}
										>
											{m.user_id}
										</button>
									</div>
									{#if m.source_message_id}
										<div>source: {m.source_message_id}</div>
									{/if}
								</div>
							</div>
							<div class="shrink-0 text-xs text-zinc-500">
								<div>updated {new Date(m.updated_at).toLocaleString()}</div>
								<div>created {new Date(m.created_at).toLocaleString()}</div>
								{#if m.last_accessed_at}
									<div>
										accessed {new Date(m.last_accessed_at).toLocaleString()}
									</div>
								{/if}
							</div>
						</div>
					</div>
				{/each}
			{/if}
		</CardContent>
	</Card>
</div>

<UserDetailsModal bind:open={isUserDetailsOpen} userId={selectedUserId} />

<MemoryDetailsModal bind:open={isMemoryDetailsOpen} memoryId={selectedMemoryId} />
