<script lang="ts">
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import LiquidGlass from '$lib/components/effects/LiquidGlass.svelte'
	import Plus from '$lib/components/icons/Plus.svelte'
	import UserGroup from '$lib/components/icons/UserGroup.svelte'
	import PageTitle from '$lib/components/PageTitle.svelte'
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
				class="interactive text-foreground/80 hover:text-foreground flex items-center gap-1.5 rounded-full border-none bg-transparent px-4 py-2 text-sm font-medium"
				onclick={() => modals.open('create-group')}
			>
				<Plus class="h-4 w-4" />
				<span>new group</span>
			</button>
		</LiquidGlass>
	</div>

	{#if isLoading}
		<div class="flex flex-col gap-3">
			{#each [0, 1, 2] as i (i)}
				<div class="bg-foreground/5 h-20 animate-pulse rounded-2xl"></div>
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
				<p class="text-foreground/80 text-base font-medium">no groups yet</p>
				<p class="text-foreground/50 max-w-xs text-sm">
					create your first group to start collaborating. share notes, reminders, and
					threads with your team.
				</p>
			</div>
		</div>
	{:else}
		<div class="flex flex-col gap-2">
			{#each groups.list as group (group.id)}
				<button
					class="bg-foreground/5 hover:bg-foreground/8 flex w-full items-center gap-4 rounded-2xl p-4 text-left transition-all active:scale-[0.98]"
					onclick={() => navigateToGroup(group)}
				>
					<div
						class="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-(--accent-primary)/15"
					>
						<UserGroup class="h-5 w-5 text-(--accent-primary)" />
					</div>
					<div class="flex min-w-0 flex-1 flex-col gap-0.5">
						<span class="text-foreground truncate text-sm font-medium">
							{group.name}
						</span>
						<div class="text-foreground/50 flex items-center gap-2 text-xs">
							<span>{group.memberships?.length ?? 0} members</span>
							<span class="text-foreground/25">-</span>
							<Timestamp timestamp={new Date(group.updated_at)} mode="relative" />
						</div>
					</div>
				</button>
			{/each}
		</div>
	{/if}
</div>
