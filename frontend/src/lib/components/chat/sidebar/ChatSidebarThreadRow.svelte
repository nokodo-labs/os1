<script lang="ts">
	import { api } from '$lib/api/client'
	import SidebarListItem from '$lib/components/SidebarListItem.svelte'
	import Timestamp from '$lib/components/Timestamp.svelte'
	import type { Thread } from '$lib/stores/chat.svelte'

	import DeleteButton from '$lib/components/DeleteButton.svelte'
	import ShimmerText from '$lib/components/effects/ShimmerText.svelte'
	import ArchiveBox from '$lib/components/icons/ArchiveBox.svelte'
	import EllipsisHorizontal from '$lib/components/icons/EllipsisHorizontal.svelte'
	import InfoCircle from '$lib/components/icons/InfoCircle.svelte'
	import Share from '$lib/components/icons/Share.svelte'
	import { MenuItem, PopupMenu } from '$lib/components/primitives'
	import type { ResourceProjectOption } from '$lib/components/widgets/ResourceProjectsMenu.svelte'
	import ResourceProjectsMenu from '$lib/components/widgets/ResourceProjectsMenu.svelte'
	import { activeRunsStore } from '$lib/stores/activeRuns.svelte'
	import { chat } from '$lib/stores/chat.svelte'
	import { device } from '$lib/stores/device.svelte'
	import { modals } from '$lib/stores/modals.svelte'
	import { projects } from '$lib/stores/projects.svelte'
	import {
		canDeleteAccessLevel,
		canEditAccessLevel,
		canShareAccessLevel,
		resourceAccess,
	} from '$lib/stores/resourceAccess.svelte'
	import { session } from '$lib/stores/session.svelte'

	type Props = {
		thread: Thread
		selected: boolean
		onOpenThread: (threadId: string) => void | Promise<void>
		onPrefetch: (threadId: string) => void
		openThreadMenuId: string | null
		onToggleMenu: (threadId: string) => void
		onCloseMenu: () => void
		onRequestEdit: (thread: Thread) => void
		onDeleteThread: (thread: Thread) => void | boolean | Promise<void | boolean>
		projectOptions?: ResourceProjectOption[]
	}

	let {
		thread,
		selected,
		onOpenThread,
		onPrefetch,
		openThreadMenuId,
		onToggleMenu,
		onCloseMenu,
		onRequestEdit,
		onDeleteThread,
		projectOptions = [],
	}: Props = $props()

	const hasRun = $derived(activeRunsStore.hasActiveRuns(thread.id))
	const hasUnread = $derived((chat.unreadCounts.get(thread.id) ?? 0) > 0)
	const metadataGenerating = $derived(chat.metadataGeneratingThreadIds.has(thread.id))
	const isGenerating = $derived(hasRun || metadataGenerating)
	const isMissingTitle = $derived(!thread.title?.trim())
	const hasTags = $derived(thread.tags && thread.tags.length > 0)
	const isGeneratingTitle = $derived(isGenerating && isMissingTitle)
	const isGeneratingTags = $derived(isGenerating && !hasTags)
	const displayTitle = $derived(thread.title || 'new chat')
	const threadAccessLevel = $derived(resourceAccess.level('thread', thread.id, thread.owner_id))
	const canEditThread = $derived(canEditAccessLevel(threadAccessLevel))
	const canShareThread = $derived(canShareAccessLevel(threadAccessLevel))
	const canDeleteThread = $derived(canDeleteAccessLevel(threadAccessLevel))
	const hasThreadActions = $derived(canEditThread || canShareThread || canDeleteThread)
	const threadProjectIds = $derived(thread.project_ids ?? [])
	const canManageProjects = $derived(canEditThread)
	const authorLabel = $derived.by(() => {
		if (thread.owner_id === session.currentUserId) return null
		return session.authorLabel(thread.owner_id)
	})

	const visibilityMode = $derived(
		device.isMobile ? 'always' : isGenerating || hasUnread ? 'overlay-always' : 'hover'
	)

	let menuButtonEl = $state<HTMLElement | null>(null)

	$effect(() => {
		if (thread.owner_id !== session.currentUserId) void session.ensureUsers([thread.owner_id])
		void resourceAccess.ensure('thread', thread.id, thread.owner_id)
	})

	async function handleThreadProjectToggle(projectId: string, selected: boolean): Promise<void> {
		const currentIds = thread.project_ids ?? []
		const nextIds = selected
			? [...new Set([...currentIds, projectId])]
			: currentIds.filter((id) => id !== projectId)
		const { data, error } = await api.PATCH('/v1/threads/{thread_id}', {
			params: { path: { thread_id: thread.id } },
			body: { project_ids: nextIds },
		})
		if (error) return
		const updated = data ?? { ...thread, project_ids: nextIds }
		chat.threadCache.set(updated)
		chat.updateRecentThread(thread.id, () => updated)
		projects.invalidateResourceCounts([...new Set([...currentIds, ...nextIds])])
	}
</script>

