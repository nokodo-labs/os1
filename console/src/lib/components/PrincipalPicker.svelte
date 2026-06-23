<script lang="ts">
	import { api, unwrap, type Schemas } from '$lib/api'
	import { onMount } from 'svelte'

	type Group = Schemas['Group']
	type Role = Schemas['Role']
	type User = Schemas['User']

	import { Input } from '$lib/components/ui/input'
	import { Shield, Users, UsersRound } from '@lucide/svelte'

	type PrincipalType = 'user' | 'group' | 'role'

	type PickedPrincipal = {
		type: PrincipalType
		id: string
		label: string
	}

	let {
		onPick,
		exclude = [],
	}: {
		onPick: (principal: PickedPrincipal) => void
		exclude?: string[]
	} = $props()

	let activeTab = $state<PrincipalType>('user')
	let query = $state('')

	const PAGE_LIMIT = 20

	let users = $state<User[]>([])
	let groups = $state<Group[]>([])
	let roles = $state<Role[]>([])

	let isLoading = $state(false)
	let userSkip = $state(0)
	let groupSkip = $state(0)
	let roleSkip = $state(0)
	let hasMoreUsers = $state(true)
	let hasMoreGroups = $state(true)
	let hasMoreRoles = $state(true)
	let userRequestId = 0
	let groupRequestId = 0
	let roleRequestId = 0
	let searchTimer: ReturnType<typeof setTimeout> | null = null

	const visibleUsers = $derived(users.filter((u) => !exclude.includes(u.id)))
	const visibleGroups = $derived(groups.filter((g) => !exclude.includes(g.id)))
	const visibleRoles = $derived(roles.filter((r) => !exclude.includes(r.id)))

	const activeHasMore = $derived.by(() => {
		if (activeTab === 'user') return hasMoreUsers
		if (activeTab === 'group') return hasMoreGroups
		return hasMoreRoles
	})

	async function fetchUsers(reset = false) {
		if (isLoading && !reset) return
		isLoading = true
		const requestId = ++userRequestId
		const skip = reset ? 0 : userSkip
		try {
			const result = unwrap(
				await api.GET('/v1/users', {
					params: {
						query: {
							limit: PAGE_LIMIT,
							skip,
							sort_by: 'display_name',
							sort_dir: 'asc',
							q: query.trim() || undefined,
						},
					},
				})
			)
			if (requestId !== userRequestId) return
			users = reset ? result : [...users, ...result]
			userSkip = skip + result.length
			hasMoreUsers = result.length === PAGE_LIMIT
		} catch {
			if (requestId === userRequestId) {
				users = reset ? [] : users
				hasMoreUsers = false
			}
		} finally {
			if (requestId === userRequestId) isLoading = false
		}
	}

	async function fetchGroups(reset = false) {
		if (isLoading && !reset) return
		isLoading = true
		const requestId = ++groupRequestId
		const skip = reset ? 0 : groupSkip
		try {
			const result = unwrap(
				await api.GET('/v1/groups', {
					params: {
						query: {
							limit: PAGE_LIMIT,
							skip,
							sort_by: 'name',
							sort_dir: 'asc',
							q: query.trim() || undefined,
						},
					},
				})
			)
			if (requestId !== groupRequestId) return
			groups = reset ? result : [...groups, ...result]
			groupSkip = skip + result.length
			hasMoreGroups = result.length === PAGE_LIMIT
		} catch {
			if (requestId === groupRequestId) {
				groups = reset ? [] : groups
				hasMoreGroups = false
			}
		} finally {
			if (requestId === groupRequestId) isLoading = false
		}
	}

	async function fetchRoles(reset = false) {
		if (isLoading && !reset) return
		isLoading = true
		const requestId = ++roleRequestId
		const skip = reset ? 0 : roleSkip
		try {
			const result = unwrap(
				await api.GET('/v1/roles', {
					params: {
						query: {
							limit: PAGE_LIMIT,
							skip,
							sort_by: 'name',
							sort_dir: 'asc',
							q: query.trim() || undefined,
						},
					},
				})
			)
			if (requestId !== roleRequestId) return
			roles = reset ? result : [...roles, ...result]
			roleSkip = skip + result.length
			hasMoreRoles = result.length === PAGE_LIMIT
		} catch {
			if (requestId === roleRequestId) {
				roles = reset ? [] : roles
				hasMoreRoles = false
			}
		} finally {
			if (requestId === roleRequestId) isLoading = false
		}
	}

	function loadActive(reset = false) {
		if (activeTab === 'user') return fetchUsers(reset)
		if (activeTab === 'group') return fetchGroups(reset)
		return fetchRoles(reset)
	}

	function switchTab(tab: PrincipalType) {
		activeTab = tab
		query = ''
		void loadActive(true)
	}

	function scheduleSearch() {
		if (searchTimer) clearTimeout(searchTimer)
		searchTimer = setTimeout(() => {
			void loadActive(true)
		}, 250)
	}

	function handleScroll(event: Event) {
		if (!(event.currentTarget instanceof HTMLElement)) return
		const target = event.currentTarget
		if (target.scrollTop + target.clientHeight < target.scrollHeight - 24) return
		if (!activeHasMore || isLoading) return
		void loadActive(false)
	}

	function pickUser(user: User) {
		onPick({ type: 'user', id: user.id, label: user.display_name || user.email })
		query = ''
		void loadActive(true)
	}

	function pickGroup(group: Group) {
		onPick({ type: 'group', id: group.id, label: group.name })
		query = ''
		void loadActive(true)
	}

	function pickRole(role: Role) {
		onPick({ type: 'role', id: role.id, label: role.name })
		query = ''
		void loadActive(true)
	}

	const tabs: { value: PrincipalType; label: string; icon: typeof Users }[] = [
		{ value: 'user', label: 'users', icon: Users },
		{ value: 'group', label: 'groups', icon: UsersRound },
		{ value: 'role', label: 'roles', icon: Shield },
	]

	onMount(() => {
		void fetchUsers(true)
	})
