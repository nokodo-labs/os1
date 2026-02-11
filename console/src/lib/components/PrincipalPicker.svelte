<script lang="ts">
	import { api, unwrap, type Group, type Role, type User } from '$lib/api'
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

	let users = $state<User[]>([])
	let groups = $state<Group[]>([])
	let roles = $state<Role[]>([])

	let isLoading = $state(false)
	let hasFetched = $state({ user: false, group: false, role: false })

	async function fetchUsers() {
		if (hasFetched.user) return
		isLoading = true
		try {
			users = unwrap(await api.GET('/v1/users', { params: { query: { limit: 200 } } }))
			hasFetched = { ...hasFetched, user: true }
		} catch {
			users = []
		} finally {
			isLoading = false
		}
	}

	async function fetchGroups() {
		if (hasFetched.group) return
		isLoading = true
		try {
			groups = unwrap(await api.GET('/v1/groups', { params: { query: { limit: 200 } } }))
			hasFetched = { ...hasFetched, group: true }
		} catch {
			groups = []
		} finally {
			isLoading = false
		}
	}

	async function fetchRoles() {
		if (hasFetched.role) return
		isLoading = true
		try {
			roles = unwrap(await api.GET('/v1/roles', { params: { query: { limit: 200 } } }))
			hasFetched = { ...hasFetched, role: true }
		} catch {
			roles = []
		} finally {
			isLoading = false
		}
	}

	function switchTab(tab: PrincipalType) {
		activeTab = tab
		query = ''
		if (tab === 'user') fetchUsers()
		else if (tab === 'group') fetchGroups()
		else fetchRoles()
	}

	$effect(() => {
		fetchUsers()
	})

	const lowerQuery = $derived(query.toLowerCase().trim())

	const filteredUsers = $derived(
		users
			.filter((u) => !exclude.includes(u.id))
			.filter(
				(u) =>
					!lowerQuery ||
					u.email.toLowerCase().includes(lowerQuery) ||
					(u.display_name ?? '').toLowerCase().includes(lowerQuery)
			)
	)

	const filteredGroups = $derived(
		groups
			.filter((g) => !exclude.includes(g.id))
			.filter(
				(g) =>
					!lowerQuery ||
					g.name.toLowerCase().includes(lowerQuery) ||
					(g.description ?? '').toLowerCase().includes(lowerQuery)
			)
	)

	const filteredRoles = $derived(
		roles
			.filter((r) => !exclude.includes(r.id))
			.filter(
				(r) =>
					!lowerQuery ||
					r.name.toLowerCase().includes(lowerQuery) ||
					(r.description ?? '').toLowerCase().includes(lowerQuery)
			)
	)

	function pickUser(user: User) {
		onPick({ type: 'user', id: user.id, label: user.display_name || user.email })
		query = ''
	}

	function pickGroup(group: Group) {
		onPick({ type: 'group', id: group.id, label: group.name })
		query = ''
	}

	function pickRole(role: Role) {
		onPick({ type: 'role', id: role.id, label: role.name })
		query = ''
	}

	const tabs: { value: PrincipalType; label: string; icon: typeof Users }[] = [
		{ value: 'user', label: 'users', icon: Users },
		{ value: 'group', label: 'groups', icon: UsersRound },
		{ value: 'role', label: 'roles', icon: Shield },
	]
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
		placeholder="search {activeTab === 'user'
			? 'by email or name'
			: activeTab === 'group'
				? 'by group name'
				: 'by role name'}..."
		class="rounded-xl"
	/>

	<div class="max-h-48 overflow-y-auto rounded-xl border border-zinc-800 bg-zinc-950">
		{#if isLoading}
			<div class="px-4 py-6 text-center text-sm text-zinc-500">loading...</div>
		{:else if activeTab === 'user'}
			{#if filteredUsers.length === 0}
				<div class="px-4 py-6 text-center text-sm text-zinc-500">no users found</div>
			{:else}
				{#each filteredUsers.slice(0, 20) as user (user.id)}
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
			{#if filteredGroups.length === 0}
				<div class="px-4 py-6 text-center text-sm text-zinc-500">no groups found</div>
			{:else}
				{#each filteredGroups.slice(0, 20) as group (group.id)}
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
		{:else if filteredRoles.length === 0}
			<div class="px-4 py-6 text-center text-sm text-zinc-500">no roles found</div>
		{:else}
			{#each filteredRoles.slice(0, 20) as role (role.id)}
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
	</div>
</div>
