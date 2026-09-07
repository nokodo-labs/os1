<script module lang="ts">
	export type ParticipantPickerKind = 'members' | 'agents'
</script>

<script lang="ts">
	/**
	 * the one picker behind both "add members" and "add agents" on a chat: same
	 * search field, same rows, same chips, same confirm - only the candidates and
	 * the write differ. keeping them one component is what keeps them identical.
	 */
	import { addThreadAgents, addThreadMembers } from '$lib/chat/threadProperties'
	import AgentAvatar from '$lib/components/chat/AgentAvatar.svelte'
	import ShimmerText from '$lib/components/effects/ShimmerText.svelte'
	import EmptyState from '$lib/components/EmptyState.svelte'
	import Brain from '$lib/components/icons/Brain.svelte'
	import Check from '$lib/components/icons/Check.svelte'
	import Plus from '$lib/components/icons/Plus.svelte'
	import Search from '$lib/components/icons/Search.svelte'
	import User from '$lib/components/icons/User.svelte'
	import BaseModal from '$lib/components/modals/BaseModal.svelte'
	import ModalActions, {
		modalPrimaryButtonClass,
	} from '$lib/components/modals/ModalActions.svelte'
	import { agents } from '$lib/stores/agents.svelte'
	import type { Thread } from '$lib/stores/chat.svelte'
	import { friends, type UserSearchResult } from '$lib/stores/friends.svelte'
	import { showError } from '$lib/stores/notifications.svelte'
	import { session } from '$lib/stores/session.svelte'
	import { getUserInitials } from '$lib/utils'
	import { userDisplayName } from '$lib/utils/resourceAuthors'
	import { SvelteMap } from 'svelte/reactivity'

	interface Candidate {
		id: string
		label: string
		meta: string | null
		avatarUrl: string | null
	}

	interface Props {
		open: boolean
		thread: Thread | null
		kind: ParticipantPickerKind
		/** ids already on the roster: they never show up as candidates. */
		excludeIds?: readonly string[]
		onClose: () => void
	}

	let { open, thread, kind, excludeIds = [], onClose }: Props = $props()

	let query = $state('')
	let searchResults = $state<UserSearchResult[]>([])
	let searching = $state(false)
	let adding = $state(false)
	// a plain Map is not reactive under $state - picks must land in a SvelteMap
	const selected = new SvelteMap<string, Candidate>()
	let debounce: ReturnType<typeof setTimeout> | null = null

	const isAgents = $derived(kind === 'agents')
	const inputClass =
		'border-foreground/12 bg-foreground/4 text-foreground/90 placeholder:text-foreground/35 min-h-10 w-full min-w-0 rounded-xl border px-3 py-2 outline-none transition-colors duration-150 focus:border-[color-mix(in_oklch,var(--accent-primary)_48%,transparent)] focus:bg-foreground/6 disabled:cursor-not-allowed disabled:opacity-55'

	const title = $derived(isAgents ? 'add agents' : 'add members')
	const placeholder = $derived(isAgents ? 'search agents' : 'search people, or pick friends')
	const emptyLabel = $derived(isAgents ? 'no agents found' : 'no people found')

	const excluded = $derived(new Set(excludeIds))

	function toCandidate(user: UserSearchResult): Candidate {
		return {
			id: user.id,
			label: userDisplayName(user) ?? user.id,
			meta: user.username ? `@${user.username}` : null,
			avatarUrl: user.avatar_url ?? null,
		}
	}

	const memberCandidates = $derived.by((): Candidate[] => {
		const source = query.trim() ? searchResults : friends.list
		return source
			.filter((user) => user.id !== session.currentUserId && !excluded.has(user.id))
			.map(toCandidate)
	})

	const agentCandidates = $derived.by((): Candidate[] => {
		const needle = query.trim().toLowerCase()
		return agents.list
			.filter((agent) => !excluded.has(agent.id))
			.filter(
				(agent) =>
					!needle ||
					agent.name.toLowerCase().includes(needle) ||
					(agent.description ?? '').toLowerCase().includes(needle)
			)
			.map(
				(agent): Candidate => ({
					id: agent.id,
					label: agent.name,
					meta: agent.description ?? null,
					avatarUrl: agent.profile_image_url ?? null,
				})
			)
	})

	const candidates = $derived(isAgents ? agentCandidates : memberCandidates)
	const selectedList = $derived([...selected.values()])

	function toggle(candidate: Candidate): void {
		if (selected.has(candidate.id)) selected.delete(candidate.id)
		else selected.set(candidate.id, candidate)
	}

	function handleInput(event: Event): void {
		const target = event.currentTarget
		if (!(target instanceof HTMLInputElement)) return
		query = target.value
		if (isAgents) return
		if (debounce) clearTimeout(debounce)
		const value = query.trim()
		if (!value) {
			searchResults = []
			searching = false
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

	async function confirm(): Promise<void> {
		const target = thread
		if (!target || adding || selected.size === 0) return
		adding = true
		try {
			const ids = [...selected.keys()]
			const added = isAgents
				? await addThreadAgents(target, ids)
				: await addThreadMembers(target, ids)
			if (!added) {
				showError(isAgents ? 'could not add agents' : 'could not add members')
				return
			}
			onClose()
		} finally {
			adding = false
		}
	}

	$effect(() => {
		if (!open) return
		if (isAgents) void agents.load()
		else void friends.load()
	})

	// the picker is scratch state: it never survives a close.
	$effect(() => {
		if (open) return
		query = ''
		searchResults = []
		selected.clear()
		adding = false
		searching = false
		if (debounce) clearTimeout(debounce)
		debounce = null
	})
</script>

<BaseModal {open} {title} onClose={() => !adding && onClose()} widthClassName="max-w-md">
	<div class="grid gap-3">
		<div class="relative">
			<Search
				class="text-foreground/40 pointer-events-none absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2"
			/>
			<input
				type="text"
				value={query}
				class="{inputClass} pl-9"
				{placeholder}
				aria-label={placeholder}
				oninput={handleInput}
				disabled={adding}
			/>
		</div>

		{#if selectedList.length > 0}
			<div class="flex flex-wrap gap-1.5">
				{#each selectedList as candidate (candidate.id)}
					<button
						type="button"
						class="rounded-pill bg-(--accent-primary)/14 text-foreground/85 hover:bg-(--accent-primary)/22 flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium transition-colors"
						onclick={() => toggle(candidate)}
					>
						{candidate.label}
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
				<EmptyState label={emptyLabel} compact>
					{#snippet icon()}
						{#if isAgents}<Brain class="size-5" />{:else}<User class="size-5" />{/if}
					{/snippet}
				</EmptyState>
			{:else}
				<div class="grid gap-0.5">
					{#each candidates as candidate (candidate.id)}
						{@const isSelected = selected.has(candidate.id)}
						<button
							type="button"
							class="rounded-pill flex w-full cursor-pointer items-center gap-3 px-3 py-2 text-left transition-colors {isSelected
								? 'bg-(--accent-primary)/16'
								: 'hover:bg-foreground/8 bg-transparent'}"
							disabled={adding}
							onclick={() => toggle(candidate)}
						>
							{#if isAgents}
								<AgentAvatar
									name={candidate.label}
									avatarUrl={candidate.avatarUrl}
									class="h-9 w-9"
									textClass="text-xs"
								/>
							{:else if candidate.avatarUrl}
								<img
									src={candidate.avatarUrl}
									alt={candidate.label}
									class="h-9 w-9 shrink-0 rounded-full object-cover"
								/>
							{:else}
								<div
									class="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-(--accent-primary)/15 text-xs font-semibold text-(--accent-primary)"
								>
									{#if candidate.label}{getUserInitials(
											candidate.label
										)}{:else}<User class="h-4 w-4" />{/if}
								</div>
							{/if}
							<div class="flex min-w-0 flex-1 flex-col">
								<span class="text-foreground truncate text-sm font-medium">
									{candidate.label}
								</span>
								{#if candidate.meta}
									<span class="text-foreground/50 truncate text-xs">
										{candidate.meta}
									</span>
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
				class={modalPrimaryButtonClass}
				disabled={selected.size === 0 || adding}
				onclick={confirm}
			>
				<Plus class="h-4 w-4" />
				{#if adding}<ShimmerText className="inline-block">adding</ShimmerText>{:else}<span
						>add</span
					>{/if}
			</button>
		</ModalActions>
	</div>
</BaseModal>
