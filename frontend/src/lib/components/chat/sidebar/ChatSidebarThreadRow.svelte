<script lang="ts">
	import SidebarListItem from '$lib/components/SidebarListItem.svelte'
	import Timestamp from '$lib/components/Timestamp.svelte'
	import type { Thread } from '$lib/stores/chat.svelte'

	import DeleteButton from '$lib/components/DeleteButton.svelte'
	import ShimmerText from '$lib/components/effects/ShimmerText.svelte'
	import ArchiveBox from '$lib/components/icons/ArchiveBox.svelte'
	import EllipsisHorizontal from '$lib/components/icons/EllipsisHorizontal.svelte'
	import InfoCircle from '$lib/components/icons/InfoCircle.svelte'
	import Share from '$lib/components/icons/Share.svelte'
	import { PopupMenu } from '$lib/components/primitives'
	import { activeRunsStore } from '$lib/stores/activeRuns.svelte'
	import { chat } from '$lib/stores/chat.svelte'
	import { modals } from '$lib/stores/modals.svelte'

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
	}: Props = $props()

	const hasRun = $derived(activeRunsStore.hasActiveRuns(thread.id))
	const hasUnread = $derived((chat.unreadCounts.get(thread.id) ?? 0) > 0)
	const isGeneratingTitle = $derived(hasRun && !thread.title)
	const displayTitle = $derived(thread.title || 'new chat')
	const hasTags = $derived(thread.tags && thread.tags.length > 0)

	let menuButtonEl = $state<HTMLElement | null>(null)
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
		actionsVisibility={hasRun || hasUnread ? 'always' : 'hover'}
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
				{/if}
			</div>
		</div>

		{#snippet actions()}
			<button
				type="button"
				class="rounded-circle text-foreground/55 hover:bg-foreground/10 hover:text-foreground inline-flex h-8 w-8 cursor-pointer items-center justify-center border border-transparent bg-transparent transition-all duration-200"
				onpointerdown={(e) => e.stopPropagation()}
				onclick={(e) => {
					e.stopPropagation()
					if (openThreadMenuId !== thread.id) {
						menuButtonEl = e.currentTarget as HTMLElement
					}
					onToggleMenu(thread.id)
				}}
				aria-label={hasRun
					? 'active run'
					: hasUnread
						? 'unread messages'
						: 'thread actions'}
				title={hasRun ? 'agent is running...' : hasUnread ? 'unread messages' : 'Menu'}
			>
				{#if hasRun}
					<div class="relative flex h-2 w-2 shrink-0 items-center justify-center">
						<span
							class="absolute inline-flex h-full w-full animate-ping rounded-full bg-yellow-400 opacity-75"
						></span>
						<span class="relative inline-flex h-1.5 w-1.5 rounded-full bg-yellow-400"
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
		{/snippet}
	</SidebarListItem>

	<PopupMenu
		open={openThreadMenuId === thread.id}
		anchorEl={menuButtonEl}
		onClose={onCloseMenu}
		data-thread-menu
	>
		<button
			type="button"
			class="rounded-pill text-foreground/80 hover:bg-foreground/10 flex w-full cursor-pointer items-center gap-2 border-none bg-transparent px-3 py-2 text-left text-sm transition-colors duration-150"
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
			<Share class="h-4 w-4" />
			share
		</button>
		<button
			type="button"
			class="rounded-pill text-foreground/80 hover:bg-foreground/10 flex w-full cursor-pointer items-center gap-2 border-none bg-transparent px-3 py-2 text-left text-sm transition-colors duration-150"
			onclick={(e) => {
				e.stopPropagation()
				onCloseMenu()
				onRequestEdit(thread)
			}}
		>
			<InfoCircle class="h-4 w-4" />
			properties
		</button>
		<button
			type="button"
			class="rounded-pill text-foreground/80 hover:bg-foreground/10 flex w-full cursor-pointer items-center gap-2 border-none bg-transparent px-3 py-2 text-left text-sm transition-colors duration-150"
			onclick={(e) => {
				e.stopPropagation()
				onCloseMenu()
				console.log('thread action', 'archive', thread.id)
			}}
		>
			<ArchiveBox class="h-4 w-4" />
			archive
		</button>
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
	</PopupMenu>
</div>
