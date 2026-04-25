<script lang="ts">
	import { browser } from '$app/environment'
	import { page } from '$app/state'
	import { api, unwrap, type Schemas } from '$lib/api'

	type Group = Schemas['Group']

	import GroupDetailsModal from '$lib/components/GroupDetailsModal.svelte'
	import NokodoLoader from '$lib/components/NokodoLoader.svelte'
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
		Hash,
		RefreshCw,
		Search,
		User,
		Users,
		X,
	} from '@lucide/svelte'
	import { SvelteURLSearchParams } from 'svelte/reactivity'

	type SortKey = 'updated_at' | 'created_at' | 'name'
	type SortDir = 'asc' | 'desc'

	const sortOptions: Array<{ value: SortKey; label: string }> = [
		{ value: 'updated_at', label: 'updated at' },
		{ value: 'created_at', label: 'created at' },
		{ value: 'name', label: 'name' },
	]

	function defaultSortDir(sort: SortKey): SortDir {
		if (sort === 'name') return 'asc'
		return 'desc'
	}

	const DEFAULT_SORT: SortKey = 'updated_at'
	const SORT_PARAM = 'sort'
	const SORT_DIR_PARAM = 'sort_dir'
	const USER_PARAM = 'user'

	let sortKey = $state<SortKey>(DEFAULT_SORT)
	let sortDir = $state<SortDir>(defaultSortDir(DEFAULT_SORT))
	let memberFilter = $state<string | null>(null)
	let pageIndex = $state(0)
	let limit = $state(50)
	let refreshToken = $state(0)

	let groups = $state<Group[]>([])
	let searchQuery = $state('')
	let isLoading = $state(false)
	let hasNext = $state(false)
	let error = $state<string | null>(null)

	let isUserDetailsOpen = $state(false)
	let selectedUserId = $state<string | null>(null)

	let isGroupDetailsOpen = $state(false)
	let selectedGroupId = $state<string | null>(null)

	const filteredGroups = $derived(
		groups.filter((g) => {
			const q = searchQuery.toLowerCase()
			return (
				g.name.toLowerCase().includes(q) ||
				(g.description ?? '').toLowerCase().includes(q) ||
				g.id.toLowerCase().includes(q)
			)
		})
	)

	function openGroup(groupId: string) {
		selectedGroupId = groupId
		isGroupDetailsOpen = true
	}

	function openUser(userId: string) {
		selectedUserId = userId
		isUserDetailsOpen = true
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

	function clearMemberFilter() {
		memberFilter = null
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
		const nextMember = user?.trim() || null

		if (sortKey !== nextSort || sortDir !== nextDir || memberFilter !== nextMember) {
			pageIndex = 0
		}

		sortKey = nextSort
		sortDir = nextDir
		memberFilter = nextMember
	})

	$effect(() => {
		if (!browser) return

		const skip = pageIndex * limit + refreshToken * 0

		isLoading = true
		error = null

		api.GET('/v1/groups', {
			params: {
				query: {
					user_id: memberFilter ?? undefined,
					skip,
					limit,
					sort_by: sortKey,
					sort_dir: sortDir,
				},
			},
		})
			.then((r) => unwrap(r))
			.then((result) => {
				groups = result
				hasNext = result.length === limit
			})
			.catch((e: unknown) => {
				error = e instanceof Error ? e.message : 'failed to load groups'
				groups = []
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
			<h2 class="text-2xl font-bold tracking-tight">groups</h2>
			<p class="text-zinc-400">all groups in the system.</p>
		</div>
		<div class="flex w-full flex-col gap-2 sm:w-auto sm:flex-row sm:flex-wrap sm:items-center">
			<div class="relative w-full sm:w-auto sm:flex-1">
				<Search
					class="pointer-events-none absolute top-1/2 left-2.5 h-3.5 w-3.5 -translate-y-1/2 text-zinc-500"
				/>
				<Input
					type="search"
					placeholder="search groups..."
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
				{#if memberFilter}
					<Button
						variant="outline"
						class="flex-1 rounded-xl sm:flex-none"
						onclick={() => clearMemberFilter()}
						disabled={isLoading}
					>
						<X class="mr-2 h-4 w-4" />
						member: {memberFilter}
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
					page {pageIndex + 1}{groups.length > 0 ? ` \u00b7 ${groups.length} items` : ''}
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
			{#if isLoading && groups.length === 0}
				<div
					class="flex min-h-0 flex-1 items-center justify-center rounded-xl border border-zinc-800 bg-zinc-950 p-10"
				>
					<NokodoLoader />
				</div>
			{/if}

			{#if filteredGroups.length === 0 && !isLoading}
				<div
					class="rounded-xl border border-dashed border-zinc-800 p-10 text-center text-sm text-zinc-500"
				>
					no groups found
				</div>
			{/if}

			{#each filteredGroups as g (g.id)}
				<div
					role="button"
					tabindex="0"
					class="flex w-full cursor-pointer items-center justify-between gap-4 rounded-2xl border border-zinc-800 bg-zinc-900 p-4 text-left transition-colors hover:border-zinc-700 hover:bg-zinc-800/50"
					onclick={(e) => {
						if (
							(e.target as HTMLElement).closest('button:not([data-row-click])') ==
							null
						)
							openGroup(g.id)
					}}
					onkeydown={(e) => {
						if (e.key === 'Enter' || e.key === ' ') {
							e.preventDefault()
							openGroup(g.id)
						}
					}}
				>
					<div class="flex min-w-0 flex-1 items-center gap-4">
						<div
							class="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-amber-400/15 text-amber-300"
						>
							<Users class="h-5 w-5" />
						</div>
						<div class="min-w-0 flex-1 space-y-1">
							<div class="flex flex-wrap items-center gap-2">
								<span class="truncate text-base font-medium text-zinc-100"
									>{g.name}</span
								>
							</div>
							{#if g.description}
								<div class="line-clamp-1 text-sm text-zinc-400">
									{g.description}
								</div>
							{/if}
							<div class="flex flex-wrap items-center gap-3 text-xs text-zinc-500">
								<span
									class="inline-flex items-center gap-1.5 font-mono text-[10px] opacity-50"
								>
									<Hash class="h-3 w-3" />
									{g.id}
								</span>
								<span class="inline-flex items-center gap-1">
									<User class="h-3.5 w-3.5" />
									<button
										type="button"
										class="underline underline-offset-4 hover:text-zinc-200"
										onclick={(e) => {
											e.stopPropagation()
											openUser(g.owner_id)
										}}
									>
										{g.owner_id}
									</button>
								</span>
								<span
									class="inline-flex items-center gap-1 rounded-md bg-zinc-800 px-2 py-0.5 text-[10px] font-medium tracking-wider text-zinc-300 uppercase"
								>
									<Users class="h-3 w-3" />
									{g.memberships.length}
									{g.memberships.length === 1 ? 'member' : 'members'}
								</span>
							</div>
						</div>
					</div>
					<div class="shrink-0 text-xs text-zinc-500">
						<div class="flex items-center gap-1.5 whitespace-nowrap">
							<Clock class="h-3.5 w-3.5" />
							{new Date(g.updated_at).toLocaleString()}
						</div>
						<div class="mt-1 flex items-center gap-1.5 whitespace-nowrap">
							<Clock class="h-3.5 w-3.5" />
							{new Date(g.created_at).toLocaleString()}
						</div>
					</div>
				</div>
			{/each}
		</div>
	</div>
</div>

<UserDetailsModal bind:open={isUserDetailsOpen} userId={selectedUserId} />

<GroupDetailsModal
	bind:open={isGroupDetailsOpen}
	groupId={selectedGroupId}
	onDeleted={() => {
		groups = groups.filter((g) => g.id !== selectedGroupId)
		selectedGroupId = null
	}}
	onUpdated={(updated) => {
		groups = groups.map((g) =>
			g.id === updated.id ? { ...g, name: updated.name, description: updated.description } : g
		)
	}}
/>
