<script lang="ts">
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import PageTitle from '$lib/components/common/PageTitle.svelte'
	import LiquidGlass from '$lib/components/effects/LiquidGlass.svelte'
	import Plus from '$lib/components/icons/Plus.svelte'
	import UserGroup from '$lib/components/icons/UserGroup.svelte'
	import Timestamp from '$lib/components/Timestamp.svelte'
	import { groups, type Group } from '$lib/stores/groups.svelte'
	import { modals } from '$lib/stores/modals.svelte'

	let isLoading = $state(true)

	$effect(() => {
		void groups.load().finally(() => {
			isLoading = false
		})
	})

	function navigateToGroup(group: Group) {
		void goto(resolve(`/social/groups/${group.id}`))
	}
</script>

<div class="flex flex-1 flex-col gap-6 py-4">
	<div
		class="flex items-center justify-between"
		style="view-transition-name: social-page-header;"
	>
		<PageTitle icon={UserGroup} label="groups" />
		<LiquidGlass class="rounded-full" style="view-transition-name: social-action-btn;">
			<button
				class="interactive flex items-center gap-1.5 rounded-full border-none bg-transparent px-4 py-2 text-sm font-medium text-white/80 hover:text-white"
				onclick={() => modals.open('create-group')}
			>
				<Plus class="h-4 w-4" />
				<span>new group</span>
			</button>
		</LiquidGlass>
	</div>

	{#if isLoading}
		<div class="flex flex-col gap-3">
			{#each { length: 3 } as _item, i (i)}
				<div class="h-20 animate-pulse rounded-2xl bg-white/5"></div>
			{/each}
		</div>
	{:else if groups.list.length === 0}
		<!-- empty state - centered -->
		<div class="flex flex-1 flex-col items-center justify-center gap-5">
			<div
				class="flex h-20 w-20 items-center justify-center rounded-full bg-(--accent-primary)/10"
			>
				<UserGroup class="h-10 w-10 text-(--accent-primary)" />
			</div>
			<div class="flex flex-col items-center gap-2 text-center">
				<p class="text-base font-medium text-white/80">no groups yet</p>
				<p class="max-w-xs text-sm text-white/50">
					create your first group to start collaborating. share notes, reminders, and
					threads with your team.
				</p>
			</div>
		</div>
	{:else}
		<div class="flex flex-col gap-2">
			{#each groups.list as group (group.id)}
				<button
					class="flex w-full items-center gap-4 rounded-2xl bg-white/5 p-4 text-left transition-all hover:bg-white/8 active:scale-[0.98]"
					onclick={() => navigateToGroup(group)}
				>
					<div
						class="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-(--accent-primary)/15"
					>
						<UserGroup class="h-5 w-5 text-(--accent-primary)" />
					</div>
					<div class="flex min-w-0 flex-1 flex-col gap-0.5">
						<span class="truncate text-sm font-medium text-white">
							{group.name}
						</span>
						<div class="flex items-center gap-2 text-xs text-white/50">
							<span>{group.memberships?.length ?? 0} members</span>
							<span class="text-white/25">-</span>
							<Timestamp timestamp={new Date(group.updated_at)} mode="relative" />
						</div>
					</div>
				</button>
			{/each}
		</div>
	{/if}
</div>