</script>

<div class="space-y-3">
	<div class="flex gap-1 rounded-lg border border-zinc-800 bg-zinc-950 p-1">
		{#each tabs as tab (tab.value)}
			<button
				type="button"
				class="flex flex-1 items-center justify-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors {activeTab ===
				tab.value
					? 'bg-zinc-800 text-zinc-100'
					: 'text-zinc-500 hover:text-zinc-300'}"
				onclick={() => switchTab(tab.value)}
			>
				<tab.icon class="h-3.5 w-3.5" />
				{tab.label}
			</button>
		{/each}
	</div>

	<Input
		bind:value={query}
		oninput={scheduleSearch}
		placeholder="search {activeTab === 'user'
			? 'by email or name'
			: activeTab === 'group'
				? 'by group name'
				: 'by role name'}..."
		class="rounded-xl"
	/>

	<div
		class="max-h-48 overflow-y-auto rounded-xl border border-zinc-800 bg-zinc-950"
		onscroll={handleScroll}
	>
		{#if isLoading && users.length === 0 && activeTab === 'user'}
			<div class="px-4 py-6 text-center text-sm text-zinc-500">loading...</div>
		{:else if isLoading && groups.length === 0 && activeTab === 'group'}
			<div class="px-4 py-6 text-center text-sm text-zinc-500">loading...</div>
		{:else if isLoading && roles.length === 0 && activeTab === 'role'}
			<div class="px-4 py-6 text-center text-sm text-zinc-500">loading...</div>
		{:else if activeTab === 'user'}
			{#if visibleUsers.length === 0}
				<div class="px-4 py-6 text-center text-sm text-zinc-500">no users found</div>
			{:else}
				{#each visibleUsers as user (user.id)}
					<button
						type="button"
						class="flex w-full items-center gap-3 px-3 py-2 text-left text-sm text-zinc-200 transition-colors hover:bg-zinc-800/60"
						onclick={() => pickUser(user)}
					>
						<Users class="h-3.5 w-3.5 shrink-0 text-zinc-500" />
						<div class="min-w-0 flex-1">
							<div class="truncate font-medium">
								{user.display_name || user.email}
							</div>
							{#if user.display_name}
								<div class="truncate text-xs text-zinc-500">{user.email}</div>
							{/if}
						</div>
					</button>
				{/each}
			{/if}
		{:else if activeTab === 'group'}
			{#if visibleGroups.length === 0}
				<div class="px-4 py-6 text-center text-sm text-zinc-500">no groups found</div>
			{:else}
				{#each visibleGroups as group (group.id)}
					<button
						type="button"
						class="flex w-full items-center gap-3 px-3 py-2 text-left text-sm text-zinc-200 transition-colors hover:bg-zinc-800/60"
						onclick={() => pickGroup(group)}
					>
						<UsersRound class="h-3.5 w-3.5 shrink-0 text-zinc-500" />
						<div class="min-w-0 flex-1">
							<div class="truncate font-medium">{group.name}</div>
							{#if group.description}
								<div class="truncate text-xs text-zinc-500">
									{group.description}
								</div>
							{/if}
						</div>
					</button>
				{/each}
			{/if}
		{:else if visibleRoles.length === 0}
			<div class="px-4 py-6 text-center text-sm text-zinc-500">no roles found</div>
		{:else}
			{#each visibleRoles as role (role.id)}
				<button
					type="button"
					class="flex w-full items-center gap-3 px-3 py-2 text-left text-sm text-zinc-200 transition-colors hover:bg-zinc-800/60"
					onclick={() => pickRole(role)}
				>
					<Shield class="h-3.5 w-3.5 shrink-0 text-zinc-500" />
					<div class="min-w-0 flex-1">
						<div class="truncate font-medium">{role.name}</div>
						{#if role.description}
							<div class="truncate text-xs text-zinc-500">
								{role.description}
							</div>
						{/if}
					</div>
				</button>
			{/each}
		{/if}
		{#if isLoading && activeHasMore}
			<div class="px-4 py-3 text-center text-xs text-zinc-500">loading more...</div>
		{:else if activeHasMore}
			<button
				type="button"
				class="w-full border-t border-zinc-800 px-4 py-2.5 text-center text-xs text-zinc-400 transition-colors hover:bg-zinc-900 hover:text-zinc-200"
				onclick={() => loadActive(false)}
			>
				load more
			</button>
		{/if}
	</div>
</div>
