<script lang="ts">
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import { page } from '$app/state'
	import ShimmerText from '$lib/components/effects/ShimmerText.svelte'
	import EmptyState from '$lib/components/EmptyState.svelte'
	import ChevronLeft from '$lib/components/icons/ChevronLeft.svelte'
	import EllipsisHorizontal from '$lib/components/icons/EllipsisHorizontal.svelte'
	import Pencil from '$lib/components/icons/Pencil.svelte'
	import Plus from '$lib/components/icons/Plus.svelte'
	import Share from '$lib/components/icons/Share.svelte'
	import UserGroup from '$lib/components/icons/UserGroup.svelte'
	import GroupAddMemberModal from '$lib/components/modals/GroupAddMemberModal.svelte'
	import GroupPropertiesModal from '$lib/components/modals/GroupPropertiesModal.svelte'
	import { MenuItem, PopupMenu } from '$lib/components/primitives'
	import Timestamp from '$lib/components/Timestamp.svelte'
	import { useSystemChrome } from '$lib/contexts/systemChromeContext.svelte'
	import { groups, type Group } from '$lib/stores/groups.svelte'
	import { modals } from '$lib/stores/modals.svelte'
	import { session } from '$lib/stores/session.svelte'

	const chrome = useSystemChrome()

	const groupId = $derived(page.params.id ?? '')
	let group = $state<Group | null>(null)
	let isLoading = $state(true)
	let removingUserId = $state<string | null>(null)
	let isPropertiesOpen = $state(false)
	let isAddMemberOpen = $state(false)
	let memberMenuUserId = $state<string | null>(null)
	let memberMenuButtonEl: HTMLButtonElement | null = $state(null)
	const currentUserId = $derived(session.currentUserId)
	const currentMembership = $derived(
		group?.memberships.find((member) => member.user_id === currentUserId) ?? null
	)
	const canManageGroup = $derived(
		Boolean(
			group &&
			currentUserId &&
			(group.owner_id === currentUserId ||
				currentMembership?.role === 'owner' ||
				currentMembership?.role === 'admin')
		)
	)

	$effect(() => {
		if (!groupId) return
		void groups.load().then(() => {
			group = groups.getById(groupId) ?? null
			isLoading = false
		})
	})

	$effect(() => {
		const memberships = group?.memberships ?? []
		if (memberships.length > 0) {
			void session.ensureUsers(memberships.map((member) => member.user_id))
		}
	})

	const handleBack = async () => {
		await goto(resolve('/social/groups'), { keepFocus: true, noScroll: true })
	}

	function memberLabel(userId: string): string {
		return session.authorLabel(userId) ?? userId
	}

	async function refreshGroup() {
		await groups.load({ force: true })
		group = groups.getById(groupId) ?? null
	}

	function shareGroup() {
		if (!group) return
		modals.open('resource-access', {
			resourceType: 'group',
			resourceId: group.id,
			title: group.name,
		})
	}

	async function removeMember(userId: string) {
		if (!group || removingUserId) return
		memberMenuUserId = null
		removingUserId = userId
		try {
			if (await groups.removeMember(group.id, userId)) await refreshGroup()
		} finally {
			removingUserId = null
		}
	}

	function toggleMemberMenu(event: MouseEvent, userId: string) {
		event.preventDefault()
		event.stopPropagation()
		memberMenuButtonEl = event.currentTarget as HTMLButtonElement
		memberMenuUserId = memberMenuUserId === userId ? null : userId
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
		aria-label="back to groups"
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
			<div class="flex flex-col gap-4 py-6">
				<div class="bg-foreground/5 h-8 w-48 animate-pulse rounded-full"></div>
				<div class="bg-foreground/5 h-4 w-72 animate-pulse rounded-full"></div>
			</div>
		{:else if !group}
			<div class="bg-foreground/5 rounded-2xl p-6 text-center">
				<p class="text-foreground/50 text-sm">group not found</p>
			</div>
		{:else}
			<div class="mb-8 flex flex-col gap-5 py-2">
				<div
					class="liquid-glass liquid-glass--frosted flex items-start gap-4 rounded-[22px] p-4"
				>
					<div
						class="flex h-14 w-14 shrink-0 items-center justify-center rounded-full bg-(--accent-primary)/15"
					>
						<UserGroup class="h-7 w-7 text-(--accent-primary)" variant="solid" />
					</div>
					<div class="flex min-w-0 flex-1 flex-col gap-1">
						<h1 class="text-foreground truncate text-xl font-bold">{group.name}</h1>
						{#if group.description}
							<p class="text-foreground/60 text-sm">{group.description}</p>
						{/if}
						<div class="text-foreground/45 mt-1 flex items-center gap-2 text-xs">
							<span>{group.memberships?.length ?? 0} members</span>
							<span class="text-foreground/20">-</span>
							<span>
								created <Timestamp
									timestamp={new Date(group.created_at)}
									mode="relative"
								/>
							</span>
						</div>
					</div>
					<div class="flex shrink-0 items-center gap-1">
						<button
							type="button"
							class="rounded-pill hover:bg-foreground/8 text-foreground/60 flex size-10 cursor-pointer items-center justify-center border-none bg-transparent transition-colors"
							onclick={shareGroup}
							aria-label="share group"
						>
							<Share class="size-4" />
						</button>
						{#if canManageGroup}
							<button
								type="button"
								class="rounded-pill hover:bg-foreground/8 text-foreground/60 flex size-10 cursor-pointer items-center justify-center border-none bg-transparent transition-colors"
								onclick={() => (isAddMemberOpen = true)}
								aria-label="add member"
							>
								<Plus class="size-4" />
							</button>
							<button
								type="button"
								class="rounded-pill hover:bg-foreground/8 text-foreground/60 flex size-10 cursor-pointer items-center justify-center border-none bg-transparent transition-colors"
								onclick={() => (isPropertiesOpen = true)}
								aria-label="group properties"
							>
								<Pencil class="size-4" />
							</button>
						{/if}
					</div>
				</div>
			</div>

			<section class="flex flex-col gap-3">
				<h2 class="text-foreground/60 text-sm font-semibold">members</h2>

				{#if group.memberships && group.memberships.length > 0}
					<div class="flex flex-col gap-2">
						{#each group.memberships as member (member.id)}
							<div
								class="border-foreground/10 bg-foreground/4 hover:bg-foreground/7 flex w-full items-center gap-3 rounded-[18px] border p-3 text-left transition-colors"
							>
								<button
									type="button"
									class="flex min-w-0 flex-1 items-center gap-3 border-none bg-transparent p-0 text-left"
									onclick={() => goto(resolve(`/social/users/${member.user_id}`))}
								>
									<div
										class="bg-foreground/10 text-foreground/80 flex h-9 w-9 items-center justify-center rounded-full text-xs font-semibold"
									>
										{memberLabel(member.user_id).slice(0, 2).toUpperCase()}
									</div>
									<div class="flex min-w-0 flex-col">
										<span class="text-foreground truncate text-sm">
											{memberLabel(member.user_id)}
										</span>
										<span class="text-foreground/45 truncate text-xs">
											{member.role} · {member.user_id}
										</span>
									</div>
								</button>
								{#if canManageGroup}
									<button
										type="button"
										class="rounded-pill hover:bg-foreground/8 text-foreground/45 flex size-9 cursor-pointer items-center justify-center border-none bg-transparent transition-colors"
										onclick={(event) => toggleMemberMenu(event, member.user_id)}
										aria-label="member options"
									>
										<EllipsisHorizontal class="size-4" />
									</button>
									<PopupMenu
										open={memberMenuUserId === member.user_id}
										anchorEl={memberMenuButtonEl}
										onClose={() => (memberMenuUserId = null)}
									>
										<MenuItem
											onclick={() => {
												memberMenuUserId = null
												void goto(
													resolve(`/social/users/${member.user_id}`)
												)
											}}
										>
											view profile
										</MenuItem>
										{#if member.role !== 'owner'}
											<MenuItem
												destructive
												disabled={removingUserId === member.user_id}
												onclick={() => removeMember(member.user_id)}
											>
												{#if removingUserId === member.user_id}
													<ShimmerText className="inline-block"
														>removing</ShimmerText
													>
												{:else}
													remove
												{/if}
											</MenuItem>
										{/if}
									</PopupMenu>
								{/if}
							</div>
						{/each}
					</div>
				{:else}
					<EmptyState label="no members yet" compact />
				{/if}
			</section>
		{/if}
	</div>
</div>

{#if group}
	<GroupPropertiesModal
		open={isPropertiesOpen}
		{group}
		canManage={canManageGroup}
		onClose={() => (isPropertiesOpen = false)}
		onSaved={refreshGroup}
	/>
	<GroupAddMemberModal
		open={isAddMemberOpen}
		{group}
		onClose={() => (isAddMemberOpen = false)}
		onAdded={refreshGroup}
	/>
{/if}
