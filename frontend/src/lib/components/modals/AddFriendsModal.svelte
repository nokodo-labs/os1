<script lang="ts">
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import Search from '$lib/components/icons/Search.svelte'
	import User from '$lib/components/icons/User.svelte'
	import UserPlus from '$lib/components/icons/UserPlusSolid.svelte'
	import BaseModal from '$lib/components/modals/BaseModal.svelte'
	import { getUserInitials } from '$lib/utils'

	interface AddFriendsModalProps {
		open: boolean
		onClose: () => void
	}

	let { open, onClose }: AddFriendsModalProps = $props()

	let query = $state('')
	let isSearching = $state(false)
	let hasSearched = $state(false)

	// TODO: replace with real API call when friend endpoints exist
	type SearchResult = {
		id: string
		display_name: string
		email: string
		avatar_url?: string | null
		requestSent?: boolean
	}
	let results = $state<SearchResult[]>([])

	async function handleSearch() {
		const q = query.trim()
		if (!q) return
		isSearching = true
		hasSearched = true
		// placeholder: will call friend search API when backend is ready
		// await apiClient().GET('/v1/users/search', { params: { query: { q } } })
		results = []
		isSearching = false
	}

	function handleSendRequest(user: SearchResult) {
		// TODO: call friend request API when backend is ready
		user.requestSent = true
		results = [...results]
	}

	function handleViewProfile(user: SearchResult) {
		onClose()
		void goto(resolve(`/social/users/${user.id}`))
	}

	function handleKeyDown(e: KeyboardEvent) {
		if (e.key === 'Enter') {
			e.preventDefault()
			handleSearch()
		}
	}

	// reset state when modal closes
	$effect(() => {
		if (!open) {
			query = ''
			results = []
			hasSearched = false
			isSearching = false
		}
	})
</script>

<BaseModal {open} title="add friends" description="search by username or email" {onClose}>
	<!-- search input -->
	<div class="relative mb-4">
		<Search class="absolute top-1/2 left-3.5 h-4.5 w-4.5 -translate-y-1/2 text-foreground/30" />
		<input
			class="w-full rounded-xl bg-foreground/8 py-3 pr-4 pl-10 text-sm text-foreground ring-1 ring-foreground/10 transition-all outline-none placeholder:text-foreground/30 focus:ring-(--accent-primary)/50"
			type="text"
			placeholder="search by name or email..."
			bind:value={query}
			onkeydown={handleKeyDown}
		/>
	</div>

	<!-- results area -->
	<div class="flex flex-col gap-1">
		{#if isSearching}
			<div class="flex flex-col gap-2 py-6">
				{#each { length: 3 } as _item, i (i)}
					<div class="flex items-center gap-3 rounded-xl p-3">
						<div class="h-10 w-10 animate-pulse rounded-full bg-foreground/8"></div>
						<div class="flex flex-1 flex-col gap-1.5">
							<div class="h-3.5 w-28 animate-pulse rounded bg-foreground/8"></div>
							<div class="h-3 w-40 animate-pulse rounded bg-foreground/8"></div>
						</div>
					</div>
				{/each}
			</div>
		{:else if results.length > 0}
			{#each results as user (user.id)}
				<div class="flex items-center gap-3 rounded-xl p-3 transition-all hover:bg-foreground/5">
					<!-- avatar (clickable to profile) -->
					<button class="shrink-0" onclick={() => handleViewProfile(user)}>
						{#if user.avatar_url}
							<img
								src={user.avatar_url}
								alt={user.display_name}
								class="h-10 w-10 rounded-full object-cover"
							/>
						{:else}
							<div
								class="flex h-10 w-10 items-center justify-center rounded-full bg-(--accent-primary)/15 text-xs font-semibold text-(--accent-primary)"
							>
								{getUserInitials(user.display_name)}
							</div>
						{/if}
					</button>

					<!-- user info (clickable to profile) -->
					<button
						class="flex min-w-0 flex-1 flex-col text-left"
						onclick={() => handleViewProfile(user)}
					>
						<span class="truncate text-sm font-medium text-foreground">
							{user.display_name}
						</span>
						<span class="truncate text-xs text-foreground/50">{user.email}</span>
					</button>

					<!-- add button -->
					{#if user.requestSent}
						<span class="shrink-0 text-xs font-medium text-foreground/40">sent</span>
					{:else}
						<button
							class="flex shrink-0 items-center gap-1.5 rounded-lg bg-(--accent-primary)/20 px-3 py-1.5 text-xs font-medium text-(--accent-primary) transition-all hover:bg-(--accent-primary)/30 active:scale-[0.97]"
							onclick={() => handleSendRequest(user)}
						>
							<UserPlus class="h-3.5 w-3.5" />
							<span>add</span>
						</button>
					{/if}
				</div>
			{/each}
		{:else if hasSearched}
			<!-- no results -->
			<div class="flex flex-col items-center gap-4 py-10">
				<div class="flex h-14 w-14 items-center justify-center rounded-full bg-foreground/5">
					<User class="h-7 w-7 text-foreground/30" />
				</div>
				<div class="flex flex-col items-center gap-1.5 text-center">
					<p class="text-sm font-medium text-foreground/60">no users found</p>
					<p class="max-w-xs text-xs text-foreground/40">
						try a different name or email, or invite them to the platform
					</p>
				</div>
				<!-- invite button -->
				<button
					class="flex items-center gap-2 rounded-xl bg-(--accent-primary)/15 px-4 py-2.5 text-sm font-medium text-(--accent-primary) transition-all hover:bg-(--accent-primary)/25 active:scale-[0.97]"
					onclick={() => {
						// TODO: invite by email flow
					}}
				>
					<UserPlus class="h-4 w-4" />
					<span>invite by email</span>
				</button>
			</div>
		{:else}
			<!-- initial state -->
			<div class="flex flex-col items-center gap-3 py-10 text-center">
				<Search class="h-8 w-8 text-foreground/20" />
				<p class="text-sm text-foreground/40">search for users to send them a friend request</p>
			</div>
		{/if}
	</div>
</BaseModal>
