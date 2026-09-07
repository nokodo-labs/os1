<script lang="ts">
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import ShimmerText from '$lib/components/effects/ShimmerText.svelte'
	import Check from '$lib/components/icons/Check.svelte'
	import Search from '$lib/components/icons/Search.svelte'
	import User from '$lib/components/icons/User.svelte'
	import BaseModal from '$lib/components/modals/BaseModal.svelte'
	import ModalActions from '$lib/components/modals/ModalActions.svelte'
	import { friends, type UserSearchResult } from '$lib/stores/friends.svelte'
	import { messages } from '$lib/stores/messages.svelte'
	import { showError } from '$lib/stores/notifications.svelte'
	import { session } from '$lib/stores/session.svelte'
	import { getUserInitials } from '$lib/utils'
	import { userDisplayName } from '$lib/utils/resourceAuthors'
	import { SvelteMap } from 'svelte/reactivity'

	interface Candidate {
		id: string
		display_name?: string | null
		username?: string | null
		avatar_url?: string | null
	}

	interface Props {
		open: boolean
		onClose: () => void
	}

	let { open, onClose }: Props = $props()

	let query = $state('')
	let searchResults = $state<UserSearchResult[]>([])
	let searching = $state(false)
	let creating = $state(false)
	// a plain Map is not reactive under $state - picks must land in a SvelteMap
	const selected = new SvelteMap<string, Candidate>()
	let debounce: ReturnType<typeof setTimeout> | null = null

	const inputClass =
		'border-foreground/12 bg-foreground/4 text-foreground/90 placeholder:text-foreground/35 min-h-10 w-full min-w-0 rounded-xl border px-3 py-2 outline-none transition-colors duration-150 focus:border-[color-mix(in_oklch,var(--accent-primary)_48%,transparent)] focus:bg-foreground/6'

	const friendCandidates = $derived(
		friends.list.map(
			(f): Candidate => ({
				id: f.id,
				display_name: f.display_name,
				username: f.username,
				avatar_url: f.avatar_url,
			})
		)
	)

	const candidates = $derived.by((): Candidate[] => {
		const trimmed = query.trim().toLowerCase()
		const base = trimmed
			? searchResults.map(
					(u): Candidate => ({
						id: u.id,
						display_name: u.display_name,
						username: u.username,
						avatar_url: u.avatar_url,
					})
				)
			: friendCandidates
		return base.filter((c) => c.id !== session.currentUserId)
	})

	const selectedList = $derived([...selected.values()])

	function label(c: Candidate): string {
		return userDisplayName(c) ?? c.id
	}

	function toggle(c: Candidate): void {
		if (selected.has(c.id)) selected.delete(c.id)
		else selected.set(c.id, c)
	}

	function handleInput(event: Event): void {
		const target = event.currentTarget
		if (!(target instanceof HTMLInputElement)) return
		query = target.value
		if (debounce) clearTimeout(debounce)
		const value = query.trim()
		if (!value) {
			searchResults = []
			return
		}
		searching = true
		debounce = setTimeout(async () => {
			try {
				searchResults = await friends.searchUsers(value, 12)
			} finally {
				searching = false
			}
		}, 250)
	}

	async function start(): Promise<void> {
		if (creating || selected.size === 0) return
		creating = true
		try {
			const ids = [...selected.keys()]
			const thread = await messages.createThread({ member_user_ids: ids })
			if (!thread) {
				showError('could not start conversation')
				return
			}
			onClose()
			await goto(resolve(`/c/${thread.id}`))
		} catch {
			showError('could not start conversation')
		} finally {
			creating = false
		}
	}

	$effect(() => {
		if (open) void friends.load()
	})

	$effect(() => {
		if (!open) {
			query = ''
			searchResults = []
			selected.clear()
			creating = false
			searching = false
			if (debounce) clearTimeout(debounce)
			debounce = null
		}
	})
</script>

<BaseModal
	{open}
	title="new conversation"
	onClose={() => !creating && onClose()}
	widthClassName="max-w-md"
>
	<div class="grid gap-3">
		<div class="relative">
			<Search
				class="text-foreground/40 pointer-events-none absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2"
			/>
			<input
				type="text"
				value={query}
				class="{inputClass} pl-9"
				placeholder="search people, or pick friends"
				oninput={handleInput}
				disabled={creating}
			/>
		</div>

		{#if selectedList.length > 0}
			<div class="flex flex-wrap gap-1.5">
				{#each selectedList as c (c.id)}
					<button
						type="button"
						class="rounded-pill bg-(--accent-primary)/14 text-foreground/85 hover:bg-(--accent-primary)/22 flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium transition-colors"
						onclick={() => toggle(c)}
					>
						{label(c)}
						<span class="text-foreground/50">×</span>
					</button>
				{/each}
			</div>
		{/if}

		<div class="max-h-72 overflow-y-auto pr-1">
			{#if searching}
				<p class="text-foreground/45 px-1 py-3 text-sm">
					<ShimmerText className="inline-block">searching</ShimmerText>
				</p>
			{:else if candidates.length === 0}
				<p class="text-foreground/45 px-1 py-3 text-sm">no people found</p>
			{:else}
				<div class="grid gap-0.5">
					{#each candidates as c (c.id)}
						{@const isSelected = selected.has(c.id)}
						<button
							type="button"
							class="rounded-pill flex w-full cursor-pointer items-center gap-3 px-3 py-2 text-left transition-colors {isSelected
								? 'bg-(--accent-primary)/16'
								: 'hover:bg-foreground/8 bg-transparent'}"
							onclick={() => toggle(c)}
						>
							{#if c.avatar_url}
								<img
									src={c.avatar_url}
									alt={label(c)}
									class="h-9 w-9 shrink-0 rounded-full object-cover"
								/>
							{:else}
								<div
									class="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-(--accent-primary)/15 text-xs font-semibold text-(--accent-primary)"
								>
									{#if label(c)}{getUserInitials(label(c))}{:else}<User
											class="h-4 w-4"
										/>{/if}
								</div>
							{/if}
							<div class="flex min-w-0 flex-1 flex-col">
								<span class="text-foreground truncate text-sm font-medium"
									>{label(c)}</span
								>
								{#if c.username}
									<span class="text-foreground/50 truncate text-xs"
										>@{c.username}</span
									>
								{/if}
							</div>
							{#if isSelected}<Check
									class="h-4 w-4 shrink-0 text-(--accent-primary)"
								/>{/if}
						</button>
					{/each}
				</div>
			{/if}
		</div>

		<ModalActions class="pt-1">
			<button
				type="button"
				class="rounded-pill bg-(--accent-primary) inline-flex min-h-9 cursor-pointer items-center justify-center px-4 text-sm font-semibold text-white transition-all duration-150 hover:brightness-[1.06] active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-55"
				disabled={selected.size === 0 || creating}
				onclick={start}
			>
				{#if creating}
					<ShimmerText className="inline-block">starting</ShimmerText>
				{:else}
					{selected.size > 1 ? 'start group' : 'message'}
				{/if}
			</button>
		</ModalActions>
	</div>
</BaseModal>
