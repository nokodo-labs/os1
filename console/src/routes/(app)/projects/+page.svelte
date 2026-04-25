<script lang="ts">
	import { browser } from '$app/environment'
	import { page } from '$app/state'
	import { api, unwrap, type Schemas } from '$lib/api'

	type Project = Schemas['Project']

	import NokodoLoader from '$lib/components/NokodoLoader.svelte'
	import ProjectDetailsModal from '$lib/components/ProjectDetailsModal.svelte'
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
		FolderKanban,
		Hash,
		MessageSquare,
		RefreshCw,
		Search,
		User,
		X,
	} from '@lucide/svelte'
	import { SvelteURLSearchParams } from 'svelte/reactivity'

	type SortKey = 'updated_at' | 'created_at' | 'name'
	type SortDir = 'asc' | 'desc'

	const sortOptions: { value: SortKey; label: string }[] = [
		{ value: 'updated_at', label: 'last updated' },
		{ value: 'created_at', label: 'created' },
		{ value: 'name', label: 'name' },
	]

	function defaultSortDir(key: SortKey): SortDir {
		return key === 'name' ? 'asc' : 'desc'
	}

	const SORT_PARAM = 'sort'
	const SORT_DIR_PARAM = 'dir'
	const USER_PARAM = 'user'
	const DEFAULT_SORT: SortKey = 'updated_at'

	let sortKey = $state<SortKey>(DEFAULT_SORT)
	let sortDir = $state<SortDir>('desc')
	let ownerIdFilter = $state<string | null>(null)
	let pageIndex = $state(0)
	const limit = 50
	let refreshToken = $state(0)

	let projects = $state<Project[]>([])
	let isLoading = $state(false)
	let error = $state<string | null>(null)
	let hasNext = $state(false)

	let searchQuery = $state('')
	let searchResults = $state<Project[]>([])
	let isSearching = $state(false)
	let searchError = $state<string | null>(null)
	let _searchTimer: ReturnType<typeof setTimeout> | undefined

	let isUserDetailsOpen = $state(false)
	let selectedUserId = $state<string | null>(null)
	let isProjectDetailsOpen = $state(false)
	let selectedProjectId = $state<string | null>(null)

	function openUser(userId: string) {
		selectedUserId = userId
		isUserDetailsOpen = true
	}

	function openProject(projectId: string) {
		selectedProjectId = projectId
		isProjectDetailsOpen = true
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
			sort && sortOptions.some((o) => o.value === sort) ? (sort as SortKey) : DEFAULT_SORT
		const dir = sp.get(SORT_DIR_PARAM)
		const nextDir = dir === 'asc' || dir === 'desc' ? dir : defaultSortDir(nextSort)
		const user = sp.get(USER_PARAM)

		if (sortKey !== nextSort || sortDir !== nextDir || ownerIdFilter !== user) {
			pageIndex = 0
		}

		sortKey = nextSort
		sortDir = nextDir
		ownerIdFilter = user?.trim() || null
	})

	$effect(() => {
		if (!browser) return

		const skip = pageIndex * limit + refreshToken * 0

		isLoading = true
		error = null

		api.GET('/v1/projects', {
			params: {
				query: {
					skip,
					limit,
					sort_by: sortKey,
					sort_dir: sortDir,
				},
			},
		})
			.then((r) => unwrap(r))
			.then((result) => {
				projects = result
				hasNext = result.length === limit
			})
			.catch((e: unknown) => {
				error = e instanceof Error ? e.message : 'failed to load projects'
				projects = []
				hasNext = false
			})
			.finally(() => {
				isLoading = false
			})
	})

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
			const lower = q.toLowerCase()
			searchResults = projects.filter(
				(p) =>
					p.name.toLowerCase().includes(lower) ||
					(p.description ?? '').toLowerCase().includes(lower)
			)
			isSearching = false
		}, 200)
		return () => clearTimeout(_searchTimer)
	})
</script>

