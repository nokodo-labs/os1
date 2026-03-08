<script lang="ts">
	import { browser } from '$app/environment'
	import { page } from '$app/state'
	import { api, unwrap, type Schemas } from '$lib/api'

	type Group = Schemas['Group']

	import GroupDetailsModal from '$lib/components/GroupDetailsModal.svelte'
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
	import { Input } from '$lib/components/ui/input'
	import { Select, SelectContent, SelectItem, SelectTrigger } from '$lib/components/ui/select'
	import { ArrowDown, ArrowUp, Clock, Hash, Search, User, Users } from '@lucide/svelte'
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

<div class="flex min-h-0 flex-1 flex-col gap-6">
	<div class="flex shrink-0 flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
		<div>
			<h2 class="text-2xl font-bold tracking-tight">groups</h2>
			<p class="text-zinc-400">all groups in the system.</p>
		</div>
		<div class="flex flex-wrap items-center gap-2">
			<div class="relative">
				<Search
					class="pointer-events-none absolute top-1/2 left-2.5 h-3.5 w-3.5 -translate-y-1/2 text-zinc-500"
				/>
				<Input
					type="search"
					placeholder="search groups..."
					bind:value={searchQuery}
					class="h-9 w-50 pl-8 lg:w-75"
				/>
			</div>
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
			{#if memberFilter}
				<Button
					variant="outline"
					class="rounded-xl"
					onclick={() => clearMemberFilter()}
					disabled={isLoading}
				>
					member: {memberFilter} · clear
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
		<div
			class="shrink-0 rounded-2xl border border-red-900/50 bg-red-900/10 p-4 text-sm text-red-200"
		>
			{error}
		</div>
	{/if}

	<Card
		class="flex min-h-0 flex-1 flex-col rounded-2xl border-zinc-800 bg-zinc-900 text-zinc-100"
	>
		<CardHeader
			class="flex shrink-0 flex-col gap-3 sm:flex-row sm:items-center sm:justify-between"
		>
			<div>
				<CardTitle>list</CardTitle>
				<CardDescription>
					page {pageIndex + 1} · showing {filteredGroups.length}{hasNext ? '+' : ''}
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
		<CardContent class="flex min-h-0 flex-1 flex-col space-y-2 overflow-y-auto">
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
					class="rounded-xl border border-zinc-800 bg-zinc-950 p-4 transition-colors hover:border-zinc-700"
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
					<div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
						<div class="min-w-0 flex-1 space-y-2">
							<div class="truncate font-medium">{g.name}</div>
							{#if g.description}
								<div class="line-clamp-1 text-sm text-zinc-400">
									{g.description}
								</div>
							{/if}
							<div class="flex flex-wrap items-center gap-2 text-xs text-zinc-400">
								<span
									class="inline-flex items-center gap-1 rounded-md bg-zinc-900 px-2 py-0.5"
								>
									<Hash class="h-3.5 w-3.5" />
									{g.id}
								</span>
								<span
									class="inline-flex items-center gap-1 rounded-md bg-zinc-900 px-2 py-0.5"
								>
									<User class="h-3.5 w-3.5" />
									<button
										type="button"
										class="underline underline-offset-4 hover:text-zinc-200"
										onclick={() => openUser(g.owner_id)}
									>
										{g.owner_id}
									</button>
								</span>
								<span
									class="inline-flex items-center gap-1 rounded-md bg-zinc-900 px-2 py-0.5"
								>
									<Users class="h-3.5 w-3.5" />
									{g.memberships.length}
									{g.memberships.length === 1 ? 'member' : 'members'}
								</span>
							</div>
						</div>
						<div class="shrink-0 text-xs text-zinc-500">
							<div class="flex items-center gap-1">
								<Clock class="h-3.5 w-3.5" />
								updated {new Date(g.updated_at).toLocaleString()}
							</div>
							<div class="mt-1 flex items-center gap-1">
								<Clock class="h-3.5 w-3.5" />
								created {new Date(g.created_at).toLocaleString()}
							</div>
						</div>
					</div>
				</div>
			{/each}
		</CardContent>
	</Card>
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
