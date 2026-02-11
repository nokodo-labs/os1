<script lang="ts">
	import { api, unwrap, type Role } from '$lib/api'
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
	let hasFetched = $state(false)
	let showDropdown = $state(false)

	async function fetchRoles() {
		if (hasFetched) return
		isLoading = true
		try {
			roles = unwrap(await api.GET('/v1/roles', { params: { query: { limit: 200 } } }))
			hasFetched = true
		} catch {
			roles = []
		} finally {
			isLoading = false
		}
	}

	$effect(() => {
		fetchRoles()
	})

	const selectedRoles = $derived(
		value.map((id) => {
			const role = roles.find((r) => r.id === id)
			return role ? { id: role.id, name: role.name } : { id, name: id }
		})
	)

	const lowerQuery = $derived(query.toLowerCase().trim())

	const filteredRoles = $derived(
		roles
			.filter((r) => !value.includes(r.id))
			.filter(
				(r) =>
					!lowerQuery ||
					r.name.toLowerCase().includes(lowerQuery) ||
					(r.description ?? '').toLowerCase().includes(lowerQuery) ||
					r.id.toLowerCase().includes(lowerQuery)
			)
	)

	function addRole(roleId: string) {
		if (!value.includes(roleId)) {
			value = [...value, roleId]
		}
		query = ''
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
			onfocus={() => (showDropdown = true)}
		/>
		{#if showDropdown && (filteredRoles.length > 0 || isLoading)}
			<!-- svelte-ignore a11y_no_static_element_interactions -->
			<div
				class="absolute top-full right-0 left-0 z-10 mt-1 max-h-48 overflow-y-auto rounded-xl border border-zinc-700 bg-zinc-900 shadow-lg"
				onmousedown={(e) => e.preventDefault()}
			>
				{#if isLoading}
					<div class="px-3 py-4 text-center text-sm text-zinc-500">loading...</div>
				{:else}
					{#each filteredRoles.slice(0, 10) as role (role.id)}
						<button
							type="button"
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
				{/if}
			</div>
		{/if}
	</div>
</div>
