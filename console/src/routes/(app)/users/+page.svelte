<script lang="ts">
	import { browser } from '$app/environment'
	import { replaceState } from '$app/navigation'
	import { page } from '$app/state'
	import { UsersService, type User } from '$lib/api'
	import CreateUserModal from '$lib/components/CreateUserModal.svelte'
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
	import { ArrowDown, ArrowUp, Plus } from '@lucide/svelte'
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
	let isLoading = $state(false)
	let hasNext = $state(false)
	let error = $state<string | null>(null)

	const filteredUsers = $derived(
		users.filter((u) => {
			const q = searchQuery.toLowerCase()
			return (
				u.email.toLowerCase().includes(q) ||
				(u.display_name && u.display_name.toLowerCase().includes(q)) ||
				u.id.toLowerCase().includes(q)
			)
		})
	)

	let isCreateUserOpen = $state(false)
	let isUserDetailsOpen = $state(false)
	let selectedUserId = $state<string | null>(null)

	function refresh() {
		refreshToken += 1
	}

	function openUser(userId: string) {
		selectedUserId = userId
		isUserDetailsOpen = true
	}

	function replaceUrl(target: string) {
		if (!browser) return
		window.history.replaceState(window.history.state, '', target)
		replaceState('', {})
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

		const skip = pageIndex * limit + refreshToken * 0

		isLoading = true
		error = null

		UsersService.readUsersUsersGet(skip, limit, sortKey, sortDir)
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

<div class="space-y-6">
	<div class="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
		<div>
			<h2 class="text-2xl font-bold tracking-tight">users</h2>
			<p class="text-zinc-400">manage users and access.</p>
		</div>
		<div class="flex items-center gap-2">
			<Input
				type="search"
				placeholder="search users..."
				bind:value={searchQuery}
				class="h-9 w-[200px] lg:w-[300px]"
			/>
			<Button class="gap-2 rounded-xl" onclick={() => (isCreateUserOpen = true)}>
				<Plus class="h-4 w-4" />
				add user
			</Button>
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
					page {pageIndex + 1} · showing {filteredUsers.length}{hasNext ? '+' : ''}
				</CardDescription>
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
			{#if isLoading && users.length === 0}
				<div
					class="flex items-center justify-center rounded-xl border border-zinc-800 bg-zinc-950 p-10"
				>
					<NokodoLoader />
				</div>
			{/if}

			{#if filteredUsers.length === 0 && !isLoading}
				<div
					class="rounded-xl border border-dashed border-zinc-800 p-10 text-center text-sm text-zinc-500"
				>
					no users found
				</div>
			{/if}

			{#each filteredUsers as u (u.id)}
				<div
					role="button"
					tabindex="0"
					class="w-full rounded-xl border border-zinc-800 bg-zinc-950 p-4 text-left transition-colors hover:border-zinc-700"
					onclick={() => openUser(u.id)}
					onkeydown={(e) => {
						if (e.key === 'Enter' || e.key === ' ') {
							e.preventDefault()
							openUser(u.id)
						}
					}}
				>
					<div class="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
						<div class="min-w-0">
							<div class="truncate font-medium">{u.email}</div>
							<div class="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xs text-zinc-400">
								<div>id: {u.id}</div>
								{#if u.display_name}
									<div>name: {u.display_name}</div>
								{/if}
								{#if u.is_active === false}
									<div class="text-amber-300">inactive</div>
								{/if}
								{#if u.is_superuser}
									<div class="text-amber-300">superuser</div>
								{/if}
							</div>
						</div>
						<div class="flex shrink-0 flex-col items-end gap-2">
							<div class="text-xs text-zinc-500">
								updated {new Date(u.updated_at).toLocaleString()}
								<div>created {new Date(u.created_at).toLocaleString()}</div>
							</div>
						</div>
					</div>
				</div>
			{/each}
		</CardContent>
	</Card>
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
