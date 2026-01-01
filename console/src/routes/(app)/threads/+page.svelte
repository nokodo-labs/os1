<script lang="ts">
	import { browser } from '$app/environment'
	import { goto } from '$app/navigation'
	import { page } from '$app/stores'
	import { ThreadsService, type Thread } from '$lib/api'
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

	type SortKey = 'updated_at' | 'last_activity_at' | 'created_at' | 'title' | 'owner_id'

	const sortOrder: SortKey[] = [
		'updated_at',
		'last_activity_at',
		'created_at',
		'title',
		'owner_id',
	]

	function sortLabel(key: SortKey) {
		switch (key) {
			case 'updated_at':
				return 'latest updated'
			case 'last_activity_at':
				return 'latest activity'
			case 'created_at':
				return 'newest created'
			case 'title':
				return 'title (a→z)'
			case 'owner_id':
				return 'owner id (a→z)'
		}
	}

	function parseDate(value: string | null | undefined) {
		if (!value) return 0
		const date = new Date(value).getTime()
		return Number.isFinite(date) ? date : 0
	}

	function sortThreads(list: Thread[], key: SortKey) {
		const sorted = [...list]
		sorted.sort((a, b) => {
			if (key === 'title') {
				return (a.title ?? '').localeCompare(b.title ?? '')
			}
			if (key === 'owner_id') {
				return (a.owner_id ?? '').localeCompare(b.owner_id ?? '')
			}

			const aValue = parseDate(a[key])
			const bValue = parseDate(b[key])
			return bValue - aValue
		})
		return sorted
	}

	const DEFAULT_SORT: SortKey = 'updated_at'
	const SORT_PARAM = 'sort'
	const USER_PARAM = 'user'

	let sortKey = $state<SortKey>(DEFAULT_SORT)
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
		pageIndex = 0
		updateQueryParams({ [SORT_PARAM]: next })
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
		const user = sp.get(USER_PARAM)
		const nextOwner = user?.trim() ? user : null

		if (sortKey !== nextSort || ownerIdFilter !== nextOwner) {
			pageIndex = 0
		}

		sortKey = nextSort
		ownerIdFilter = nextOwner
	})

	$effect(() => {
		if (!browser) return

		const skip = pageIndex * limit
		sortKey
		refreshToken

		isLoading = true
		error = null

		ThreadsService.listThreadsThreadsGet(ownerIdFilter ?? undefined, skip, limit, true)
			.then((result) => {
				threads = sortThreads(result, sortKey)
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
										<span class="ml-1">—</span>
									{/if}
								</div>
								{#if t.is_archived}
									<div class="text-amber-300">archived</div>
								{/if}
								{#if t.is_temporary}
									<div class="text-amber-300">temporary</div>
								{/if}
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