<div class="flex flex-col gap-6">
	<div class="flex shrink-0 flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
		<div>
			<h2 class="text-2xl font-bold tracking-tight">projects</h2>
			<p class="text-zinc-400">all projects in the system.</p>
		</div>
		<div class="flex w-full flex-col gap-2 sm:w-auto sm:flex-row sm:flex-wrap sm:items-center">
			<div class="relative w-full sm:w-auto sm:flex-1">
				<Search
					class="pointer-events-none absolute top-1/2 left-2.5 h-3.5 w-3.5 -translate-y-1/2 text-zinc-500"
				/>
				<Input
					type="search"
					placeholder="search projects..."
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
					page {pageIndex + 1}{projects.length > 0
						? ` \u00b7 ${projects.length} items`
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
					{#each searchResults as p (p.id)}
						<div
							class="rounded-xl border border-zinc-800 bg-zinc-950 p-4 transition-colors hover:border-zinc-700"
						>
							<div
								class="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between"
							>
								<div class="min-w-0 flex-1 space-y-1">
									<div class="flex items-center gap-2">
										<FolderKanban class="h-4 w-4 text-yellow-400" />
										<span class="truncate font-medium">{p.name}</span>
									</div>
									{#if p.description}
										<div class="line-clamp-1 text-sm text-zinc-400">
											{p.description}
										</div>
									{/if}
									<div class="flex items-center gap-2 text-xs text-zinc-400">
										<span
											class="inline-flex items-center gap-1 rounded-md bg-zinc-900 px-2 py-0.5"
										>
											<Hash class="h-3.5 w-3.5" />
											{p.id}
										</span>
									</div>
								</div>
							</div>
						</div>
					{/each}
				{/if}
			{:else}
				{#if isLoading && projects.length === 0}
					<div
						class="flex min-h-0 flex-1 items-center justify-center rounded-xl border border-zinc-800 bg-zinc-950 p-10"
					>
						<NokodoLoader />
					</div>
				{/if}

				{#if projects.length === 0 && !isLoading}
					<div
						class="rounded-xl border border-dashed border-zinc-800 p-10 text-center text-sm text-zinc-500"
					>
						no projects found
					</div>
				{/if}

				{#each projects as p (p.id)}
					<!-- svelte-ignore a11y_click_events_have_key_events -->
					<!-- svelte-ignore a11y_no_static_element_interactions -->
					<div
						class="flex w-full cursor-pointer items-center justify-between gap-4 rounded-2xl border border-zinc-800 bg-zinc-900 p-4 text-left transition-colors hover:border-zinc-700 hover:bg-zinc-800/50"
						onclick={() => openProject(p.id)}
					>
						<div class="flex min-w-0 flex-1 items-center gap-4">
							<div
								class="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-yellow-500/15 text-yellow-400"
							>
								<FolderKanban class="h-5 w-5" />
							</div>
							<div class="min-w-0 flex-1 space-y-1">
								<div class="flex flex-wrap items-center gap-2">
									<span class="truncate text-base font-medium text-zinc-100"
										>{p.name}</span
									>
									{#if (p.thread_ids ?? []).length > 0}
										<span
											class="inline-flex items-center gap-1 rounded-md bg-emerald-500/10 px-2 py-0.5 text-[10px] font-medium tracking-wider text-emerald-400"
										>
											<MessageSquare class="h-3 w-3" />
											{(p.thread_ids ?? []).length} thread{(
												p.thread_ids ?? []
											).length === 1
												? ''
												: 's'}
										</span>
									{/if}
								</div>
								{#if p.description}
									<div class="line-clamp-2 text-sm text-zinc-400">
										{p.description}
									</div>
								{/if}
								<div
									class="flex flex-wrap items-center gap-3 text-xs text-zinc-500"
								>
									<span
										class="inline-flex items-center gap-1.5 font-mono text-[10px] opacity-50"
									>
										<Hash class="h-3 w-3" />
										{p.id}
									</span>
									<span class="inline-flex items-center gap-1">
										<User class="h-3.5 w-3.5" />
										<button
											type="button"
											class="underline underline-offset-4 hover:text-zinc-200"
											onclick={(e) => {
												e.stopPropagation()
												openUser(p.owner_id)
											}}
										>
											{p.owner_id}
										</button>
									</span>
								</div>
							</div>
						</div>
						<div class="shrink-0 text-xs text-zinc-500">
							<div class="flex items-center gap-1.5 whitespace-nowrap">
								<Clock class="h-3.5 w-3.5" />
								{new Date(p.updated_at).toLocaleString()}
							</div>
						</div>
					</div>
				{/each}
			{/if}
		</div>
	</div>
</div>

<UserDetailsModal bind:open={isUserDetailsOpen} userId={selectedUserId} />
<ProjectDetailsModal
	bind:open={isProjectDetailsOpen}
	projectId={selectedProjectId}
	onViewUser={(userId) => openUser(userId)}
	onUpdated={(updated) => {
		projects = projects.map((p) => (p.id === updated.id ? updated : p))
	}}
	onDeleted={(id) => {
		projects = projects.filter((p) => p.id !== id)
		isProjectDetailsOpen = false
	}}
/>
