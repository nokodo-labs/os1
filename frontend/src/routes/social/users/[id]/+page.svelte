<script lang="ts">
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import { page } from '$app/state'
	import { api } from '$lib/api/client'
	import Camera from '$lib/components/icons/Camera.svelte'
	import ChevronLeft from '$lib/components/icons/ChevronLeft.svelte'
	import PencilSquare from '$lib/components/icons/PencilSquare.svelte'
	import UserGroup from '$lib/components/icons/UserGroup.svelte'
	import NokodoLoader from '$lib/components/NokodoLoader.svelte'
	import { DropdownSelect } from '$lib/components/primitives'
	import { useSystemChrome } from '$lib/contexts/systemChromeContext.svelte'
	import { preferences } from '$lib/stores/preferences.svelte'
	import { session } from '$lib/stores/session.svelte'
	import { debounce, getUserInitials } from '$lib/utils'
	import { userDisplayName } from '$lib/utils/resourceAuthors'
	import { onMount } from 'svelte'

	const chrome = useSystemChrome()

	const userId = $derived(page.params.id ?? '')
	const isOwnProfile = $derived(session.currentUser?.id === userId)

	let editing = $state(false)
	let profileUser = $state<Record<string, unknown> | null>(null)
	let friendsCount = $state(0)
	let isLoading = $state(true)

	// edit fields
	let editDisplayName = $state('')
	let editUsername = $state('')
	let editBio = $state('')
	let editBirthDate = $state('')
	let editGender = $state('')

	// derived display values
	const user = $derived(isOwnProfile ? session.currentUser : profileUser)
	const displayName = $derived(
		userDisplayName({
			id: userId,
			display_name: typeof user?.display_name === 'string' ? user.display_name : null,
			username: typeof user?.username === 'string' ? user.username : null,
		}) ?? userId
	)
	const displayUsername = $derived((user?.username as string) ?? '')
	const displayAvatar = $derived(
		isOwnProfile ? session.userDisplay?.avatar : ((user?.avatar_url as string) ?? null)
	)
	const displayBio = $derived((user?.bio as string) ?? '')

	const displayGender = $derived(
		isOwnProfile
			? (preferences.data.account.gender ?? '')
			: ((profileUser?.gender as string) ?? '')
	)

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

	const genderOptions = [
		{ value: '', label: 'prefer not to say' },
		{ value: 'male', label: 'male' },
		{ value: 'female', label: 'female' },
		{ value: 'non-binary', label: 'non-binary' },
		{ value: 'other', label: 'other' },
	]

	onMount(async () => {
		await fetchProfile()
	})

	async function fetchProfile() {
		isLoading = true
		try {
			if (isOwnProfile) {
				const { data: friends } = await api.GET('/v1/users/{user_id}/friends', {
					params: { path: { user_id: userId } },
				})
				friendsCount = Array.isArray(friends) ? friends.length : 0
			} else {
				const { data } = await api.GET('/v1/users/{user_id}', {
					params: { path: { user_id: userId } },
				})
				if (data) profileUser = data as Record<string, unknown>
			}
		} catch {
			// silently handle
		} finally {
			isLoading = false
		}
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

	$effect(() => {
		chrome.setContextActions(islandBackAction)
		return () => chrome.setContextActions(null)
	})
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

<div
	class="absolute inset-0 overflow-y-auto"
	style="padding-top: calc(var(--chrome-island-offset, 0px) + var(--spacing-island-content));"
>
	<div
		class="pb-10"
		style="padding-left: var(--spacing-page-x); padding-right: var(--spacing-page-x);"
	>
		{#if isLoading}
			<div class="flex min-h-[45vh] items-center justify-center">
				<NokodoLoader className="opacity-70" expanded={false} />
			</div>
		{:else if !isOwnProfile && !profileUser}
			<div class="bg-foreground/5 rounded-2xl p-6 text-center">
				<p class="text-foreground/50 text-sm">profile not found</p>
			</div>
		{:else if editing && isOwnProfile}
			<!-- edit mode -->
			<div class="flex flex-col items-center gap-4 py-6">
				<button
					type="button"
					class="group relative h-24 w-24 shrink-0 cursor-pointer overflow-hidden rounded-full border-none bg-transparent"
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
							class="text-foreground flex h-full w-full items-center justify-center text-2xl font-bold uppercase"
							style="background: linear-gradient(to bottom right, var(--accent-primary), color-mix(in srgb, var(--accent-primary) 60%, black));"
						>
							{getUserInitials(editDisplayName || 'U')}
						</div>
					{/if}
					<div
						class="absolute inset-0 flex items-center justify-center bg-black/50 opacity-0 transition-opacity group-hover:opacity-100"
					>
						<Camera class="text-foreground h-5 w-5" />
					</div>
				</button>

				<button
					class="interactive text-accent-primary text-sm font-medium"
					onclick={stopEditing}
				>
					done
				</button>
			</div>

			<div class="mx-auto max-w-md space-y-4">
				<div class="rounded-container bg-foreground/5 p-5">
					<label
						class="text-foreground/50 mb-1.5 block text-xs font-medium"
						for="edit-name">display name</label
					>
					<input
						id="edit-name"
						type="text"
						class="rounded-pill border-foreground/10 bg-foreground/5 text-foreground/90 placeholder:text-foreground/40 focus:border-foreground/20 focus:bg-foreground/8 w-full border px-4 py-2.5 text-sm transition-colors outline-none"
						placeholder="your name"
						bind:value={editDisplayName}
						oninput={() => saveDisplayName(editDisplayName)}
					/>
				</div>

				<div class="rounded-container bg-foreground/5 p-5">
					<label
						class="text-foreground/50 mb-1.5 block text-xs font-medium"
						for="edit-username">username</label
					>
					<input
						id="edit-username"
						type="text"
						class="rounded-pill border-foreground/10 bg-foreground/5 text-foreground/90 placeholder:text-foreground/40 focus:border-foreground/20 focus:bg-foreground/8 w-full border px-4 py-2.5 text-sm transition-colors outline-none"
						placeholder="3-30 characters, letters, numbers, . and _"
						bind:value={editUsername}
						oninput={() => saveUsername(editUsername)}
					/>
				</div>

				<div class="rounded-container bg-foreground/5 p-5">
					<label
						class="text-foreground/50 mb-1.5 block text-xs font-medium"
						for="edit-bio">bio</label
					>
					<textarea
						id="edit-bio"
						class="border-foreground/10 bg-foreground/5 text-foreground/90 placeholder:text-foreground/40 focus:border-foreground/20 focus:bg-foreground/8 w-full resize-none rounded-xl border px-4 py-3 text-sm transition-colors outline-none"
						rows="3"
						maxlength={500}
						placeholder="tell others a bit about yourself..."
						bind:value={editBio}
						oninput={() => saveBio(editBio)}
					></textarea>
					<div class="text-foreground/30 mt-1 text-right text-xs">
						{editBio.length}/500
					</div>
				</div>

				<div class="rounded-container bg-foreground/5 p-5">
					<label
						class="text-foreground/50 mb-1.5 block text-xs font-medium"
						for="edit-birthdate">birth date</label
					>
					<input
						id="edit-birthdate"
						type="date"
						class="rounded-pill border-foreground/10 bg-foreground/5 text-foreground/90 focus:border-foreground/20 focus:bg-foreground/8 w-full border px-4 py-2.5 text-sm scheme-dark transition-colors outline-none"
						value={editBirthDate}
						onchange={(e) => {
							editBirthDate = e.currentTarget.value
							saveBirthDate(editBirthDate)
						}}
					/>
				</div>

				<div class="rounded-container bg-foreground/5 p-5">
					<label
						class="text-foreground/50 mb-1.5 block text-xs font-medium"
						for="edit-gender">gender</label
					>
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
			</div>
		{:else}
			<!-- view mode -->
			<div class="flex flex-col items-center gap-4 py-6">
				{#if displayAvatar}
					<img
						src={displayAvatar}
						alt={displayName}
						class="ring-foreground/10 h-24 w-24 rounded-full object-cover ring-2"
					/>
				{:else}
					<div
						class="text-foreground flex h-24 w-24 items-center justify-center rounded-full text-2xl font-bold uppercase"
						style="background: linear-gradient(to bottom right, var(--accent-primary), color-mix(in srgb, var(--accent-primary) 60%, black));"
					>
						{getUserInitials(displayName || userId)}
					</div>
				{/if}

				<div class="flex flex-col items-center gap-1 text-center">
					<h1 class="text-foreground text-xl font-bold">
						{displayName || userId}
					</h1>
					{#if displayUsername}
						<p class="text-foreground/50 text-sm">@{displayUsername}</p>
					{/if}
				</div>

				<!-- stats row -->
				{#if isOwnProfile}
					<div class="flex items-center gap-8 py-2">
						<button
							type="button"
							class="flex cursor-pointer flex-col items-center gap-0.5 border-none bg-transparent"
							onclick={() =>
								goto(resolve('/social/friends'), {
									keepFocus: true,
									noScroll: true,
								})}
						>
							<span class="text-foreground text-lg font-bold">{friendsCount}</span>
							<span class="text-foreground/50 text-xs">friends</span>
						</button>
					</div>
				{/if}

				<!-- bio -->
				{#if displayBio}
					<p class="text-foreground/70 max-w-sm text-center text-sm">{displayBio}</p>
				{/if}

				<!-- meta tags -->
				{#if displayGender || displayAge}
					<div class="text-foreground/40 flex items-center gap-3 text-xs">
						{#if displayGender}
							<span>{displayGender}</span>
						{/if}
						{#if displayGender && displayAge}
							<span>-</span>
						{/if}
						{#if displayAge}
							<span>{displayAge} years old</span>
						{/if}
					</div>
				{/if}

				{#if isOwnProfile}
					<button
						class="interactive bg-foreground/8 text-foreground hover:bg-foreground/12 flex items-center gap-2 rounded-full px-4 py-2.5 text-sm font-medium"
						onclick={startEditing}
					>
						<PencilSquare class="h-4 w-4" />
						<span>edit profile</span>
					</button>
				{/if}
			</div>

			<div class="mt-4 flex flex-col gap-6">
				<section class="flex flex-col gap-3">
					<div class="flex items-center gap-2">
						<UserGroup class="text-foreground/50 h-4 w-4" />
						<h2 class="text-foreground/60 text-sm font-semibold">mutual groups</h2>
					</div>
					<div class="bg-foreground/5 rounded-2xl py-8 text-center">
						<p class="text-foreground/40 text-sm">
							groups you both belong to will appear here
						</p>
					</div>
				</section>
			</div>
		{/if}
	</div>
</div>
