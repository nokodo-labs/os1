<script lang="ts">
	import { browser } from '$app/environment'
	import { goto } from '$app/navigation'
	import { base, resolve } from '$app/paths'
	import { page } from '$app/state'
	import { api } from '$lib/api/client'
	import type { components } from '$lib/api/types'
	import ShimmerText from '$lib/components/effects/ShimmerText.svelte'
	import EmptyState from '$lib/components/EmptyState.svelte'
	import Camera from '$lib/components/icons/Camera.svelte'
	import ChatBubble from '$lib/components/icons/ChatBubble.svelte'
	import Check from '$lib/components/icons/Check.svelte'
	import ChevronLeft from '$lib/components/icons/ChevronLeft.svelte'
	import ChevronRight from '$lib/components/icons/ChevronRight.svelte'
	import LockClosed from '$lib/components/icons/LockClosed.svelte'
	import PencilSquare from '$lib/components/icons/PencilSquare.svelte'
	import Share from '$lib/components/icons/Share.svelte'
	import UserCircle from '$lib/components/icons/UserCircle.svelte'
	import UserGroup from '$lib/components/icons/UserGroup.svelte'
	import UserMinus from '$lib/components/icons/UserMinus.svelte'
	import UserPlus from '$lib/components/icons/UserPlus.svelte'
	import XMark from '$lib/components/icons/XMark.svelte'
	import { ActionTile, DropdownSelect, Skeleton } from '$lib/components/primitives'
	import { useSystemChrome } from '$lib/contexts/systemChromeContext.svelte'
	import { friends } from '$lib/stores/friends.svelte'
	import { groups, type Group } from '$lib/stores/groups.svelte'
	import { messages } from '$lib/stores/messages.svelte'
	import { modals } from '$lib/stores/modals.svelte'
	import { notifications, showError } from '$lib/stores/notifications.svelte'
	import { preferences } from '$lib/stores/preferences.svelte'
	import { session } from '$lib/stores/session.svelte'
	import { debounce, getUserInitials } from '$lib/utils'
	import { userDisplayName } from '$lib/utils/resourceAuthors'

	type User = components['schemas']['User']

	const chrome = useSystemChrome()

	const userId = $derived(page.params.id ?? '')
	const isOwnProfile = $derived(session.currentUserId === userId)

	let editing = $state(false)
	let profileUser = $state<User | null>(null)
	let isLoading = $state(true)
	let mutualGroups = $state<Group[]>([])
	let isBlocked = $state(false)
	let pendingAction = $state<string | null>(null)

	// edit fields
	let editDisplayName = $state('')
	let editUsername = $state('')
	let editBio = $state('')
	let editBirthDate = $state('')
	let editGender = $state('')

	// identity: own profile reads the session record; anyone else is limited to
	// what the bulk lookup returns, plus the full record when the API allows it.
	const summary = $derived(isOwnProfile ? null : session.getUserSummary(userId))
	const user = $derived(isOwnProfile ? session.currentUser : (profileUser ?? summary))
	const notFound = $derived(!isOwnProfile && !user)
	const displayName = $derived(
		userDisplayName({
			id: userId,
			display_name: user?.display_name ?? null,
			username: user?.username ?? null,
		}) ?? userId
	)
	const displayUsername = $derived(user?.username ?? '')
	const displayAvatar = $derived(
		isOwnProfile ? (session.userDisplay?.avatar ?? null) : (user?.avatar_url ?? null)
	)
	const displayBio = $derived(
		isOwnProfile ? (session.currentUser?.bio ?? '') : (profileUser?.bio ?? '')
	)
	const displayGender = $derived(isOwnProfile ? (preferences.data.account.gender ?? '') : '')

	const displayAge = $derived.by(() => {
		const bd = isOwnProfile ? preferences.data.account.birthDate : null
		if (!bd) return null
		const birth = new Date(bd)
		const today = new Date()
		let age = today.getFullYear() - birth.getFullYear()
		const m = today.getMonth() - birth.getMonth()
		if (m < 0 || (m === 0 && today.getDate() < birth.getDate())) age--
		return age > 0 ? age : null
	})

	const relationship = $derived(isOwnProfile ? null : friends.getRelationship(userId))
	const isFriend = $derived(relationship?.kind === 'accepted')
	const sharedThreads = $derived(
		isOwnProfile
			? []
			: messages.conversations.filter((thread) =>
					(thread.participants ?? []).some(
						(part) => part.kind === 'user' && part.user.id === userId
					)
				)
	)
	const groupList = $derived(isOwnProfile ? groups.list : mutualGroups)
	const hasAbout = $derived(Boolean(displayBio || displayGender || displayAge))

	const shareUrl = $derived.by(() => {
		const path = `${base}/social/users/${userId}`
		return browser ? new URL(path, window.location.origin).toString() : path
	})

	const genderOptions = [
		{ value: '', label: 'prefer not to say' },
		{ value: 'male', label: 'male' },
		{ value: 'female', label: 'female' },
		{ value: 'non-binary', label: 'non-binary' },
		{ value: 'other', label: 'other' },
	]

	// one load per visited profile: the effect must not refire on its own writes.
	let loadedUserId: string | null = null
	$effect(() => {
		const id = userId
		if (!id || loadedUserId === id) return
		loadedUserId = id
		void fetchProfile(id)
	})

	async function fetchProfile(id: string): Promise<void> {
		isLoading = true
		profileUser = null
		mutualGroups = []
		isBlocked = false
		editing = false
		try {
			await Promise.all([
				friends.load(),
				messages.load(),
				loadIdentity(id),
				loadGroups(id),
				loadBlockState(id),
			])
		} finally {
			isLoading = false
		}
	}

	async function loadIdentity(id: string): Promise<void> {
		if (isOwnProfile) return
		// the bulk lookup is the only user read everyone is allowed; the full
		// record answers for yourself and for operators, and carries the bio.
		await session.ensureUsers([id])
		const { data } = await api.GET('/v1/users/{user_id}', {
			params: { path: { user_id: id } },
		})
		if (data) profileUser = data
	}

	async function loadGroups(id: string): Promise<void> {
		if (isOwnProfile) {
			await groups.load()
			return
		}
		const { data } = await api.GET('/v1/groups', {
			params: { query: { member_user_id: id } },
		})
		mutualGroups = data ?? []
	}

	async function loadBlockState(id: string): Promise<void> {
		const me = session.currentUserId
		if (!me || me === id) return
		const { data } = await api.GET('/v1/users/{user_id}/blocks', {
			params: { path: { user_id: me } },
		})
		isBlocked = (data ?? []).some((block) => block.blocked_id === id)
	}

	function startEditing() {
		editDisplayName = displayName
		editUsername = displayUsername
		editBio = displayBio
		editBirthDate = preferences.data.account.birthDate ?? ''
		editGender = preferences.data.account.gender ?? ''
		editing = true
	}

	function stopEditing() {
		editing = false
	}

	const saveDisplayName = debounce(async (value: string) => {
		const uid = session.currentUser?.id
		if (!uid) return
		const { data: res } = await api.PATCH('/v1/users/{user_id}', {
			params: { path: { user_id: uid } },
			body: { display_name: value || null },
		})
		if (res) session.currentUser = { ...res }
	}, 600)

	const saveUsername = debounce(async (value: string) => {
		const uid = session.currentUser?.id
		if (!uid) return
		const { data: res } = await api.PATCH('/v1/users/{user_id}', {
			params: { path: { user_id: uid } },
			body: { username: value || undefined },
		})
		if (res) session.currentUser = { ...res }
	}, 600)

	const saveBio = debounce(async (value: string) => {
		const uid = session.currentUser?.id
		if (!uid) return
		const { data: res } = await api.PATCH('/v1/users/{user_id}', {
			params: { path: { user_id: uid } },
			body: { bio: value || null },
		})
		if (res) session.currentUser = { ...res }
	}, 600)

	function saveBirthDate(value: string): void {
		void preferences.update('account', { birthDate: value || null })
	}

	function saveGender(value: string): void {
		void preferences.update('account', { gender: value || null })
	}

	const handleBack = async () => {
		await goto(resolve('/social/friends'), { keepFocus: true, noScroll: true })
	}

	async function withPending(action: string, run: () => Promise<void>): Promise<void> {
		if (pendingAction) return
		pendingAction = action
		try {
			await run()
		} finally {
			pendingAction = null
		}
	}

	/** the friends-page DM flow: reuse the existing thread, else open a new one. */
	async function handleMessage(): Promise<void> {
		const existing = sharedThreads[0]
		if (existing) {
			await goto(resolve(`/c/${existing.id}`))
			return
		}
		await withPending('message', async () => {
			const thread = await messages.createThread({ member_user_ids: [userId] })
			if (thread) await goto(resolve(`/c/${thread.id}`))
			else showError('could not start a conversation')
		})
	}

	async function handleAddFriend(): Promise<void> {
		await withPending('add-friend', async () => {
			const sent = await friends.sendRequest(userId)
			if (sent) await friends.refresh()
			else showError('could not send the friend request')
		})
	}

	async function handleAcceptRequest(friendshipId: string): Promise<void> {
		await withPending('accept', async () => {
			await friends.acceptRequest(friendshipId)
			await friends.refresh()
		})
	}

	async function handleDeclineRequest(friendshipId: string): Promise<void> {
		await withPending('decline', async () => {
			await friends.declineRequest(friendshipId)
			await friends.refresh()
		})
	}

	async function handleCancelRequest(friendshipId: string): Promise<void> {
		await withPending('cancel', async () => {
			await friends.cancelRequest(friendshipId)
		})
	}

	async function handleShare(): Promise<void> {
		const canNativeShare =
			browser && typeof navigator !== 'undefined' && typeof navigator.share === 'function'
		if (canNativeShare) {
			try {
				await navigator.share({ title: displayName, text: displayName, url: shareUrl })
				return
			} catch (error) {
				if (error instanceof DOMException && error.name === 'AbortError') return
				showError('could not share')
				return
			}
		}
		try {
			await navigator.clipboard.writeText(shareUrl)
			notifications.pushEphemeralToast('success', 'link copied')
		} catch {
			showError('could not copy')
		}
	}

	// unfriending is not undoable, so it asks first - the friends-page dialog.
	function confirmRemoveFriend(): void {
		modals.open('confirm-delete', {
			title: `remove ${displayName}?`,
			description: 'you will no longer be friends. you can send a new request later.',
			confirmLabel: 'unfriend',
			pendingLabel: 'removing',
			confirmIcon: UserMinus,
			onDelete: async () => {
				await withPending('unfriend', async () => {
					if (await friends.removeFriend(userId)) await friends.refresh()
					else showError('could not remove this friend')
				})
			},
		})
	}

	function confirmBlock(): void {
		modals.open('confirm-delete', {
			title: `block ${displayName}?`,
			description:
				'they will not be able to find you, message you, or send you a friend request.',
			confirmLabel: 'block',
			pendingLabel: 'blocking',
			confirmIcon: LockClosed,
			onDelete: async () => {
				await withPending('block', async () => {
					const me = session.currentUserId
					if (!me) return
					const { error } = await api.POST('/v1/users/{user_id}/blocks', {
						params: { path: { user_id: me } },
						body: { blocked_id: userId },
					})
					if (error) showError('could not block this person')
					else isBlocked = true
				})
			},
		})
	}

	async function handleUnblock(): Promise<void> {
		await withPending('unblock', async () => {
			const me = session.currentUserId
			if (!me) return
			const { error } = await api.DELETE('/v1/users/{user_id}/blocks/{blocked_user_id}', {
				params: { path: { user_id: me, blocked_user_id: userId } },
			})
			if (error) showError('could not unblock this person')
			else isBlocked = false
		})
	}

	function openGroup(group: Group): void {
		void goto(resolve(`/social/groups/${group.id}`))
	}

	$effect(() => {
		chrome.setContextActions(islandBackAction)
		return () => chrome.setContextActions(null)
	})

	const panelClass =
		'border-foreground/13 bg-background/70 shadow-[inset_0_1px_0_rgb(255_255_255/0.08)] backdrop-blur-[16px] backdrop-saturate-[1.08]'
	const sectionClass = `${panelClass} grid min-w-0 gap-2 rounded-[18px] border p-3`
	const sectionTitleClass =
		'text-foreground/45 px-1 text-[0.68rem] font-semibold tracking-[0.14em] uppercase'
	const destructiveTitleClass =
		'px-1 text-[0.68rem] font-semibold tracking-[0.14em] text-red-500/75 uppercase dark:text-red-400/75'
	/** the app's destructive pill, as the confirm dialog draws it. */
	const destructivePillClass =
		'rounded-pill inline-flex cursor-pointer items-center justify-self-start border border-red-500/25 bg-red-500/20 px-4 py-2 text-sm text-red-100 transition-colors duration-150 hover:bg-red-500/30 disabled:cursor-not-allowed disabled:opacity-60'
	const quietPillClass =
		'rounded-pill border-foreground/12 text-foreground/80 hover:bg-foreground/6 inline-flex cursor-pointer items-center justify-self-start border bg-transparent px-4 py-2 text-sm transition-colors duration-150 disabled:cursor-not-allowed disabled:opacity-60'
	const detailRowClass = 'flex min-w-0 items-baseline gap-3 px-1 py-1.5'
	const detailLabelClass = 'text-foreground/45 w-24 shrink-0 text-xs'
	const detailValueClass = 'text-foreground/85 min-w-0 flex-1 text-sm wrap-break-word'
	const fieldLabelClass = 'text-foreground/50 px-1 text-xs font-medium'
	const inputClass =
		'rounded-pill border-foreground/10 bg-foreground/5 text-foreground/90 placeholder:text-foreground/40 focus:border-foreground/20 focus:bg-foreground/8 w-full border px-4 py-2.5 text-sm transition-colors outline-none'
	const textareaClass =
		'border-foreground/10 bg-foreground/5 text-foreground/90 placeholder:text-foreground/40 focus:border-foreground/20 focus:bg-foreground/8 w-full resize-none rounded-xl border px-4 py-3 text-sm transition-colors outline-none'
	const statClass =
		'flex min-w-0 flex-col items-center gap-0.5 border-none bg-transparent px-3 py-1'
	const groupRowClass =
		'hover:bg-foreground/6 flex w-full min-w-0 cursor-pointer items-center gap-3 rounded-xl px-1 py-1.5 text-left transition-colors'
