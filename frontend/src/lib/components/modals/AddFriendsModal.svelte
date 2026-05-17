<script lang="ts">
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import EmptyState from '$lib/components/EmptyState.svelte'
	import ShimmerText from '$lib/components/effects/ShimmerText.svelte'
	import Check from '$lib/components/icons/Check.svelte'
	import Search from '$lib/components/icons/Search.svelte'
	import User from '$lib/components/icons/User.svelte'
	import UserPlus from '$lib/components/icons/UserPlusSolid.svelte'
	import BaseModal from '$lib/components/modals/BaseModal.svelte'
	import { friends, type UserSearchResult } from '$lib/stores/friends.svelte'
	import { getUserInitials } from '$lib/utils'
	import { userDisplayName, userHandleOrId } from '$lib/utils/resourceAuthors'

	interface AddFriendsModalProps {
		open: boolean
		onClose: () => void
	}

	let { open, onClose }: AddFriendsModalProps = $props()

	let query = $state('')
	let isSearching = $state(false)
	let hasSearched = $state(false)
	let results = $state<UserSearchResult[]>([])
	let pendingIds = $state<Set<string>>(new Set())
	let sentIds = $state<Set<string>>(new Set())
	let lastSearchedQuery = $state('')
	let searchRequestId = 0

	async function runSearch(q: string, force = false) {
		if (!q) return
		if (!force && q === lastSearchedQuery) return
		lastSearchedQuery = q
		const requestId = ++searchRequestId
		isSearching = true
		hasSearched = true
		try {
			const found = await friends.searchUsers(q)
			if (requestId === searchRequestId) results = found
		} finally {
			if (requestId === searchRequestId) isSearching = false
		}
	}

	async function handleSearch(force = false) {
		const q = query.trim()
		if (!q) return
		await runSearch(q, force)
	}

	async function handleSendRequest(userId: string) {
		pendingIds = new Set([...pendingIds, userId])
		try {
			const sent = await friends.sendRequest(userId)
			if (sent) {
				sentIds = new Set([...sentIds, userId])
				void friends.refresh()
			}
		} finally {
			pendingIds = new Set([...pendingIds].filter((id) => id !== userId))
		}
	}

	async function handleAcceptRequest(friendshipId: string, userId: string) {
		pendingIds = new Set([...pendingIds, userId])
		try {
			await friends.acceptRequest(friendshipId)
		} finally {
			pendingIds = new Set([...pendingIds].filter((id) => id !== userId))
		}
	}

	function handleViewProfile(user: UserSearchResult) {
		onClose()
		void goto(resolve(`/social/users/${user.id}`))
	}

	function handleKeyDown(e: KeyboardEvent) {
		if (e.key === 'Enter') {
			e.preventDefault()
			void handleSearch(true)
		}
	}

	function userLabel(user: UserSearchResult): string {
		return userDisplayName(user) ?? user.id
	}

	function userMeta(user: UserSearchResult): string {
		return userHandleOrId(user) ?? user.id
	}

	// reset state when modal closes
	$effect(() => {
		if (!open) {
			query = ''
			results = []
			hasSearched = false
			isSearching = false
			pendingIds = new Set()
			sentIds = new Set()
			lastSearchedQuery = ''
			searchRequestId += 1
		}
	})

	$effect(() => {
		if (!open) return
		const q = query.trim()
		if (!q) {
			searchRequestId += 1
			results = []
			hasSearched = false
			isSearching = false
			lastSearchedQuery = ''
			return
		}

		searchRequestId += 1
		const timeoutId = window.setTimeout(() => {
			void runSearch(q)
		}, 250)
		return () => window.clearTimeout(timeoutId)
	})
</script>