<div class="group/chat relative min-w-0" role="listitem">
	<SidebarListItem
		{selected}
		radiusClass="rounded-container"
		paddingClass="px-3 py-2"
		className="gap-2 text-foreground"
		onPrefetch={() => onPrefetch(thread.id)}
		onSelect={async () => {
			await onOpenThread(thread.id)
		}}
		actionsVisibility={visibilityMode}
	>
		<div class="min-w-0 flex-1 overflow-hidden">
			<!-- primary row: title -->
			<div class="flex items-center">
				{#if isGeneratingTitle}
					<ShimmerText
						className="min-w-0 flex-1 overflow-hidden text-sm font-medium leading-normal text-ellipsis whitespace-nowrap"
					>
						generating
					</ShimmerText>
				{:else}
					<span
						class="min-w-0 flex-1 overflow-hidden text-sm leading-normal font-medium text-ellipsis whitespace-nowrap {thread.title
							? 'text-foreground'
							: 'text-foreground/40 italic'}"
					>
						{displayTitle}
					</span>
				{/if}
			</div>

			<!-- second row: timestamp + tags -->
			<div class="mt-0.5 flex items-center gap-1.5 overflow-hidden">
				<Timestamp
					timestamp={new Date(thread.last_activity_at ?? '')}
					mode="relative"
					minUnit="hour"
					className="shrink-0 text-[11px] text-foreground/35"
				/>
				{#if authorLabel}
					<span class="text-foreground/30 shrink-0 text-[10px]">·</span>
					<span class="text-foreground/45 min-w-0 truncate text-[10px]">
						by {authorLabel}
					</span>
				{/if}
				{#if hasTags}
					{#each (thread.tags ?? []).slice(0, 3) as tag (tag)}
						<span
							class="bg-foreground/8 text-foreground/50 inline-flex max-w-20 shrink-0 items-center truncate rounded-full px-1.5 py-px text-[10px] leading-tight"
							title={tag}
						>
							{tag}
						</span>
					{/each}
					{#if (thread.tags ?? []).length > 3}
						<span class="text-foreground/30 shrink-0 text-[10px]">
							+{(thread.tags ?? []).length - 3}
						</span>
					{/if}
				{:else if isGeneratingTags}
					<ShimmerText
						className="text-foreground/45 min-w-0 truncate text-[10px] leading-tight"
					>
						generating
					</ShimmerText>
				{/if}
			</div>
		</div>

		{#snippet actions()}
			{#if hasThreadActions || isGenerating || hasUnread}
				<button
					type="button"
					class="rounded-circle text-foreground/55 hover:bg-foreground/10 hover:text-foreground inline-flex h-8 w-8 cursor-pointer items-center justify-center border border-transparent bg-transparent transition-all duration-200"
					onpointerdown={(e) => e.stopPropagation()}
					onclick={(e) => {
						e.stopPropagation()
						if (!hasThreadActions) return
						if (openThreadMenuId !== thread.id) {
							menuButtonEl = e.currentTarget as HTMLElement
						}
						onToggleMenu(thread.id)
					}}
					aria-label={isGenerating
						? 'generating'
						: hasUnread
							? 'unread messages'
							: 'thread actions'}
					title={isGenerating ? 'generating' : hasUnread ? 'unread messages' : 'Menu'}
				>
					{#if isGenerating}
						<div class="relative flex h-2 w-2 shrink-0 items-center justify-center">
							<span
								class="absolute inline-flex h-full w-full animate-ping rounded-full bg-yellow-400 opacity-75"
							></span>
							<span
								class="relative inline-flex h-1.5 w-1.5 rounded-full bg-yellow-400"
							></span>
						</div>
					{:else if hasUnread}
						<div class="relative flex h-2 w-2 shrink-0 items-center justify-center">
							<span
								class="absolute inline-flex h-full w-full animate-ping rounded-full bg-green-400 opacity-75"
							></span>
							<span class="relative inline-flex h-1.5 w-1.5 rounded-full bg-green-400"
							></span>
						</div>
					{:else}
						<EllipsisHorizontal class="h-4.5 w-4.5" />
					{/if}
				</button>
			{/if}
		{/snippet}
	</SidebarListItem>

	<PopupMenu
		open={hasThreadActions && openThreadMenuId === thread.id}
		anchorEl={menuButtonEl}
		onClose={onCloseMenu}
		data-thread-menu
	>
		{#if canShareThread}
			<MenuItem
				onclick={(e) => {
					e.stopPropagation()
					onCloseMenu()
					modals.open('resource-access', {
						resourceType: 'thread',
						resourceId: thread.id,
						title: thread.title ?? thread.id,
					})
				}}
			>
				{#snippet icon()}<Share class="size-full" strokeWidth="2.1" />{/snippet}
				share
			</MenuItem>
		{/if}
		{#if canEditThread}
			<MenuItem
				onclick={(e) => {
					e.stopPropagation()
					onCloseMenu()
					onRequestEdit(thread)
				}}
			>
				{#snippet icon()}<InfoCircle variant="solid" class="size-full" />{/snippet}
				properties
			</MenuItem>
			<MenuItem
				onclick={(e) => {
					e.stopPropagation()
					onCloseMenu()
					console.log('thread action', 'archive', thread.id)
				}}
			>
				{#snippet icon()}<ArchiveBox variant="solid" class="size-full" />{/snippet}
				archive
			</MenuItem>
			{#if canManageProjects}
				<ResourceProjectsMenu
					{projectOptions}
					selectedProjectIds={threadProjectIds}
					onProjectToggle={handleThreadProjectToggle}
				/>
			{/if}
		{/if}
		{#if canDeleteThread}
			<div class="bg-foreground/15 my-1 h-px w-full"></div>
			<div class="mt-1">
				<DeleteButton
					confirm={true}
					stopPropagation={true}
					onTrigger={onCloseMenu}
					modalText={{ title: 'delete chat?', description: thread.title || 'new chat' }}
					onDelete={() => onDeleteThread(thread)}
				/>
			</div>
		{/if}
	</PopupMenu>
</div>
