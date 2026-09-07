<script lang="ts">
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import ShimmerText from '$lib/components/effects/ShimmerText.svelte'
	import EmptyState from '$lib/components/EmptyState.svelte'
	import ChatBubble from '$lib/components/icons/ChatBubble.svelte'
	import Check from '$lib/components/icons/Check.svelte'
	import UserMinus from '$lib/components/icons/UserMinus.svelte'
	import UserPlus from '$lib/components/icons/UserPlus.svelte'
	import Users from '$lib/components/icons/Users.svelte'
	import XMark from '$lib/components/icons/XMark.svelte'
	import { MenuItem, Skeleton } from '$lib/components/primitives'
	import PersonRowMenu from '$lib/components/social/PersonRowMenu.svelte'
	import { useSystemChrome } from '$lib/contexts/systemChromeContext.svelte'
	import { device } from '$lib/stores/device.svelte'
	import { friends, type FriendResponse, type FriendshipDetail } from '$lib/stores/friends.svelte'
	import { messages } from '$lib/stores/messages.svelte'
	import { modals } from '$lib/stores/modals.svelte'
	import { getUserInitials } from '$lib/utils'
	import { userDisplayName, userHandleOrId } from '$lib/utils/resourceAuthors'
	import { onMount } from 'svelte'

	type SocialUser = Pick<
		FriendResponse,
		'id' | 'username' | 'display_name' | 'email' | 'avatar_url'
	>

	const chrome = useSystemChrome()

	let actionPending = $state<Set<string>>(new Set())

	onMount(() => {
		void friends.load()
	})

	$effect(() => {
		chrome.setContextActions(islandContextActions)
		return () => chrome.setContextActions(null)
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

	async function handleCancel(request: FriendshipDetail) {
		actionPending = new Set([...actionPending, request.id])
		try {
			await friends.cancelRequest(request.id)
		} finally {
			actionPending = new Set([...actionPending].filter((id) => id !== request.id))
		}
	}

	function confirmRemoveFriend(friend: FriendResponse) {
		// unfriending is not undoable and the button sits next to "message",
		// so it asks first rather than acting on a stray click
		modals.open('confirm-delete', {
			title: `remove ${userLabel(friend)}?`,
			description: 'you will no longer be friends. you can send a new request later.',
			confirmLabel: 'unfriend',
			pendingLabel: 'removing',
			confirmIcon: UserMinus,
			onDelete: async () => {
				actionPending = new Set([...actionPending, friend.id])
				try {
					await friends.removeFriend(friend.id)
				} finally {
					actionPending = new Set([...actionPending].filter((id) => id !== friend.id))
				}
			},
		})
	}

	async function handleMessage(friend: FriendResponse) {
		const existing = messages.conversations.find((thread) =>
			(thread.participants ?? []).some((p) => p.kind === 'user' && p.user.id === friend.id)
		)
		if (existing) {
			void goto(resolve(`/c/${existing.id}`))
			return
		}
		actionPending = new Set([...actionPending, friend.id])
		try {
			const thread = await messages.createThread({ member_user_ids: [friend.id] })
			if (thread) void goto(resolve(`/c/${thread.id}`))
		} finally {
			actionPending = new Set([...actionPending].filter((id) => id !== friend.id))
		}
	}

	function userLabel(user: SocialUser): string {
		return userDisplayName(user) ?? user.id
	}

	function userMeta(user: SocialUser): string {
		return userHandleOrId(user) ?? user.id
	}

	const ACTION_BUTTON =
		'rounded-pill flex shrink-0 cursor-pointer items-center gap-1.5 border px-4 py-2.5 text-sm font-semibold transition-colors active:scale-[0.97]'
	const ACCEPT_TONE =
		'border-green-500/25 bg-green-500/15 text-green-600 hover:bg-green-500/25 dark:text-green-400'
	const DANGER_TONE =
		'border-red-500/25 bg-red-500/15 text-red-600 hover:bg-red-500/25 dark:text-red-400'
	const NEUTRAL_TONE =
		'border-foreground/10 bg-foreground/5 text-foreground/80 hover:bg-foreground/10 hover:text-foreground'
</script>

{#snippet islandContextActions()}
	<button
		type="button"
		class="flex cursor-pointer items-center justify-center opacity-80 transition-all duration-150 hover:scale-[1.05] hover:opacity-100 active:scale-[0.97]"
		onclick={() => modals.open('add-friends')}
		aria-label="add friend"
	>
		<UserPlus />
	</button>
{/snippet}

<!-- the person, as a pill. actions live OUTSIDE it so they read as controls
     rather than decoration on a row that is itself a link to the profile. -->
{#snippet personRow(user: SocialUser)}
	{@const label = userLabel(user)}
	<div
		class="bg-foreground/8 hover:bg-foreground/12 rounded-pill flex min-w-0 flex-1 items-center gap-3 p-3 transition-colors"
	>
		<button
			type="button"
			class="shrink-0 cursor-pointer"
			onclick={() => navigateToProfile(user.id)}
			aria-label="open profile"
		>
			{#if user.avatar_url}
				<img
					src={user.avatar_url}
					alt={label}
					class="h-11 w-11 rounded-full object-cover"
				/>
			{:else}
				<div
					class="text-foreground/90 flex h-11 w-11 items-center justify-center rounded-full text-sm font-semibold"
					style="background-color: var(--accent-primary);"
				>
					{getUserInitials(label)}
				</div>
			{/if}
		</button>
		<button
			type="button"
			class="flex min-w-0 flex-1 cursor-pointer flex-col text-left"
			onclick={() => navigateToProfile(user.id)}
		>
			<span class="text-foreground truncate text-sm font-medium">{label}</span>
			<span class="text-foreground/50 truncate text-xs">{userMeta(user)}</span>
		</button>
	</div>
{/snippet}

<div class="flex flex-1 flex-col gap-6">
	<!-- a failed load shows why, not a skeleton that never resolves -->
	{#if !friends.hasLoaded && !friends.error}
		<section class="flex flex-col gap-2">
			<Skeleton shape="lines" lines={1} width="9rem" />
			<div class="flex flex-col gap-2">
				{#each [0, 1, 2, 3, 4] as row (row)}
					<div class="flex items-center gap-2">
						<Skeleton
							shape="row"
							lines={2}
							height="4.25rem"
							radius="pill"
							class="min-w-0 flex-1"
						/>
						<Skeleton shape="pill" width="7rem" height="2.6rem" class="shrink-0" />
					</div>
				{/each}
			</div>
		</section>
	{:else if friends.error && !friends.hasContent}
		<div
			class="flex flex-1 flex-col items-center justify-center"
			style="view-transition-name: social-empty-state;"
		>
			<EmptyState
				label="could not load friends"
				description="check your connection - your friends will show up once it is back"
			>
				{#snippet icon()}<Users variant="solid" class="size-6" />{/snippet}
			</EmptyState>
		</div>
	{:else if !friends.hasContent}
		<div
			class="flex flex-1 flex-col items-center justify-center"
			style="view-transition-name: social-empty-state;"
		>
			<EmptyState
				label="no friends yet"
				description="add friends to share notes, start conversations, and collaborate together"
			>
				{#snippet icon()}<Users variant="solid" class="size-6" />{/snippet}
			</EmptyState>
		</div>
	{:else}
		<!-- incoming requests -->
		{#if friends.incoming.length > 0}
			<section class="flex flex-col gap-2">
				<h2 class="text-foreground/40 text-xs font-semibold tracking-wide uppercase">
					incoming requests
				</h2>
				<div class="flex flex-col gap-2">
					{#each friends.incoming as request (request.id)}
						{@const user = request.requester}
						{#if user}
							<div class="flex items-center gap-2">
								{@render personRow(user)}
								{#if actionPending.has(request.id)}
									<ShimmerText className="shrink-0 text-sm">pending</ShimmerText>
								{:else}
									<button
										type="button"
										class="{ACTION_BUTTON} {ACCEPT_TONE}"
										onclick={() => handleAccept(request)}
									>
										<Check class="h-4 w-4" strokeWidth="2.5" />
										accept
									</button>
									<button
										type="button"
										class="{ACTION_BUTTON} {DANGER_TONE}"
										onclick={() => handleDecline(request)}
									>
										<XMark class="h-4 w-4" />
										decline
									</button>
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
				<div class="flex flex-col gap-2">
					{#each friends.outgoing as request (request.id)}
						{@const user = request.addressee}
						{#if user}
							<div class="flex items-center gap-2">
								{@render personRow(user)}
								{#if actionPending.has(request.id)}
									<ShimmerText className="shrink-0 text-sm">pending</ShimmerText>
								{:else}
									<!-- a lone action is never worth a menu: it would cost two
									     taps to reach a list of one -->
									<button
										type="button"
										class="{ACTION_BUTTON} {DANGER_TONE}"
										onclick={() => handleCancel(request)}
									>
										<XMark class="h-4 w-4" />
										cancel
									</button>
								{/if}
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
				<div class="flex flex-col gap-2">
					{#each friends.list as friend (friend.id)}
						<div class="flex items-center gap-2" data-row>
							{@render personRow(friend)}
							{#if actionPending.has(friend.id)}
								<ShimmerText className="shrink-0 text-sm">pending</ShimmerText>
							{:else if device.isMobile}
								<PersonRowMenu label="friend options">
									{#snippet children(closeMenu)}
										<MenuItem
											icon={ChatBubble}
											onclick={() => {
												closeMenu()
												void handleMessage(friend)
											}}
										>
											message
										</MenuItem>
										<MenuItem
											destructive
											icon={UserMinus}
											onclick={() => {
												closeMenu()
												confirmRemoveFriend(friend)
											}}
										>
											unfriend
										</MenuItem>
									{/snippet}
								</PersonRowMenu>
							{:else}
								<button
									type="button"
									class="{ACTION_BUTTON} {NEUTRAL_TONE}"
									onclick={() => handleMessage(friend)}
								>
									<ChatBubble class="h-4 w-4" strokeWidth="2" />
									message
								</button>
								<button
									type="button"
									class="{ACTION_BUTTON} {DANGER_TONE}"
									onclick={() => confirmRemoveFriend(friend)}
								>
									<UserMinus class="h-4 w-4" strokeWidth="2" />
									unfriend
								</button>
							{/if}
						</div>
					{/each}
				</div>
			</section>
		{/if}
	{/if}
</div>
