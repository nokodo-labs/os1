<script lang="ts">
	import ShimmerText from '$lib/components/effects/ShimmerText.svelte'
	import EmptyState from '$lib/components/EmptyState.svelte'
	import Plus from '$lib/components/icons/Plus.svelte'
	import Search from '$lib/components/icons/Search.svelte'
	import Trash from '$lib/components/icons/Trash.svelte'
	import User from '$lib/components/icons/User.svelte'
	import UserGroup from '$lib/components/icons/UserGroup.svelte'
	import BaseModal from '$lib/components/modals/BaseModal.svelte'
	import type { UserPick } from '$lib/components/resource-access/resourceAccessModal'
	import { friends } from '$lib/stores/friends.svelte'
	import { groups } from '$lib/stores/groups.svelte'
	import { showError } from '$lib/stores/notifications.svelte'
	import { session } from '$lib/stores/session.svelte'
	import { userDisplayName } from '$lib/utils/resourceAuthors'

	interface CreateGroupModalProps {
		open: boolean
		onClose: () => void
	}

	let { open, onClose }: CreateGroupModalProps = $props()

	let name = $state('')
	let peopleQuery = $state('')
	let peopleResults = $state<UserPick[]>([])
	let selectedPeople = $state<UserPick[]>([])
	let isCreating = $state(false)
	let peopleSearchDebounce: ReturnType<typeof setTimeout> | null = null

	const currentUserId = $derived(session.currentUserId)
	const panelClass =
		'border-foreground/12 bg-foreground/4 rounded-[18px] border shadow-[inset_0_1px_0_rgb(255_255_255/0.05)]'
	const inputClass =
		'bg-foreground/8 text-foreground ring-foreground/10 placeholder:text-foreground/30 min-w-0 rounded-full px-4 py-3 text-sm ring-1 transition-all outline-none focus:ring-(--accent-primary)/50 disabled:cursor-not-allowed disabled:opacity-55'
	const selectableUserIds = $derived(new Set(selectedPeople.map((person) => person.id)))
	const filteredFriends = $derived(
		friends.list.filter(
			(friend) => isSelectableUser(friend) && userMatchesQuery(friend, peopleQuery)
		)
	)
	const filteredPeopleResults = $derived(
		peopleResults.filter((person) => isSelectableUser(person))
	)

	function userLabel(user: UserPick): string {
		return userDisplayName(user) ?? user.id
	}

	function isSelectableUser(user: UserPick): boolean {
		if (user.id === currentUserId) return false
		return !selectableUserIds.has(user.id)
	}

	function userMatchesQuery(user: UserPick, query: string): boolean {
		const trimmed = query.trim().toLowerCase()
		if (!trimmed) return true
		return [user.display_name, user.username, user.email, user.id]
			.filter(Boolean)
			.some((value) => value?.toLowerCase().includes(trimmed))
	}

	async function searchPeople(query: string): Promise<void> {
		const trimmed = query.trim()
		if (!trimmed) {
			peopleResults = []
			return
		}
		peopleResults = await friends.searchUsers(trimmed, 10)
	}

	function handlePeopleSearchInput(event: Event): void {
		const target = event.currentTarget
		if (!(target instanceof HTMLInputElement)) return
		peopleQuery = target.value
		if (peopleSearchDebounce) clearTimeout(peopleSearchDebounce)
		peopleSearchDebounce = setTimeout(() => void searchPeople(peopleQuery), 250)
	}

	function addPerson(user: UserPick): void {
		if (!isSelectableUser(user)) return
		selectedPeople = [...selectedPeople, user]
		peopleQuery = ''
		peopleResults = []
	}

	function removePerson(userId: string): void {
		selectedPeople = selectedPeople.filter((person) => person.id !== userId)
	}

	async function handleCreate() {
		const trimmed = name.trim()
		if (!trimmed) return
		isCreating = true
		try {
			const created = await groups.create({ name: trimmed })
			if (!created) {
				showError('could not create group')
				return
			}
			let failedAdds = 0
			for (const person of selectedPeople) {
				const member = await groups.addMember(created.id, {
					user_id: person.id,
					role: 'member',
				})
				if (!member) failedAdds += 1
			}
			name = ''
			peopleQuery = ''
			peopleResults = []
			selectedPeople = []
			onClose()
			void groups.load({ force: true })
			if (failedAdds > 0) showError('group created, but some people were not added')
		} catch {
			showError('could not create group')
		} finally {
			isCreating = false
		}
	}

	function handleKeyDown(e: KeyboardEvent) {
		if (e.key === 'Enter') {
			e.preventDefault()
			handleCreate()
		}
	}

	$effect(() => {
		if (open) void friends.load()
	})

	$effect(() => {
		if (!open) {
			name = ''
			peopleQuery = ''
			peopleResults = []
			selectedPeople = []
			isCreating = false
			if (peopleSearchDebounce) clearTimeout(peopleSearchDebounce)
			peopleSearchDebounce = null
		}
	})
