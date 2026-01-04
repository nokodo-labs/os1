<script lang="ts">
	import { browser } from '$app/environment'
	import { goto } from '$app/navigation'
	import { page } from '$app/stores'
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
	import { Select, SelectContent, SelectItem, SelectTrigger } from '$lib/components/ui/select'
	import { Plus } from '@lucide/svelte'

	type SortKey =
		| 'updated_at'
		| 'created_at'
		| 'email'
		| 'display_name'
		| 'is_superuser'
		| 'is_active'

	const sortOptions: Array<{ value: SortKey; label: string }> = [
		{ value: 'updated_at', label: 'latest updated' },
		{ value: 'created_at', label: 'newest created' },
		{ value: 'email', label: 'email (a→z)' },
		{ value: 'display_name', label: 'display name (a→z)' },
		{ value: 'is_superuser', label: 'superuser first' },
		{ value: 'is_active', label: 'active first' },
	]

	function parseDate(value: string | null | undefined) {
		if (!value) return 0
		const date = new Date(value).getTime()
		return Number.isFinite(date) ? date : 0
	}

	function sortUsers(list: User[], key: SortKey) {
		const sorted = [...list]
		sorted.sort((a, b) => {
			if (key === 'email') return (a.email ?? '').localeCompare(b.email ?? '')
			if (key === 'display_name') {
				return (a.display_name ?? '').localeCompare(b.display_name ?? '')
			}
			if (key === 'is_superuser') {
				const aValue = a.is_superuser ? 1 : 0
				const bValue = b.is_superuser ? 1 : 0
				return bValue - aValue
			}
			if (key === 'is_active') {
				const aValue = a.is_active === false ? 0 : 1
				const bValue = b.is_active === false ? 0 : 1
				return bValue - aValue
			}
			const aValue = parseDate(a[key])
			const bValue = parseDate(b[key])
			return bValue - aValue
		})
		return sorted
	}

	let pageIndex = $state(0)
	let limit = $state(50)
	let refreshToken = $state(0)
	let sortKey = $state<SortKey>('updated_at')

	const SORT_PARAM = 'sort'

	let users = $state<User[]>([])
	let isLoading = $state(false)
	let hasNext = $state(false)
	let error = $state<string | null>(null)

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

	$effect(() => {
		if (!browser) return
		const sort = $page.url.searchParams.get(SORT_PARAM)
		const next =
			sort && sortOptions.some((o) => o.value === (sort as SortKey))
				? (sort as SortKey)
				: 'updated_at'
		if (sortKey !== next) {
			sortKey = next
			pageIndex = 0
		}
	})

	$effect(() => {
		if (!browser) return

		const skip = pageIndex * limit
		sortKey
		refreshToken

		isLoading = true
		error = null

		UsersService.readUsersUsersGet(skip, limit)
			.then((result) => {
				users = sortUsers(result, sortKey)
				hasNext = result.length === limit
			})
			.catch((e: any) => {
				error = e?.message ?? 'failed to load users'
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
					page {pageIndex + 1} · showing {users.length}{hasNext ? '+' : ''}
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
							<Button
								variant="outline"
								class="rounded-xl"
								onclick={(e) => {
									e.stopPropagation()
									goto(`/threads?user=${encodeURIComponent(u.id)}`)
								}}
							>
								threads
							</Button>
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