<BaseModal {open} title="add friends" description="search users" {onClose}>
	<!-- search input -->
	<div class="relative -mt-1 mb-4 pt-1">
		<Search class="text-foreground/30 absolute top-1/2 left-3.5 h-4.5 w-4.5 -translate-y-1/2" />
		<input
			class="bg-foreground/8 text-foreground ring-foreground/10 placeholder:text-foreground/30 rounded-pill w-full py-3 pr-4 pl-10 text-sm ring-1 transition-all outline-none focus:ring-(--accent-primary)/50"
			type="text"
			placeholder="search users"
			bind:value={query}
			onkeydown={handleKeyDown}
		/>
	</div>

	<!-- results area -->
	<div class="flex flex-col gap-1">
		{#if isSearching}
			<div class="flex flex-col gap-2 py-6">
				{#each [0, 1, 2] as i (i)}
					<div class="flex items-center gap-3 rounded-xl p-3">
						<div class="bg-foreground/8 h-10 w-10 animate-pulse rounded-full"></div>
						<div class="flex flex-1 flex-col gap-1.5">
							<div class="bg-foreground/8 h-3.5 w-28 animate-pulse rounded"></div>
							<div class="bg-foreground/8 h-3 w-40 animate-pulse rounded"></div>
						</div>
					</div>
				{/each}
			</div>
		{:else if results.length > 0}
			{#each results as user (user.id)}
				{@const displayName = userLabel(user)}
				{@const relationship = friends.getRelationship(user.id)}
				<div
					class="hover:bg-foreground/5 rounded-pill flex items-center gap-3 p-2.5 transition-all"
				>
					<!-- avatar (clickable to profile) -->
					<button
						type="button"
						class="shrink-0 cursor-pointer"
						onclick={() => handleViewProfile(user)}
					>
						{#if user.avatar_url}
							<img
								src={user.avatar_url}
								alt={displayName}
								class="h-10 w-10 rounded-full object-cover"
							/>
						{:else}
							<div
								class="flex h-10 w-10 items-center justify-center rounded-full bg-(--accent-primary)/15 text-xs font-semibold text-(--accent-primary)"
							>
								{getUserInitials(displayName)}
							</div>
						{/if}
					</button>

					<!-- user info (clickable to profile) -->
					<button
						type="button"
						class="flex min-w-0 flex-1 cursor-pointer flex-col text-left"
						onclick={() => handleViewProfile(user)}
					>
						<span class="text-foreground truncate text-sm font-medium">
							{displayName}
						</span>
						<span class="text-foreground/50 truncate text-xs">{userMeta(user)}</span>
					</button>

					<!-- action button -->
					{#if pendingIds.has(user.id)}
						<ShimmerText className="shrink-0 text-xs font-medium">pending</ShimmerText>
					{:else if relationship?.kind === 'accepted'}
						<span
							class="flex shrink-0 items-center gap-1 text-xs font-medium text-green-500/70"
						>
							<Check class="h-3.5 w-3.5" />
							friends
						</span>
					{:else if relationship?.kind === 'pending_outgoing' || sentIds.has(user.id)}
						<span
							class="text-foreground/55 bg-foreground/8 rounded-pill flex shrink-0 items-center gap-1.5 px-3 py-1.5 text-xs font-semibold"
						>
							<Check class="h-3.5 w-3.5" />
							request sent
						</span>
					{:else if relationship?.kind === 'pending_incoming'}
						<button
							type="button"
							class="rounded-pill flex shrink-0 cursor-pointer items-center gap-1.5 bg-green-500/20 px-3 py-1.5 text-xs font-semibold text-green-600 transition-all hover:bg-green-500/30 active:scale-[0.97] dark:text-green-400"
							onclick={() => handleAcceptRequest(relationship.friendshipId, user.id)}
						>
							<Check class="h-3.5 w-3.5" />
							accept
						</button>
					{:else}
						<button
							type="button"
							class="rounded-pill flex shrink-0 cursor-pointer items-center gap-1.5 bg-(--accent-primary)/20 px-3 py-1.5 text-xs font-semibold text-(--accent-primary) transition-all hover:bg-(--accent-primary)/30 active:scale-[0.97]"
							onclick={() => handleSendRequest(user.id)}
						>
							<UserPlus class="h-3.5 w-3.5" />
							<span>add</span>
						</button>
					{/if}
				</div>
			{/each}
		{:else if hasSearched}
			<div class="flex flex-col items-center gap-4 py-10">
				<EmptyState
					label="no users found"
					description="try a different name or email, or invite them to the platform"
					compact
				>
					{#snippet icon()}<User class="h-7 w-7" />{/snippet}
				</EmptyState>
				<!-- invite button -->
				<button
					type="button"
					class="rounded-pill flex cursor-pointer items-center gap-2 bg-(--accent-primary)/15 px-4 py-2.5 text-sm font-semibold text-(--accent-primary) transition-all hover:bg-(--accent-primary)/25 active:scale-[0.97]"
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
				<Search class="text-foreground/20 h-8 w-8" />
				<p class="text-foreground/40 text-sm">
					search for users to send them a friend request
				</p>
			</div>
		{/if}
	</div>
</BaseModal>
