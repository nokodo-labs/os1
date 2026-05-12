<script lang="ts">
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import LiquidGlass from '$lib/components/effects/LiquidGlass.svelte'
	import EmptyState from '$lib/components/EmptyState.svelte'
	import EllipsisHorizontal from '$lib/components/icons/EllipsisHorizontal.svelte'
	import Pencil from '$lib/components/icons/Pencil.svelte'
	import Plus from '$lib/components/icons/Plus.svelte'
	import Share from '$lib/components/icons/Share.svelte'
	import UserGroup from '$lib/components/icons/UserGroup.svelte'
	import GroupPropertiesModal from '$lib/components/modals/GroupPropertiesModal.svelte'
	import PageTitle from '$lib/components/PageTitle.svelte'
	import { MenuItem, PopupMenu } from '$lib/components/primitives'
	import Timestamp from '$lib/components/Timestamp.svelte'
	import { groups, type Group } from '$lib/stores/groups.svelte'
	import { modals } from '$lib/stores/modals.svelte'
	import { session } from '$lib/stores/session.svelte'

	let isLoading = $state(true)
	let menuGroupId = $state<string | null>(null)
	let menuButtonEl: HTMLButtonElement | null = $state(null)
	let editingGroup = $state<Group | null>(null)
	let isPropertiesOpen = $state(false)
	const currentUserId = $derived(session.currentUserId)

	$effect(() => {
		void groups.load().finally(() => {
			isLoading = false
		})
	})

	function navigateToGroup(group: Group) {
		void goto(resolve(`/social/groups/${group.id}`))
	}

	function canManageGroup(group: Group): boolean {
		const membership = group.memberships.find((member) => member.user_id === currentUserId)
		return Boolean(
			currentUserId &&
			(group.owner_id === currentUserId ||
				membership?.role === 'owner' ||
				membership?.role === 'admin')
		)
	}

	function toggleGroupMenu(event: MouseEvent, groupId: string) {
		event.preventDefault()
		event.stopPropagation()
		menuButtonEl = event.currentTarget as HTMLButtonElement
		menuGroupId = menuGroupId === groupId ? null : groupId
	}

	function shareGroup(group: Group) {
		menuGroupId = null
		modals.open('resource-access', {
			resourceType: 'group',
			resourceId: group.id,
			title: group.name,
		})
	}

	function openProperties(group: Group) {
		menuGroupId = null
		editingGroup = group
		isPropertiesOpen = true
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
		<div class="flex flex-1 flex-col items-center justify-center">
			<EmptyState
				label="no groups yet"
				description="create your first group to start collaborating. share notes, reminders, and threads with your team"
			>
				{#snippet icon()}<UserGroup class="h-10 w-10" />{/snippet}
			</EmptyState>
		</div>
	{:else}
		<div class="flex flex-col gap-2">
			{#each groups.list as group (group.id)}
				<div
					class="bg-foreground/5 hover:bg-foreground/8 flex w-full items-center gap-2 rounded-2xl p-2 text-left transition-all"
				>
					<button
						type="button"
						class="flex min-w-0 flex-1 items-center gap-4 rounded-xl border-none bg-transparent p-2 text-left active:scale-[0.98]"
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
					<button
						type="button"
						class="rounded-pill hover:bg-foreground/8 text-foreground/45 flex size-9 cursor-pointer items-center justify-center border-none bg-transparent transition-colors"
						onclick={(event) => toggleGroupMenu(event, group.id)}
						aria-label="group options"
					>
						<EllipsisHorizontal class="size-4" />
					</button>
					<PopupMenu
						open={menuGroupId === group.id}
						anchorEl={menuButtonEl}
						onClose={() => (menuGroupId = null)}
					>
						<MenuItem onclick={() => shareGroup(group)}>
							{#snippet icon()}<Share class="h-4 w-4" />{/snippet}
							share
						</MenuItem>
						{#if canManageGroup(group)}
							<MenuItem onclick={() => openProperties(group)}>
								{#snippet icon()}<Pencil class="h-4 w-4" />{/snippet}
								properties
							</MenuItem>
						{/if}
					</PopupMenu>
				</div>
			{/each}
		</div>
	{/if}
</div>

{#if editingGroup}
	<GroupPropertiesModal
		open={isPropertiesOpen}
		group={editingGroup}
		canManage={canManageGroup(editingGroup)}
		onClose={() => {
			isPropertiesOpen = false
			editingGroup = null
		}}
		onSaved={async () => {
			await groups.load({ force: true })
		}}
	/>
{/if}
