<script lang="ts">
	import { browser } from '$app/environment'
	import { replaceState } from '$app/navigation'
	import { page } from '$app/state'
	import { api, unwrap, type Schemas } from '$lib/api'

	type Role = Schemas['Role']

	import CreateRoleModal from '$lib/components/CreateRoleModal.svelte'
	import NokodoLoader from '$lib/components/NokodoLoader.svelte'
	import RoleDetailsModal from '$lib/components/RoleDetailsModal.svelte'
	import { Button } from '$lib/components/ui/button'
	import {
		Card,
		CardContent,
		CardDescription,
		CardHeader,
		CardTitle,
	} from '$lib/components/ui/card'
	import { Select, SelectContent, SelectItem, SelectTrigger } from '$lib/components/ui/select'
	import { ArrowDown, ArrowUp, Clock, Hash, ListOrdered, Plus, Shield } from '@lucide/svelte'
	import { SvelteURLSearchParams } from 'svelte/reactivity'

	type SortKey = 'priority' | 'name' | 'created_at' | 'updated_at'
	type SortDir = 'asc' | 'desc'

	const sortOptions: Array<{ value: SortKey; label: string }> = [
		{ value: 'priority', label: 'priority' },
		{ value: 'name', label: 'name' },
		{ value: 'created_at', label: 'created at' },
		{ value: 'updated_at', label: 'updated at' },
	]

	function defaultSortDir(sort: SortKey): SortDir {
		if (sort === 'name') return 'asc'
		return 'desc'
	}

	const DEFAULT_SORT: SortKey = 'priority'
	const SORT_PARAM = 'sort'
	const SORT_DIR_PARAM = 'sort_dir'
	const USER_PARAM = 'user'

	let sortKey = $state<SortKey>(DEFAULT_SORT)
	let sortDir = $state<SortDir>(defaultSortDir(DEFAULT_SORT))
	let userIdFilter = $state<string | null>(null)
	let pageIndex = $state(0)
	let limit = $state(50)
	let refreshToken = $state(0)

	let roles = $state<Role[]>([])
	let isLoading = $state(false)
	let isReordering = $state(false)
	let error = $state<string | null>(null)
	let hasNext = $state(false)

	let isCreateOpen = $state(false)
	let isDetailsOpen = $state(false)
	let selectedRoleId = $state<string | null>(null)

	function replaceUrl(target: string) {
		if (!browser) return
		replaceState(target, {})
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
		updateQueryParams({ [USER_PARAM]: null })
	}

	function refresh() {
		refreshToken += 1
	}

	function openRole(roleId: string) {
		selectedRoleId = roleId
		isDetailsOpen = true
	}

	async function moveRole(roleId: string, direction: 'up' | 'down') {
		if (sortKey !== 'priority') return
		const index = roles.findIndex((r) => r.id === roleId)
		if (index === -1) return
		const targetIndex = direction === 'up' ? index - 1 : index + 1
		if (targetIndex < 0 || targetIndex >= roles.length) return

		const current = roles[index]
		const target = roles[targetIndex]
		const currentPriority = current.priority ?? 0
		const targetPriority = target.priority ?? 0

		isReordering = true
		error = null
		try {
			const [currentResult, targetResult] = await Promise.all([
				api.PATCH('/v1/roles/{role_id}', {
					params: { path: { role_id: current.id } },
					body: { priority: targetPriority },
				}),
				api.PATCH('/v1/roles/{role_id}', {
					params: { path: { role_id: target.id } },
					body: { priority: currentPriority },
				}),
			])
			unwrap(currentResult)
			unwrap(targetResult)

			const next = [...roles]
			next[index] = { ...current, priority: targetPriority }
			next[targetIndex] = { ...target, priority: currentPriority }
			roles = next
		} catch (e) {
			error = e instanceof Error ? e.message : 'failed to reorder roles'
		} finally {
			isReordering = false
		}
	}

	// Sync from URL params
	$effect(() => {
		if (!browser) return

		const sp = page.url.searchParams
		const sort = sp.get(SORT_PARAM)
		const nextSort =
			sort && sortOptions.some((o) => o.value === sort) ? (sort as SortKey) : DEFAULT_SORT
		const dir = sp.get(SORT_DIR_PARAM)
		const nextDir = dir === 'asc' || dir === 'desc' ? dir : defaultSortDir(nextSort)
		const user = sp.get(USER_PARAM)
		const stateUser =
			typeof (page.state as { user?: unknown } | undefined)?.user === 'string'
				? ((page.state as { user?: unknown }).user as string)
				: null
		const nextUser = user?.trim() ? user : stateUser?.trim() ? stateUser : null

		if (sortKey !== nextSort || sortDir !== nextDir || userIdFilter !== nextUser) {
			pageIndex = 0
		}

		sortKey = nextSort
		sortDir = nextDir
		userIdFilter = nextUser
		if (!user && nextUser) {
			updateQueryParams({ [USER_PARAM]: nextUser })
		}
	})

	// Fetch roles
	$effect(() => {
		if (!browser) return

		const skip = pageIndex * limit + refreshToken * 0

		isLoading = true
		error = null

		api.GET('/v1/roles', {
			params: {
				query: {
					skip,
					limit,
					sort_by: sortKey,
					sort_dir: sortDir,
					user_id: userIdFilter ?? undefined,
				},
			},
		})
			.then((r) => unwrap(r))
			.then((result) => {
				roles = result
				hasNext = result.length === limit
			})
			.catch((e: unknown) => {
				error = e instanceof Error ? e.message : 'failed to load roles'
				roles = []
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
			<h2 class="text-2xl font-bold tracking-tight">roles</h2>
			<p class="text-zinc-400">manage roles and default permissions.</p>
		</div>
		<div class="flex flex-wrap items-center gap-2">
			<Button class="gap-2 rounded-xl" onclick={() => (isCreateOpen = true)}>
				<Plus class="h-4 w-4" />
				new role
			</Button>
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
			{#if userIdFilter}
				<Button
					variant="outline"
					class="rounded-xl"
					onclick={() => clearUserFilter()}
					disabled={isLoading}
				>
					user: {userIdFilter} · clear
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
					page {pageIndex + 1} · showing {roles.length}{hasNext ? '+' : ''}
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
			{#if isLoading && roles.length === 0}
				<div
					class="flex min-h-0 flex-1 items-center justify-center rounded-xl border border-zinc-800 bg-zinc-950 p-10"
				>
					<NokodoLoader />
				</div>
			{/if}

			{#if roles.length === 0 && !isLoading}
				<div
					class="rounded-xl border border-dashed border-zinc-800 p-10 text-center text-sm text-zinc-500"
				>
					no roles found
				</div>
			{/if}

			{#each roles as role, index (role.id)}
				<div
					role="button"
					tabindex="0"
					class="rounded-xl border border-zinc-800 bg-zinc-950 p-4 text-left transition-colors hover:border-zinc-700"
					onclick={() => openRole(role.id)}
					onkeydown={(e) => {
						if (e.key === 'Enter' || e.key === ' ') {
							e.preventDefault()
							openRole(role.id)
						}
					}}
				>
					<div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
						<div class="min-w-0 flex-1 space-y-2">
							<div class="flex items-center gap-2">
								<Shield class="h-4 w-4 text-zinc-500" />
								<span class="truncate font-medium">{role.name}</span>
							</div>
							{#if role.description}
								<div class="line-clamp-1 text-sm text-zinc-400">
									{role.description}
								</div>
							{/if}
							<div class="flex flex-wrap items-center gap-2 text-xs text-zinc-400">
								<span
									class="inline-flex items-center gap-1 rounded-md bg-zinc-900 px-2 py-0.5"
								>
									<Hash class="h-3.5 w-3.5" />
									{role.id}
								</span>
								<span
									class="inline-flex items-center gap-1 rounded-md bg-zinc-900 px-2 py-0.5"
								>
									<ListOrdered class="h-3.5 w-3.5" />
									priority {role.priority ?? 0}
								</span>
							</div>
						</div>
						<div class="flex items-start gap-3">
							{#if sortKey === 'priority'}
								<div class="flex flex-col gap-1">
									<Button
										variant="outline"
										class="h-7 w-7 rounded-lg p-0"
										onclick={(e) => {
											e.stopPropagation()
											moveRole(role.id, 'up')
										}}
										disabled={isReordering || index === 0}
										aria-label="move role up"
										title="move role up"
									>
										<ArrowUp class="h-3.5 w-3.5" />
									</Button>
									<Button
										variant="outline"
										class="h-7 w-7 rounded-lg p-0"
										onclick={(e) => {
											e.stopPropagation()
											moveRole(role.id, 'down')
										}}
										disabled={isReordering || index === roles.length - 1}
										aria-label="move role down"
										title="move role down"
									>
										<ArrowDown class="h-3.5 w-3.5" />
									</Button>
								</div>
							{/if}
							<div class="shrink-0 text-xs text-zinc-500">
								<div class="flex items-center gap-1">
									<Clock class="h-3.5 w-3.5" />
									updated {new Date(role.updated_at).toLocaleString()}
								</div>
								<div class="mt-1 flex items-center gap-1">
									<Clock class="h-3.5 w-3.5" />
									created {new Date(role.created_at).toLocaleString()}
								</div>
							</div>
						</div>
					</div>
				</div>
			{/each}
		</CardContent>
	</Card>
</div>

<CreateRoleModal
	bind:open={isCreateOpen}
	onCreated={(role) => {
		refresh()
		selectedRoleId = role.id
		isDetailsOpen = true
	}}
/>

<RoleDetailsModal
	bind:open={isDetailsOpen}
	roleId={selectedRoleId}
	onUpdated={() => refresh()}
	onDeleted={() => refresh()}
/>
