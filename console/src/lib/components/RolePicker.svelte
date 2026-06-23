<script lang="ts">
	import { api, unwrap, type Schemas } from '$lib/api'
	import { onMount } from 'svelte'

	type Role = Schemas['Role']

	import { Input } from '$lib/components/ui/input'
	import { Shield, X } from '@lucide/svelte'

	let {
		value = $bindable<string[]>([]),
	}: {
		value?: string[]
	} = $props()

	let query = $state('')
	let roles = $state<Role[]>([])
	let isLoading = $state(false)
	let roleSkip = $state(0)
	let hasMoreRoles = $state(true)
	let showDropdown = $state(false)
	let requestId = 0
	let searchTimer: ReturnType<typeof setTimeout> | null = null

	const PAGE_LIMIT = 20

	async function fetchRoles(reset = false) {
		if (isLoading && !reset) return
		isLoading = true
		const currentRequestId = ++requestId
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
			if (currentRequestId !== requestId) return
			roles = reset ? result : [...roles, ...result]
			roleSkip = skip + result.length
			hasMoreRoles = result.length === PAGE_LIMIT
		} catch {
			if (currentRequestId === requestId) {
				roles = reset ? [] : roles
				hasMoreRoles = false
			}
		} finally {
			if (currentRequestId === requestId) isLoading = false
		}
	}

	onMount(() => {
		void fetchRoles(true)
	})

	const selectedRoles = $derived(
		value.map((id) => {
			const role = roles.find((r) => r.id === id)
			return role ? { id: role.id, name: role.name } : { id, name: id }
		})
	)

	const filteredRoles = $derived(roles.filter((r) => !value.includes(r.id)))

	function scheduleSearch() {
		if (searchTimer) clearTimeout(searchTimer)
		searchTimer = setTimeout(() => {
			void fetchRoles(true)
		}, 250)
	}

	function handleScroll(event: Event) {
		if (!(event.currentTarget instanceof HTMLElement)) return
		const target = event.currentTarget
		if (target.scrollTop + target.clientHeight < target.scrollHeight - 24) return
		if (!hasMoreRoles || isLoading) return
		void fetchRoles(false)
	}

	function addRole(roleId: string) {
		if (!value.includes(roleId)) {
			value = [...value, roleId]
		}
		query = ''
		void fetchRoles(true)
		showDropdown = false
	}

	function removeRole(roleId: string) {
		value = value.filter((id) => id !== roleId)
	}
</script>

<div class="space-y-2">
	{#if selectedRoles.length > 0}
		<div class="flex flex-wrap gap-1.5">
			{#each selectedRoles as role (role.id)}
				<span
					class="inline-flex items-center gap-1 rounded-lg border border-zinc-700 bg-zinc-800 px-2 py-1 text-xs text-zinc-200"
				>
					<Shield class="h-3 w-3 text-zinc-500" />
					<span class="max-w-40 truncate">{role.name}</span>
					<button
						type="button"
						class="ml-0.5 rounded p-0.5 text-zinc-500 transition-colors hover:text-red-400"
						onclick={() => removeRole(role.id)}
						aria-label="remove {role.name}"
					>
						<X class="h-3 w-3" />
					</button>
				</span>
			{/each}
		</div>
	{/if}

	<div class="relative">
		<Input
			bind:value={query}
			placeholder="search roles to add..."
			class="rounded-xl"
			onfocus={() => {
				showDropdown = true
				if (roles.length === 0) void fetchRoles(true)
			}}
			oninput={scheduleSearch}
		/>
		{#if showDropdown && (filteredRoles.length > 0 || isLoading || hasMoreRoles || query.trim())}
			<div
				class="absolute top-full right-0 left-0 z-10 mt-1 max-h-48 overflow-y-auto rounded-xl border border-zinc-700 bg-zinc-900 shadow-lg"
				role="listbox"
				tabindex="-1"
				onmousedown={(e) => e.preventDefault()}
				onscroll={handleScroll}
			>
				{#if isLoading}
					<div class="px-3 py-4 text-center text-sm text-zinc-500">loading...</div>
				{:else}
					{#each filteredRoles as role (role.id)}
						<button
							type="button"
							role="option"
							aria-selected="false"
							class="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-zinc-200 transition-colors hover:bg-zinc-800"
							onclick={() => addRole(role.id)}
						>
							<Shield class="h-3.5 w-3.5 shrink-0 text-zinc-500" />
							<span class="truncate font-medium">{role.name}</span>
							{#if role.description}
								<span class="truncate text-xs text-zinc-500">
									{role.description}
								</span>
							{/if}
						</button>
					{/each}
					{#if filteredRoles.length === 0}
						<div class="px-3 py-4 text-center text-sm text-zinc-500">
							no more roles available
						</div>
					{/if}
					{#if hasMoreRoles}
						<button
							type="button"
							class="w-full border-t border-zinc-800 px-3 py-2 text-center text-xs text-zinc-400 transition-colors hover:bg-zinc-800 hover:text-zinc-200"
							onclick={() => fetchRoles(false)}
						>
							load more
						</button>
					{/if}
				{/if}
			</div>
		{/if}
	</div>
</div>
