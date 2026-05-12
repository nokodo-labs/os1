<script lang="ts">
	import { browser } from '$app/environment'
	import { page } from '$app/state'
	import { api, unwrap, type Schemas } from '$lib/api'

	type User = Schemas['User']

	import CreateUserModal from '$lib/components/CreateUserModal.svelte'
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
		Circle,
		CircleX,
		Clock,
		Hash,
		Mail,
		Plus,
		RefreshCw,
		Search,
		Shield,
		User as UserIcon,
	} from '@lucide/svelte'
	import { SvelteURLSearchParams } from 'svelte/reactivity'

	type SortKey =
		| 'updated_at'
		| 'created_at'
		| 'email'
		| 'display_name'
		| 'is_superuser'
		| 'is_active'

	type SortDir = 'asc' | 'desc'

	const sortOptions: Array<{ value: SortKey; label: string }> = [
		{ value: 'updated_at', label: 'updated at' },
		{ value: 'created_at', label: 'created at' },
		{ value: 'email', label: 'email' },
		{ value: 'display_name', label: 'display name' },
		{ value: 'is_superuser', label: 'is superuser' },
		{ value: 'is_active', label: 'is active' },
	]

	function defaultSortDir(sort: SortKey): SortDir {
		if (sort === 'email' || sort === 'display_name') return 'asc'
		if (sort === 'is_active' || sort === 'is_superuser') return 'desc'
		return 'desc'
	}

	let pageIndex = $state(0)
	let limit = $state(50)
	let refreshToken = $state(0)
	const DEFAULT_SORT: SortKey = 'updated_at'
	let sortKey = $state<SortKey>(DEFAULT_SORT)
	let sortDir = $state<SortDir>(defaultSortDir(DEFAULT_SORT))

	const SORT_PARAM = 'sort'
	const SORT_DIR_PARAM = 'sort_dir'

	let users = $state<User[]>([])
	let searchQuery = $state('')
	let serverSearchQuery = $state('')
	let searchTimer: ReturnType<typeof setTimeout> | null = null
	let isLoading = $state(false)
	let hasNext = $state(false)
	let error = $state<string | null>(null)

	let isCreateUserOpen = $state(false)
	let isUserDetailsOpen = $state(false)
	let selectedUserId = $state<string | null>(null)

	function refresh() {
		refreshToken += 1
	}

	function scheduleSearch() {
		pageIndex = 0
		if (searchTimer) clearTimeout(searchTimer)
		searchTimer = setTimeout(() => {
			serverSearchQuery = searchQuery.trim()
		}, 250)
	}

	function openUser(userId: string) {
		selectedUserId = userId
		isUserDetailsOpen = true
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

	$effect(() => {
		if (!browser) return
		const sort = page.url.searchParams.get(SORT_PARAM)
		const next =
			sort && sortOptions.some((o) => o.value === (sort as SortKey))
				? (sort as SortKey)
				: DEFAULT_SORT
		const dir = page.url.searchParams.get(SORT_DIR_PARAM)
		const nextDir = dir === 'asc' || dir === 'desc' ? dir : defaultSortDir(next)

		if (sortKey !== next || sortDir !== nextDir) {
			sortKey = next
			sortDir = nextDir
			pageIndex = 0
		}
	})

	$effect(() => {
		if (!browser) return

		const q = serverSearchQuery || undefined
		const skip = pageIndex * limit + refreshToken * 0

		isLoading = true
		error = null

		api.GET('/v1/users', {
			params: { query: { skip, limit, sort_by: sortKey, sort_dir: sortDir, q } },
		})
			.then((r) => unwrap(r))
			.then((result) => {
				users = result
				hasNext = result.length === limit
			})
			.catch((e: unknown) => {
				error = e instanceof Error ? e.message : 'failed to load users'
				users = []
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
			<h2 class="text-2xl font-bold tracking-tight">users</h2>
			<p class="text-zinc-400">manage users and access.</p>
		</div>
		<div class="flex w-full flex-col gap-2 sm:w-auto sm:flex-row sm:flex-wrap sm:items-center">
			<div class="relative w-full sm:w-auto sm:flex-1">
				<Search
					class="pointer-events-none absolute top-1/2 left-2.5 h-3.5 w-3.5 -translate-y-1/2 text-zinc-500"
				/>
				<Input
					type="search"
					placeholder="search users..."
					bind:value={searchQuery}
					oninput={scheduleSearch}
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
				<Button
					onclick={() => (isCreateUserOpen = true)}
					class="flex-1 gap-2 rounded-xl sm:flex-none"
				>
					<Plus class="h-4 w-4" />
					add user
				</Button>
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
					page {pageIndex + 1}{users.length > 0 ? ` \u00b7 ${users.length} items` : ''}
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
			{#if isLoading && users.length === 0}
				<div
					class="flex min-h-0 flex-1 items-center justify-center rounded-xl border border-zinc-800 bg-zinc-950 p-10"
				>
					<NokodoLoader />
				</div>
			{/if}

			{#if users.length === 0 && !isLoading}
				<div
					class="rounded-xl border border-dashed border-zinc-800 p-10 text-center text-sm text-zinc-500"
				>
					no users found
				</div>
			{/if}

			{#each users as u (u.id)}
				<div
					role="button"
					tabindex="0"
					class="flex w-full items-center justify-between gap-4 rounded-2xl border border-zinc-800 bg-zinc-900 p-4 text-left transition-colors hover:border-zinc-700 hover:bg-zinc-800/50"
					onclick={() => openUser(u.id)}
					onkeydown={(e) => {
						if (e.key === 'Enter' || e.key === ' ') {
							e.preventDefault()
							openUser(u.id)
						}
					}}
				>
					<div class="flex min-w-0 flex-1 items-center gap-4">
						<div
							class="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-orange-500/15 text-orange-400"
						>
							<UserIcon class="h-5 w-5" />
						</div>
						<div class="min-w-0 flex-1 space-y-1">
							<div class="flex flex-wrap items-center gap-2">
								<span class="truncate text-base font-medium text-zinc-100">
									{u.display_name || u.email}
								</span>
								{#if u.is_online}
									<span class="relative flex h-2.5 w-2.5 shrink-0" title="online">
										<span
											class="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75"
										></span>
										<span
											class="relative inline-flex h-2.5 w-2.5 rounded-full bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)]"
										></span>
									</span>
								{:else}
									<div class="h-2 w-2 rounded-full bg-zinc-700/50"></div>
								{/if}
								{#if u.is_superuser}
									<span
										class="inline-flex items-center gap-1 rounded-md bg-amber-500/10 px-2 py-0.5 text-[10px] font-medium tracking-wider text-amber-400 uppercase"
									>
										<Shield class="h-3 w-3" />
										superuser
									</span>
								{/if}
								{#if u.is_active === false}
									<span
										class="inline-flex items-center gap-1 rounded-md bg-red-500/10 px-2 py-0.5 text-[10px] font-medium tracking-wider text-red-400 uppercase"
									>
										<CircleX class="h-3 w-3" />
										inactive
									</span>
								{/if}
							</div>
							<div class="flex flex-wrap items-center gap-3 text-xs text-zinc-500">
								<span class="inline-flex items-center gap-1.5 truncate">
									<Mail class="h-3.5 w-3.5" />
									{u.email}
								</span>
								{#if u.username}
									<span class="inline-flex items-center gap-1">
										@{u.username}
									</span>
								{/if}
								<span
									class="inline-flex items-center gap-1.5 font-mono text-[10px] opacity-50"
								>
									<Hash class="h-3 w-3" />
									{u.id}
								</span>
							</div>
						</div>
						<div class="shrink-0 text-xs text-zinc-500">
							{#if u.is_online}
								<div class="flex items-center gap-1 text-emerald-400">
									<Circle class="h-3 w-3 fill-emerald-400" />
									online now
								</div>
							{:else if u.last_active_at}
								<div class="flex items-center gap-1">
									<Clock class="h-3.5 w-3.5" />
									last active {new Date(u.last_active_at).toLocaleString()}
								</div>
							{/if}
							<div class="mt-1 flex items-center gap-1">
								<Clock class="h-3.5 w-3.5" />
								updated {new Date(u.updated_at).toLocaleString()}
							</div>
							<div class="mt-1 flex items-center gap-1">
								<Clock class="h-3.5 w-3.5" />
								created {new Date(u.created_at).toLocaleString()}
							</div>
						</div>
					</div>
				</div>
			{/each}
		</div>
	</div>
</div>

<CreateUserModal
	bind:open={isCreateUserOpen}
	onCreated={(u) => {
		refresh()
		selectedUserId = u.id
		isUserDetailsOpen = true
	}}
/>

<UserDetailsModal bind:open={isUserDetailsOpen} userId={selectedUserId} />
