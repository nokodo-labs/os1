<script lang="ts">
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import LiquidGlass from '$lib/components/effects/LiquidGlass.svelte'
	import ShimmerText from '$lib/components/effects/ShimmerText.svelte'
	import UserPlus from '$lib/components/icons/UserPlusSolid.svelte'
	import Users from '$lib/components/icons/Users.svelte'
	import XMark from '$lib/components/icons/XMark.svelte'
	import PageTitle from '$lib/components/PageTitle.svelte'
	import { friends, type FriendResponse, type FriendshipDetail } from '$lib/stores/friends.svelte'
	import { modals } from '$lib/stores/modals.svelte'
	import { getUserInitials } from '$lib/utils'
	import { onMount } from 'svelte'

	let actionPending = $state<Set<string>>(new Set())

	onMount(() => {
		void friends.load()
	})

	function navigateToProfile(uid: string) {
		void goto(resolve(`/social/users/${uid}`))
	}

	async function handleAccept(request: FriendshipDetail) {
		actionPending = new Set([...actionPending, request.id])
		try {
			await friends.acceptRequest(request.id)
		} finally {
			actionPending = new Set([...actionPending].filter((id) => id !== request.id))
		}
	}

	async function handleDecline(request: FriendshipDetail) {
		actionPending = new Set([...actionPending, request.id])
		try {
			await friends.declineRequest(request.id)
		} finally {
			actionPending = new Set([...actionPending].filter((id) => id !== request.id))
		}
	}

	async function handleRemoveFriend(friend: FriendResponse) {
		actionPending = new Set([...actionPending, friend.id])
		try {
			await friends.removeFriend(friend.id)
		} finally {
			actionPending = new Set([...actionPending].filter((id) => id !== friend.id))
		}
	}
</script>