</script>

<BaseModal
	{open}
	title="new group"
	description="create a group to collaborate with others"
	{onClose}
>
	<div class="flex flex-col gap-4">
		<div class="flex items-center gap-4">
			<div
				class="flex h-14 w-14 shrink-0 items-center justify-center rounded-full bg-(--accent-primary)/10"
			>
				<UserGroup class="h-7 w-7 text-(--accent-primary)" variant="solid" />
			</div>
			<input
				class="{inputClass} flex-1"
				type="text"
				placeholder="group name"
				bind:value={name}
				onkeydown={handleKeyDown}
				disabled={isCreating}
			/>
		</div>

		<section class="{panelClass} p-4">
			<div class="mb-3 flex items-center justify-between gap-3">
				<div class="flex items-center gap-2">
					<User class="text-foreground/50 h-4 w-4" />
					<p class="text-foreground/90 text-sm font-semibold">people</p>
				</div>
				<p class="text-foreground/45 text-xs">{selectedPeople.length} selected</p>
			</div>

			<div class="relative">
				<Search
					class="text-foreground/35 absolute top-1/2 left-3.5 h-4 w-4 -translate-y-1/2"
				/>
				<input
					class="{inputClass} w-full pr-4 pl-10"
					type="text"
					placeholder="search people"
					value={peopleQuery}
					oninput={handlePeopleSearchInput}
					onkeydown={(event) => {
						if (event.key === 'Enter') event.preventDefault()
					}}
					disabled={isCreating}
				/>
			</div>

			{#if filteredPeopleResults.length > 0}
				<div class="border-foreground/10 bg-foreground/4 mt-2 rounded-[18px] border py-1">
					{#each filteredPeopleResults as person (person.id)}
						<button
							type="button"
							class="rounded-pill text-foreground/80 hover:bg-foreground/8 mx-1 flex w-[calc(100%-0.5rem)] cursor-pointer items-center gap-3 px-3 py-2.5 text-sm transition-colors disabled:cursor-not-allowed disabled:opacity-55"
							onclick={() => addPerson(person)}
							disabled={isCreating}
						>
							<div
								class="bg-foreground/10 flex h-8 w-8 shrink-0 items-center justify-center rounded-full"
							>
								<User class="h-4 w-4" />
							</div>
							<span class="min-w-0 flex-1 truncate text-left"
								>{userLabel(person)}</span
							>
							<Plus class="text-foreground/40 h-4 w-4" />
						</button>
					{/each}
				</div>
			{/if}

			{#if filteredFriends.length > 0}
				<div class="mt-3">
					<p class="text-foreground/40 mb-2 text-xs">
						{peopleQuery ? 'matching friends' : 'friends'}
					</p>
					<div class="flex flex-wrap gap-2">
						{#each filteredFriends as friend (friend.id)}
							<button
								type="button"
								class="rounded-pill border-foreground/12 text-foreground/80 hover:bg-foreground/6 inline-flex min-h-9 cursor-pointer items-center justify-center gap-1.5 border bg-transparent px-4 text-sm font-semibold transition-all duration-150 active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-55"
								onclick={() => addPerson(friend)}
								disabled={isCreating}
							>
								<User class="h-4 w-4" />
								<span class="max-w-36 truncate">{userLabel(friend)}</span>
								<Plus class="text-foreground/40 h-3.5 w-3.5" />
							</button>
						{/each}
					</div>
				</div>
			{/if}

			<div class="mt-4 flex flex-col gap-2">
				{#if selectedPeople.length === 0}
					<EmptyState label="no people selected" compact />
				{:else}
					{#each selectedPeople as person (person.id)}
						<div
							class="border-foreground/10 bg-foreground/4 flex items-center gap-3 rounded-[18px] border px-3 py-2.5"
						>
							<div
								class="bg-foreground/10 flex h-8 w-8 shrink-0 items-center justify-center rounded-full"
							>
								<User class="h-4 w-4" />
							</div>
							<span class="text-foreground/80 min-w-0 flex-1 truncate text-sm">
								{userLabel(person)}
							</span>
							<button
								type="button"
								class="text-foreground/30 cursor-pointer transition-colors hover:text-red-400 disabled:cursor-not-allowed disabled:opacity-55"
								onclick={() => removePerson(person.id)}
								aria-label="remove"
								disabled={isCreating}
							>
								<Trash class="h-4 w-4" />
							</button>
						</div>
					{/each}
				{/if}
			</div>
		</section>

		<button
			class="interactive w-full rounded-full bg-(--accent-primary)/20 py-3 text-sm font-medium text-(--accent-primary) hover:bg-(--accent-primary)/30 disabled:pointer-events-none disabled:opacity-50"
			type="button"
			onclick={handleCreate}
			disabled={!name.trim() || isCreating}
		>
			{#if isCreating}
				<ShimmerText>creating</ShimmerText>
			{:else}
				create group
			{/if}
		</button>
	</div>
</BaseModal>
