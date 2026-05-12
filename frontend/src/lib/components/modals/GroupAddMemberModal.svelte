<script lang="ts">
	import { api } from '$lib/api/client'
	import type { components } from '$lib/api/types'
	import ShimmerText from '$lib/components/effects/ShimmerText.svelte'
	import Check from '$lib/components/icons/Check.svelte'
	import Plus from '$lib/components/icons/Plus.svelte'
	import Search from '$lib/components/icons/Search.svelte'
	import User from '$lib/components/icons/User.svelte'
	import BaseModal from '$lib/components/modals/BaseModal.svelte'
	import { resourceAccentStyle, resourceVisual } from '$lib/resources/resourceVisuals'
	import { groups, type Group, type GroupMemberRole } from '$lib/stores/groups.svelte'
	import { showError } from '$lib/stores/notifications.svelte'
	import { userDisplayName } from '$lib/utils/resourceAuthors'

	type UserResult = components['schemas']['UserSearchResult']

	interface Props {
		open: boolean
		group: Group
		onClose: () => void
		onAdded?: () => void | Promise<void>
	}

	let { open, group, onClose, onAdded }: Props = $props()

	let query = $state('')
	let results = $state<UserResult[]>([])
	let selected = $state<UserResult | null>(null)
	let role = $state<GroupMemberRole>('member')
	let searching = $state(false)
	let adding = $state(false)
	let debounce: ReturnType<typeof setTimeout> | null = null

	const panelClass =
		'border-foreground/13 bg-background/70 shadow-[inset_0_1px_0_rgb(255_255_255/0.08)] backdrop-blur-[16px] backdrop-saturate-[1.08]'
	const inputClass =
		'border-foreground/12 bg-foreground/4 text-foreground/90 placeholder:text-foreground/35 min-h-10 w-full min-w-0 rounded-xl border px-3 py-2 outline-none transition-colors duration-150 focus:border-[color-mix(in_oklch,var(--accent-primary)_48%,transparent)] focus:bg-foreground/6 disabled:cursor-not-allowed disabled:opacity-55'
	const actionButtonClass =
		'rounded-pill inline-flex min-h-9 cursor-pointer items-center justify-center gap-1.5 px-4 text-sm font-semibold transition-all duration-150 active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-55'
	const groupVisual = resourceVisual('group')
	const GroupIcon = groupVisual.icon
	const groupAccentStyle = resourceAccentStyle('group')
	const existingUserIds = $derived(new Set(group.memberships.map((member) => member.user_id)))
	const filteredResults = $derived(results.filter((user) => !existingUserIds.has(user.id)))

	function userLabel(user: UserResult): string {
		return userDisplayName(user) ?? user.id
	}

	async function searchUsers(value: string): Promise<void> {
		const trimmed = value.trim()
		if (!trimmed) {
			results = []
			return
		}
		searching = true
		try {
			const { data } = await api.GET('/v1/users/search', {
				params: { query: { q: trimmed, limit: 10 } },
			})
			results = data ?? []
		} finally {
			searching = false
		}
	}

	function handleInput(event: Event): void {
		const target = event.currentTarget
		if (!(target instanceof HTMLInputElement)) return
		query = target.value
		selected = null
		if (debounce) clearTimeout(debounce)
		debounce = setTimeout(() => void searchUsers(query), 250)
	}

	async function addMember(): Promise<void> {
		if (!selected || adding) return
		adding = true
		try {
			const created = await groups.addMember(group.id, { user_id: selected.id, role })
			if (!created) {
				showError('could not add member')
				return
			}
			await onAdded?.()
			onClose()
		} finally {
			adding = false
		}
	}

	$effect(() => {
		if (!open) {
			query = ''
			results = []
			selected = null
			role = 'member'
			adding = false
			searching = false
			if (debounce) clearTimeout(debounce)
			debounce = null
		}
	})
</script>

<BaseModal {open} title="add member" onClose={() => !adding && onClose()} widthClassName="max-w-md">
	<div class="grid gap-3" style={groupAccentStyle}>
		<section class="{panelClass} flex min-w-0 items-center gap-4 rounded-[18px] border p-4">
			<div
				class="flex h-11 w-11 shrink-0 items-center justify-center rounded-[15px] border border-[color-mix(in_oklch,var(--accent-primary)_22%,transparent)] bg-[color-mix(in_oklch,var(--accent-primary)_12%,transparent)] text-(--accent-primary)"
			>
				<GroupIcon variant="solid" class="h-5 w-5" />
			</div>
			<div class="min-w-0 flex-1">
				<p class="text-foreground/50 text-xs font-medium tracking-[0.12em] uppercase">
					group
				</p>
				<h3 class="text-foreground min-w-0 truncate text-lg font-semibold">{group.name}</h3>
				<p class="text-foreground/55 mt-0.5 min-w-0 truncate text-xs">
					{group.memberships.length} members
				</p>
			</div>
		</section>

		<div class="{panelClass} rounded-[18px] border p-3">
			<label
				class="text-foreground/60 mb-2 flex items-center gap-2 text-[0.78rem] font-semibold"
				for="member-search"
			>
				<Search class="h-4 w-4 text-(--accent-primary)" />
				search users
			</label>
			<input
				id="member-search"
				type="text"
				value={query}
				class={inputClass}
				placeholder="name, username, or email"
				oninput={handleInput}
				disabled={adding}
			/>

			{#if searching}
				<p class="text-foreground/45 px-1 pt-3 text-sm">searching</p>
			{:else if filteredResults.length > 0}
				<div class="mt-3 grid gap-1">
					{#each filteredResults as user (user.id)}
						<button
							type="button"
							class="rounded-pill flex w-full cursor-pointer items-center gap-3 border-none px-3 py-2 text-left transition-colors {selected?.id ===
							user.id
								? 'text-foreground bg-(--accent-primary)/16'
								: 'text-foreground/75 hover:bg-foreground/8 bg-transparent'}"
							onclick={() => (selected = user)}
						>
							<div
								class="bg-foreground/10 flex h-8 w-8 shrink-0 items-center justify-center rounded-full"
							>
								<User class="h-4 w-4" />
							</div>
							<span class="min-w-0 flex-1 truncate text-sm">{userLabel(user)}</span>
							{#if selected?.id === user.id}<Check
									class="h-4 w-4 text-(--accent-primary)"
								/>{/if}
						</button>
					{/each}
				</div>
			{/if}
		</div>

		<div class="{panelClass} rounded-[18px] border p-3">
			<label
				class="text-foreground/60 mb-2 block text-[0.78rem] font-semibold"
				for="member-role">role</label
			>
			<select
				id="member-role"
				bind:value={role}
				class="{inputClass} appearance-none"
				disabled={adding}
			>
				<option value="member">member</option>
				<option value="admin">admin</option>
			</select>
		</div>

		<div class="flex justify-end gap-2 pt-1">
			<button
				type="button"
				class="{actionButtonClass} bg-(--accent-primary) text-white hover:brightness-[1.06]"
				disabled={!selected || adding}
				onclick={addMember}
			>
				<Plus class="h-4 w-4" />
				{#if adding}<ShimmerText className="inline-block">adding</ShimmerText>{:else}<span
						>add</span
					>{/if}
			</button>
		</div>
	</div>
</BaseModal>
