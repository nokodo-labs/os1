<script lang="ts">
	import { browser } from '$app/environment'
	import { goto } from '$app/navigation'
	import { page } from '$app/stores'
	import { ThreadsService, type Thread } from '$lib/api'
	import NokodoLoader from '$lib/components/NokodoLoader.svelte'
	import ThreadDetailsModal from '$lib/components/ThreadDetailsModal.svelte'
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

	type SortKey = 'last_activity_at' | 'updated_at' | 'created_at' | 'title'
	type SortDir = 'asc' | 'desc'

	const sortOrder: SortKey[] = ['last_activity_at', 'updated_at', 'created_at', 'title']

	function sortLabel(key: SortKey) {
		switch (key) {
			case 'last_activity_at':
				return 'activity at'
			case 'updated_at':
				return 'updated at'
			case 'created_at':
				return 'created at'
			case 'title':
				return 'title'
		}
	}

	function defaultSortDir(sort: SortKey): SortDir {
		if (sort === 'title') return 'asc'
		return 'desc'
	}

	type ThreadWithDeletedAt = Thread & { deleted_at?: string | null }

	function deletedAt(thread: Thread): string | null {
		return (thread as ThreadWithDeletedAt).deleted_at ?? null
	}

	const DEFAULT_SORT: SortKey = 'last_activity_at'
	const SORT_PARAM = 'sort'
	const SORT_DIR_PARAM = 'sort_dir'
	const USER_PARAM = 'user'

	let sortKey = $state<SortKey>(DEFAULT_SORT)
	let sortDir = $state<SortDir>(defaultSortDir(DEFAULT_SORT))
	let ownerIdFilter = $state<string | null>(null)
	let pageIndex = $state(0)
	let limit = $state(20)
	let refreshToken = $state(0)

	let threads = $state<Thread[]>([])
	let isLoading = $state(false)
	let error = $state<string | null>(null)
	let hasNext = $state(false)

	let isUserDetailsOpen = $state(false)
	let selectedUserId = $state<string | null>(null)
	let isThreadDetailsOpen = $state(false)
	let selectedThreadId = $state<string | null>(null)

	function openUser(userId: string) {
		selectedUserId = userId
		isUserDetailsOpen = true
	}

	function openThread(threadId: string) {
		selectedThreadId = threadId
		isThreadDetailsOpen = true
	}

	function refresh() {
		refreshToken += 1
	}

	function updateQueryParams(updates: Record<string, string | null>) {
		if (!browser) return
		const url = $page.url
		const params = new URLSearchParams(url.searchParams)
		for (const [key, value] of Object.entries(updates)) {
			if (!value) params.delete(key)
			else params.set(key, value)
		}
		const qs = params.toString()
		goto(qs ? `${url.pathname}?${qs}` : url.pathname, {
			replaceState: true,
			keepFocus: true,
			noScroll: true,
		})
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

		const sp = $page.url.searchParams
		const sort = sp.get(SORT_PARAM)
		const nextSort =
			sort && sortOrder.includes(sort as SortKey) ? (sort as SortKey) : DEFAULT_SORT
		const dir = sp.get(SORT_DIR_PARAM)
		const nextDir = dir === 'asc' || dir === 'desc' ? dir : defaultSortDir(nextSort)
		const user = sp.get(USER_PARAM)
		const nextOwner = user?.trim() ? user : null

		if (sortKey !== nextSort || sortDir !== nextDir || ownerIdFilter !== nextOwner) {
			pageIndex = 0
		}

		sortKey = nextSort
		sortDir = nextDir
		ownerIdFilter = nextOwner
	})

	$effect(() => {
		if (!browser) return

		const skip = pageIndex * limit
		sortKey
		sortDir
		refreshToken

		isLoading = true
		error = null

		ThreadsService.listThreadsThreadsGet(
			ownerIdFilter ?? undefined,
			skip,
			limit,
			sortKey,
			sortDir,
			true
		)
			.then((result) => {
				threads = result
				hasNext = result.length === limit
			})
			.catch((e: any) => {
				error = e?.message ?? 'failed to load threads'
				threads = []
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
			<h2 class="text-2xl font-bold tracking-tight">threads</h2>
			<p class="text-zinc-400">all threads in the system (including hidden).</p>
		</div>
		<div class="flex flex-wrap items-center gap-2">
			<Select value={sortKey} onValueChange={(v: string) => setSort(v as SortKey)}>
				<SelectTrigger class="w-56 rounded-xl">
					<span class="truncate text-left">{sortLabel(sortKey)}</span>
				</SelectTrigger>
				<SelectContent>
					{#each sortOrder as key (key)}
						<SelectItem value={key}>{sortLabel(key)}</SelectItem>
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
			{#if ownerIdFilter}
				<Button
					variant="outline"
					class="rounded-xl"
					onclick={() => clearOwnerFilter()}
					disabled={isLoading}
				>
					owner: {ownerIdFilter} · clear
				</Button>
			{/if}
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
		<div class="rounded-2xl border border-red-900/50 bg-red-900/10 p-4 text-sm text-red-200">
			{error}
		</div>
	{/if}

	<Card class="rounded-2xl border-zinc-800 bg-zinc-900 text-zinc-100">
		<CardHeader class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
			<div>
				<CardTitle>list</CardTitle>
				<CardDescription>
					page {pageIndex + 1} · showing {threads.length}{hasNext ? '+' : ''}
				</CardDescription>
			</div>
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
		</CardHeader>
		<CardContent class="space-y-2">
			{#if isLoading && threads.length === 0}
				<div
					class="flex items-center justify-center rounded-xl border border-zinc-800 bg-zinc-950 p-10"
				>
					<NokodoLoader />
				</div>
			{/if}

			{#if threads.length === 0 && !isLoading}
				<div
					class="rounded-xl border border-dashed border-zinc-800 p-10 text-center text-sm text-zinc-500"
				>
					no threads found
				</div>
			{/if}

			{#each threads as t (t.id)}
				<div
					role="button"
					tabindex="0"
					class="rounded-xl border border-zinc-800 bg-zinc-950 p-4 text-left transition-colors hover:border-zinc-700"
					onclick={() => openThread(t.id)}
					onkeydown={(e) => {
						if (e.key === 'Enter' || e.key === ' ') {
							e.preventDefault()
							openThread(t.id)
						}
					}}
				>
					<div class="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
						<div class="min-w-0">
							<div class="truncate font-medium">
								{t.title ?? '(untitled)'}
							</div>
							<div class="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xs text-zinc-400">
								<div>id: {t.id}</div>
								<div>
									owner:
									{#if t.owner_id}
										<button
											type="button"
											class="ml-1 underline underline-offset-4 hover:text-zinc-200"
											onclick={(e) => {
												e.stopPropagation()
												openUser(t.owner_id)
											}}
										>
											{t.owner_id}
										</button>
									{:else}
										<span class="ml-1">-</span>
									{/if}
								</div>
								<div class={t.is_archived ? 'text-amber-300' : 'text-zinc-500'}>
									archived: {t.is_archived ? 'yes' : 'no'}
								</div>
								<div class={deletedAt(t) ? 'text-red-300' : 'text-zinc-500'}>
									deleted: {deletedAt(t) ? 'yes' : 'no'}
								</div>
								<div class={t.is_temporary ? 'text-amber-300' : 'text-zinc-500'}>
									temporary: {t.is_temporary ? 'yes' : 'no'}
								</div>
							</div>
						</div>
						<div class="shrink-0 text-xs text-zinc-500">
							updated {new Date(t.updated_at).toLocaleString()}
							<div>activity {new Date(t.last_activity_at).toLocaleString()}</div>
						</div>
					</div>
				</div>
			{/each}
		</CardContent>
	</Card>
</div>

<UserDetailsModal bind:open={isUserDetailsOpen} userId={selectedUserId} />

<ThreadDetailsModal bind:open={isThreadDetailsOpen} threadId={selectedThreadId} />