</script>

{#snippet islandBackAction()}
	<button
		type="button"
		class="rounded-pill hover:text-foreground flex h-12 w-12 cursor-pointer items-center justify-center border-none bg-transparent transition-transform duration-150 hover:scale-[1.05] active:scale-[0.97]"
		onclick={handleBack}
		aria-label="back to friends"
	>
		<ChevronLeft class="h-5 w-5" strokeWidth="2" />
	</button>
{/snippet}

{#snippet stat(label: string, value: number, open: (() => void) | null)}
	{#if open}
		<button type="button" class="cursor-pointer {statClass}" data-stat={label} onclick={open}>
			<span class="text-foreground text-lg font-bold">{value}</span>
			<span class="text-foreground/50 text-xs">{label}</span>
		</button>
	{:else}
		<div class={statClass} data-stat={label}>
			<span class="text-foreground text-lg font-bold">{value}</span>
			<span class="text-foreground/50 text-xs">{label}</span>
		</div>
	{/if}
{/snippet}

{#snippet detail(label: string, value: string)}
	<div class={detailRowClass}>
		<span class={detailLabelClass}>{label}</span>
		<span class={detailValueClass}>{value}</span>
	</div>
{/snippet}

<div
	class="absolute inset-0 overflow-y-auto"
	style="padding-top: calc(var(--chrome-island-offset, 0px) + var(--spacing-island-content));"
>
	<div
		class="pb-10"
		style="padding-left: var(--spacing-page-x); padding-right: var(--spacing-page-x);"
	>
		<div class="mx-auto flex w-full max-w-xl flex-col gap-3">
			{#if isLoading}
				<div class="flex flex-col items-center gap-4 py-6">
					<Skeleton shape="avatar" width="8rem" height="8rem" />
					<div class="flex flex-col items-center gap-2">
						<Skeleton shape="pill" width="10rem" height="1.75rem" />
						<Skeleton shape="lines" lines={1} width="7rem" class="items-center" />
					</div>
					<div class="flex items-center gap-8 py-2">
						<Skeleton shape="lines" lines={2} width="3.5rem" class="items-center" />
					</div>
				</div>
				<Skeleton shape="block" height="6.5rem" />
			{:else if notFound}
				<!-- the scroller already pads for the island and the page bottom, so the
				     centring box has to discount BOTH or it sits low by that much -->
				<div
					class="flex items-center justify-center"
					style="min-height: calc(100dvh - 2 * (var(--chrome-island-offset, 0px) + var(--spacing-island-content)));"
				>
					<EmptyState
						label="profile not found"
						description="this person doesn't exist or their profile is private."
					>
						{#snippet icon()}<UserCircle class="h-10 w-10" />{/snippet}
					</EmptyState>
				</div>
			{:else}
				<header class="grid justify-items-center gap-3 pt-2 pb-1 text-center" data-identity>
					{#if editing && isOwnProfile}
						<button
							type="button"
							class="group ring-foreground/12 relative size-32 shrink-0 cursor-pointer overflow-hidden rounded-full border-none bg-transparent ring-2"
							aria-label="change profile picture"
						>
							{#if displayAvatar}
								<img
									src={displayAvatar}
									alt={displayName}
									class="h-full w-full object-cover"
								/>
							{:else}
								<div
									class="text-foreground flex h-full w-full items-center justify-center text-4xl font-bold uppercase"
									style="background: linear-gradient(to bottom right, var(--accent-primary), color-mix(in srgb, var(--accent-primary) 60%, black));"
								>
									{getUserInitials(editDisplayName || displayName)}
								</div>
							{/if}
							<div
								class="absolute inset-0 flex items-center justify-center bg-black/50 opacity-0 transition-opacity group-hover:opacity-100"
							>
								<Camera class="text-foreground h-6 w-6" />
							</div>
						</button>
					{:else if displayAvatar}
						<img
							src={displayAvatar}
							alt={displayName}
							class="ring-foreground/12 size-32 rounded-full object-cover shadow-[0_10px_28px_rgb(0_0_0/0.22)] ring-2"
						/>
					{:else}
						<div
							class="text-foreground ring-foreground/12 flex size-32 items-center justify-center rounded-full text-4xl font-bold uppercase shadow-[0_10px_28px_rgb(0_0_0/0.22)] ring-2"
							style="background: linear-gradient(to bottom right, var(--accent-primary), color-mix(in srgb, var(--accent-primary) 60%, black));"
						>
							{getUserInitials(displayName)}
						</div>
					{/if}

					<div class="grid w-full min-w-0 justify-items-center gap-1">
						<h1 class="text-foreground min-w-0 truncate text-2xl font-bold">
							{displayName}
						</h1>
						{#if displayUsername}
							<p class="text-foreground/50 min-w-0 truncate text-sm">
								@{displayUsername}
							</p>
						{/if}
						{#if isBlocked}
							<span
								class="rounded-pill mt-0.5 border border-red-500/25 bg-red-500/15 px-2.5 py-0.5 text-[0.68rem] font-medium text-red-600 dark:text-red-400"
							>
								blocked
							</span>
						{:else if isFriend}
							<span
								class="rounded-pill border-foreground/12 bg-foreground/6 text-foreground/60 mt-0.5 border px-2.5 py-0.5 text-[0.68rem] font-medium"
							>
								friends
							</span>
						{/if}
					</div>

					<div class="flex items-center justify-center gap-6 py-1" data-stats>
						{#if isOwnProfile}
							{@render stat('friends', friends.friendCount, () => {
								void goto(resolve('/social/friends'))
							})}
							{@render stat('groups', groupList.length, () => {
								void goto(resolve('/social/groups'))
							})}
						{:else}
							{@render stat('mutual groups', groupList.length, null)}
							{@render stat('chats', sharedThreads.length, () => {
								void goto(resolve('/messages'))
							})}
						{/if}
					</div>
				</header>

				<div class="flex flex-wrap items-start justify-center gap-2 pb-1" data-actions>
					{#if isOwnProfile}
						{#if editing}
							<ActionTile label="done" icon={Check} onclick={stopEditing} />
						{:else}
							<ActionTile
								label="edit profile"
								icon={PencilSquare}
								onclick={startEditing}
							/>
						{/if}
						<ActionTile label="share" icon={Share} onclick={handleShare} />
					{:else}
						<ActionTile
							label="message"
							icon={ChatBubble}
							onclick={() => void handleMessage()}
							disabled={isBlocked || pendingAction !== null}
							workingLabel={pendingAction === 'message' ? 'opening' : null}
						/>
						{#if relationship?.kind === 'pending_incoming'}
							{@const friendshipId = relationship.friendshipId}
							<ActionTile
								label="accept"
								icon={Check}
								onclick={() => void handleAcceptRequest(friendshipId)}
								disabled={pendingAction !== null}
								workingLabel={pendingAction === 'accept' ? 'accepting' : null}
							/>
							<ActionTile
								label="decline"
								icon={XMark}
								onclick={() => void handleDeclineRequest(friendshipId)}
								disabled={pendingAction !== null}
								workingLabel={pendingAction === 'decline' ? 'declining' : null}
							/>
						{:else if relationship?.kind === 'pending_outgoing'}
							{@const friendshipId = relationship.friendshipId}
							<ActionTile
								label="cancel request"
								icon={XMark}
								onclick={() => void handleCancelRequest(friendshipId)}
								disabled={pendingAction !== null}
								workingLabel={pendingAction === 'cancel' ? 'cancelling' : null}
							/>
						{:else if !isFriend}
							<ActionTile
								label="add friend"
								icon={UserPlus}
								onclick={() => void handleAddFriend()}
								disabled={isBlocked || pendingAction !== null}
								workingLabel={pendingAction === 'add-friend' ? 'sending' : null}
							/>
						{/if}
						<ActionTile label="share" icon={Share} onclick={handleShare} />
					{/if}
				</div>

				{#if editing && isOwnProfile}
					<section class={sectionClass} data-section="profile">
						<h2 class={sectionTitleClass}>profile</h2>
						<div class="grid gap-1.5">
							<label class={fieldLabelClass} for="edit-name">display name</label>
							<input
								id="edit-name"
								type="text"
								class={inputClass}
								placeholder="your name"
								bind:value={editDisplayName}
								oninput={() => saveDisplayName(editDisplayName)}
							/>
						</div>
						<div class="grid gap-1.5">
							<label class={fieldLabelClass} for="edit-username">username</label>
							<input
								id="edit-username"
								type="text"
								class={inputClass}
								placeholder="3-30 characters, letters, numbers, . and _"
								bind:value={editUsername}
								oninput={() => saveUsername(editUsername)}
							/>
						</div>
					</section>

					<section class={sectionClass} data-section="about">
						<h2 class={sectionTitleClass}>about</h2>
						<div class="grid gap-1.5">
							<label class={fieldLabelClass} for="edit-bio">bio</label>
							<textarea
								id="edit-bio"
								class={textareaClass}
								rows="3"
								maxlength={500}
								placeholder="tell others a bit about yourself..."
								bind:value={editBio}
								oninput={() => saveBio(editBio)}
							></textarea>
							<div class="text-foreground/30 px-1 text-right text-xs">
								{editBio.length}/500
							</div>
						</div>
						<div class="grid gap-1.5">
							<label class={fieldLabelClass} for="edit-birthdate">birth date</label>
							<input
								id="edit-birthdate"
								type="date"
								class="{inputClass} scheme-dark"
								value={editBirthDate}
								onchange={(e) => {
									editBirthDate = e.currentTarget.value
									saveBirthDate(editBirthDate)
								}}
							/>
						</div>
						<div class="grid gap-1.5">
							<span class={fieldLabelClass}>gender</span>
							<DropdownSelect
								options={genderOptions}
								value={editGender}
								onchange={(value) => {
									editGender = value
									saveGender(editGender)
								}}
								ariaLabel="gender"
							/>
						</div>
					</section>
				{:else}
					<section class={sectionClass} data-section="about">
						<h2 class={sectionTitleClass}>about</h2>
						{#if hasAbout}
							{#if displayBio}
								<p
									class="text-foreground/80 px-1 py-1 text-sm leading-6 wrap-break-word select-text"
								>
									{displayBio}
								</p>
							{/if}
							{#if displayGender}
								{@render detail('gender', displayGender)}
							{/if}
							{#if displayAge !== null}
								{@render detail('age', `${displayAge} years old`)}
							{/if}
						{:else}
							<EmptyState
								label={isOwnProfile ? 'no bio yet' : 'nothing shared yet'}
								description={isOwnProfile
									? 'edit your profile to tell others about yourself'
									: undefined}
								compact
							>
								{#snippet icon()}<UserCircle class="size-5" />{/snippet}
							</EmptyState>
						{/if}
					</section>
				{/if}

				<section class={sectionClass} data-section="groups">
					<h2 class={sectionTitleClass}>
						{isOwnProfile ? 'groups' : 'mutual groups'}
					</h2>
					{#if groupList.length > 0}
						<ul class="grid gap-0.5">
							{#each groupList as group (group.id)}
								<li class="min-w-0">
									<button
										type="button"
										class={groupRowClass}
										onclick={() => openGroup(group)}
									>
										<span
											class="bg-foreground/8 text-foreground/70 flex size-8 shrink-0 items-center justify-center rounded-full"
										>
											<UserGroup class="size-4" />
										</span>
										<span class="grid min-w-0 flex-1">
											<span
												class="text-foreground/85 min-w-0 truncate text-sm"
											>
												{group.name}
											</span>
											<span
												class="text-foreground/45 min-w-0 truncate text-xs"
											>
												{group.memberships.length === 1
													? '1 member'
													: `${group.memberships.length} members`}
											</span>
										</span>
										<ChevronRight class="text-foreground/30 size-4 shrink-0" />
									</button>
								</li>
							{/each}
						</ul>
					{:else}
						<EmptyState
							label={isOwnProfile ? 'no groups yet' : 'no groups in common'}
							compact
						>
							{#snippet icon()}<UserGroup class="size-5" />{/snippet}
						</EmptyState>
					{/if}
				</section>

				{#if !isOwnProfile}
					<section
						class="{sectionClass} border-red-500/22 bg-red-500/6"
						data-section="destructive"
					>
						<h2 class={destructiveTitleClass}>danger zone</h2>
						{#if isFriend}
							<button
								type="button"
								class={destructivePillClass}
								disabled={pendingAction !== null}
								onclick={confirmRemoveFriend}
							>
								<UserMinus class="h-4 w-4" />
								<span class="ml-2">
									{#if pendingAction === 'unfriend'}
										<ShimmerText className="inline-block">removing</ShimmerText>
									{:else}
										unfriend
									{/if}
								</span>
							</button>
						{/if}
						{#if isBlocked}
							<button
								type="button"
								class={quietPillClass}
								disabled={pendingAction !== null}
								onclick={() => void handleUnblock()}
							>
								<LockClosed class="h-4 w-4" />
								<span class="ml-2">
									{#if pendingAction === 'unblock'}
										<ShimmerText className="inline-block"
											>unblocking</ShimmerText
										>
									{:else}
										unblock
									{/if}
								</span>
							</button>
						{:else}
							<button
								type="button"
								class={destructivePillClass}
								disabled={pendingAction !== null}
								onclick={confirmBlock}
							>
								<LockClosed class="h-4 w-4" />
								<span class="ml-2">
									{#if pendingAction === 'block'}
										<ShimmerText className="inline-block">blocking</ShimmerText>
									{:else}
										block
									{/if}
								</span>
							</button>
						{/if}
					</section>
				{/if}
			{/if}
		</div>
	</div>
</div>
