<script lang="ts">
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import EmptyState from '$lib/components/EmptyState.svelte'
	import ChevronDown from '$lib/components/icons/ChevronDown.svelte'
	import EllipsisHorizontal from '$lib/components/icons/EllipsisHorizontal.svelte'
	import Pencil from '$lib/components/icons/Pencil.svelte'
	import Plus from '$lib/components/icons/Plus.svelte'
	import Share from '$lib/components/icons/Share.svelte'
	import UserGroup from '$lib/components/icons/UserGroup.svelte'
	import GroupAddMemberModal from '$lib/components/modals/GroupAddMemberModal.svelte'
	import GroupPropertiesModal from '$lib/components/modals/GroupPropertiesModal.svelte'
	import PageTitle from '$lib/components/PageTitle.svelte'
	import { MenuItem, PopupMenu } from '$lib/components/primitives'
	import Timestamp from '$lib/components/Timestamp.svelte'
	import { useSystemChrome } from '$lib/contexts/systemChromeContext.svelte'
	import { groups, type Group } from '$lib/stores/groups.svelte'
	import { modals } from '$lib/stores/modals.svelte'
	import { session } from '$lib/stores/session.svelte'

	let isLoading = $state(true)
	let menuGroupId = $state<string | null>(null)
	let menuButtonEl: HTMLButtonElement | null = $state(null)
	let editingGroup = $state<Group | null>(null)
	let addingGroup = $state<Group | null>(null)
	let isPropertiesOpen = $state(false)
	let isAddMemberOpen = $state(false)
	const chrome = useSystemChrome()
	const currentUserId = $derived(session.currentUserId)
	const createdGroups = $derived(
		currentUserId
			? groups.list.filter((group) => group.owner_id === currentUserId)
			: groups.list
	)
	const joinedGroups = $derived(
		currentUserId ? groups.list.filter((group) => group.owner_id !== currentUserId) : []
	)
	let createdGroupsOpen = $state(true)
	let joinedGroupsOpen = $state(true)

	$effect(() => {
		void groups.load().finally(() => {
			isLoading = false
		})
	})

	$effect(() => {
		chrome.setContextActions(islandContextActions)
		return () => chrome.setContextActions(null)
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

	function openAddMember(group: Group) {
		menuGroupId = null
		addingGroup = group
		isAddMemberOpen = true
	}
</script>

{#snippet islandContextActions()}
	<button
		type="button"
		class="flex cursor-pointer items-center justify-center opacity-80 transition-all duration-150 hover:scale-[1.05] hover:opacity-100 active:scale-[0.97]"
		onclick={() => modals.open('create-group')}
		aria-label="new group"
	>
		<Plus />
	</button>
{/snippet}

{#snippet groupSection(label: string, count: number, open: boolean, onToggle: () => void)}
	<button
		type="button"
		class="text-foreground/70 hover:text-foreground/90 flex w-full cursor-pointer items-center gap-1.5 bg-transparent px-2 py-2 text-xs font-semibold tracking-wide uppercase transition-colors duration-150"
		onclick={onToggle}
		aria-expanded={open}
	>
		<ChevronDown class="h-3 w-3 transition-transform duration-200 {open ? '' : '-rotate-90'}" />
		{label}
		<span class="text-foreground/50 font-normal">({count})</span>
	</button>
{/snippet}

{#snippet groupRow(group: Group)}
	<div
		class="bg-foreground/5 hover:bg-foreground/8 rounded-pill flex w-full items-center gap-2 p-2 text-left transition-all"
	>
		<button
			type="button"
			class="rounded-pill flex min-w-0 flex-1 cursor-pointer items-center gap-4 border-none bg-transparent p-2 text-left active:scale-[0.98]"
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
				<MenuItem onclick={() => openAddMember(group)}>
					{#snippet icon()}<Plus class="h-4 w-4" />{/snippet}
					add people
				</MenuItem>
				<MenuItem onclick={() => openProperties(group)}>
					{#snippet icon()}<Pencil class="h-4 w-4" />{/snippet}
					properties
				</MenuItem>
			{/if}
		</PopupMenu>
	</div>
{/snippet}

<div class="flex flex-1 flex-col gap-6 py-4">
	<div class="flex items-center" style="view-transition-name: social-page-header;">
		<PageTitle icon={UserGroup} label="groups" />
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
			{#if currentUserId}
				{#if createdGroups.length > 0}
					{@render groupSection(
						'groups you created',
						createdGroups.length,
						createdGroupsOpen,
						() => {
							createdGroupsOpen = !createdGroupsOpen
						}
					)}
					{#if createdGroupsOpen}
						{#each createdGroups as group (group.id)}
							{@render groupRow(group)}
						{/each}
					{/if}
				{/if}
				{#if joinedGroups.length > 0}
					{@render groupSection(
						'groups you are in',
						joinedGroups.length,
						joinedGroupsOpen,
						() => {
							joinedGroupsOpen = !joinedGroupsOpen
						}
					)}
					{#if joinedGroupsOpen}
						{#each joinedGroups as group (group.id)}
							{@render groupRow(group)}
						{/each}
					{/if}
				{/if}
			{:else}
				{#each groups.list as group (group.id)}
					{@render groupRow(group)}
				{/each}
			{/if}
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

{#if addingGroup}
	<GroupAddMemberModal
		open={isAddMemberOpen}
		group={addingGroup}
		onClose={() => {
			isAddMemberOpen = false
			addingGroup = null
		}}
		onAdded={async () => {
			await groups.load({ force: true })
		}}
	/>
{/if}