<div class="flex flex-1 flex-col gap-6 py-4">
	<div
		class="flex items-center justify-between"
		style="view-transition-name: social-page-header;"
	>
		<PageTitle icon={Users} label="friends" />
		<LiquidGlass class="rounded-full" style="view-transition-name: social-action-btn;">
			<button
				class="interactive text-foreground/80 hover:text-foreground flex items-center gap-1.5 rounded-full border-none bg-transparent px-4 py-2 text-sm font-medium"
				onclick={() => modals.open('add-friends')}
			>
				<UserPlus class="h-4 w-4" />
				<span>add friend</span>
			</button>
		</LiquidGlass>
	</div>

	{#if !friends.isReady}
		<div class="flex flex-col gap-3">
			{#each [0, 1, 2] as i (i)}
				<div class="bg-foreground/5 h-16 animate-pulse rounded-2xl"></div>
			{/each}
		</div>
	{:else if !friends.hasContent}
		<!-- empty state -->
		<div
			class="flex flex-1 flex-col items-center justify-center gap-5"
			style="view-transition-name: social-empty-state;"
		>
			<div
				class="flex h-20 w-20 items-center justify-center rounded-full bg-(--accent-primary)/10"
			>
				<Users class="h-10 w-10 text-(--accent-primary)" />
			</div>
			<div class="flex flex-col items-center gap-2 text-center">
				<p class="text-foreground/80 text-base font-medium">no friends yet</p>
				<p class="text-foreground/50 max-w-xs text-sm">
					add friends to share notes, start conversations, and collaborate together.
				</p>
			</div>
		</div>
	{:else}
		<!-- incoming requests -->
		{#if friends.incoming.length > 0}
			<section class="flex flex-col gap-2">
				<h2 class="text-foreground/40 text-xs font-semibold tracking-wide uppercase">
					incoming requests
				</h2>
				<div class="flex flex-col gap-1">
					{#each friends.incoming as request (request.id)}
						{@const user = request.requester}
						{#if user}
							<div
								class="bg-foreground/3 hover:bg-foreground/5 flex items-center gap-3 rounded-2xl p-3 transition-all"
							>
								<button class="shrink-0" onclick={() => navigateToProfile(user.id)}>
									{#if user.avatar_url}
										<img
											src={user.avatar_url}
											alt={user.display_name ?? ''}
											class="h-10 w-10 rounded-full object-cover"
										/>
									{:else}
										<div
											class="flex h-10 w-10 items-center justify-center rounded-full bg-(--accent-primary)/15 text-xs font-semibold text-(--accent-primary)"
										>
											{getUserInitials(user.display_name ?? user.email)}
										</div>
									{/if}
								</button>
								<button
									class="flex min-w-0 flex-1 flex-col text-left"
									onclick={() => navigateToProfile(user.id)}
								>
									<span class="text-foreground truncate text-sm font-medium">
										{user.display_name ?? user.email.split('@')[0]}
									</span>
									<span class="text-foreground/50 truncate text-xs">
										{user.email}
									</span>
								</button>
								{#if actionPending.has(request.id)}
									<ShimmerText className="shrink-0 text-xs">pending</ShimmerText>
								{:else}
									<div class="flex shrink-0 items-center gap-1.5">
										<button
											class="rounded-lg bg-green-500/20 px-3 py-1.5 text-xs font-medium text-green-600 transition-all hover:bg-green-500/30 active:scale-[0.97] dark:text-green-400"
											onclick={() => handleAccept(request)}
										>
											accept
										</button>
										<button
											class="bg-foreground/8 text-foreground/50 hover:bg-foreground/12 rounded-lg px-3 py-1.5 text-xs font-medium transition-all active:scale-[0.97]"
											onclick={() => handleDecline(request)}
										>
											decline
										</button>
									</div>
								{/if}
							</div>
						{/if}
					{/each}
				</div>
			</section>
		{/if}

		<!-- outgoing requests -->
		{#if friends.outgoing.length > 0}
			<section class="flex flex-col gap-2">
				<h2 class="text-foreground/40 text-xs font-semibold tracking-wide uppercase">
					sent requests
				</h2>
				<div class="flex flex-col gap-1">
					{#each friends.outgoing as request (request.id)}
						{@const user = request.addressee}
						{#if user}
							<div
								class="bg-foreground/3 hover:bg-foreground/5 flex items-center gap-3 rounded-2xl p-3 transition-all"
							>
								<button class="shrink-0" onclick={() => navigateToProfile(user.id)}>
									{#if user.avatar_url}
										<img
											src={user.avatar_url}
											alt={user.display_name ?? ''}
											class="h-10 w-10 rounded-full object-cover"
										/>
									{:else}
										<div
											class="bg-foreground/10 text-foreground/50 flex h-10 w-10 items-center justify-center rounded-full text-xs font-semibold"
										>
											{getUserInitials(user.display_name ?? user.email)}
										</div>
									{/if}
								</button>
								<button
									class="flex min-w-0 flex-1 flex-col text-left"
									onclick={() => navigateToProfile(user.id)}
								>
									<span class="text-foreground truncate text-sm font-medium">
										{user.display_name ?? user.email.split('@')[0]}
									</span>
									<span class="text-foreground/50 truncate text-xs">
										{user.email}
									</span>
								</button>
								<span class="text-foreground/30 shrink-0 text-xs font-medium">
									pending
								</span>
							</div>
						{/if}
					{/each}
				</div>
			</section>
		{/if}

		<!-- friends list -->
		{#if friends.list.length > 0}
			<section class="flex flex-col gap-2">
				<h2 class="text-foreground/40 text-xs font-semibold tracking-wide uppercase">
					friends ({friends.friendCount})
				</h2>
				<div class="flex flex-col gap-1">
					{#each friends.list as friend (friend.id)}
						<div
							class="group hover:bg-foreground/5 flex items-center gap-3 rounded-2xl p-3 transition-all"
						>
							<button class="shrink-0" onclick={() => navigateToProfile(friend.id)}>
								{#if friend.avatar_url}
									<img
										src={friend.avatar_url}
										alt={friend.display_name ?? ''}
										class="h-10 w-10 rounded-full object-cover"
									/>
								{:else}
									<div
										class="flex h-10 w-10 items-center justify-center rounded-full bg-(--accent-primary)/15 text-xs font-semibold text-(--accent-primary)"
									>
										{getUserInitials(friend.display_name ?? friend.email)}
									</div>
								{/if}
							</button>
							<button
								class="flex min-w-0 flex-1 flex-col text-left"
								onclick={() => navigateToProfile(friend.id)}
							>
								<span class="text-foreground truncate text-sm font-medium">
									{friend.display_name ?? friend.email.split('@')[0]}
								</span>
								<span class="text-foreground/50 truncate text-xs">
									{friend.email}
								</span>
							</button>
							{#if actionPending.has(friend.id)}
								<ShimmerText className="shrink-0 text-xs">pending</ShimmerText>
							{:else}
								<button
									class="text-foreground/0 group-hover:text-foreground/30 hover:bg-foreground/8 hover:text-foreground/60 shrink-0 rounded-lg p-1.5 transition-all"
									title="remove friend"
									onclick={() => handleRemoveFriend(friend)}
								>
									<XMark class="h-4 w-4" />
								</button>
							{/if}
						</div>
					{/each}
				</div>
			</section>
		{/if}
	{/if}
</div>
