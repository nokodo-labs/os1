<script lang="ts">
	import SidebarListItem from '$lib/components/sidebar/SidebarListItem.svelte'
	import Timestamp from '$lib/components/Timestamp.svelte'
	import type { Thread } from '$lib/stores/chat.svelte'

	import DeleteButton from '$lib/components/DeleteButton.svelte'
	import ArchiveBox from '$lib/components/icons/ArchiveBox.svelte'
	import EllipsisHorizontal from '$lib/components/icons/EllipsisHorizontal.svelte'
	import Pencil from '$lib/components/icons/Pencil.svelte'
	import Share from '$lib/components/icons/Share.svelte'
	import { device } from '$lib/stores/device.svelte'
	import { modals } from '$lib/stores/modals.svelte'
	import { scale } from 'svelte/transition'

	export let thread: Thread
	export let selected: boolean
	export let onOpenThread: (threadId: string) => void | Promise<void>
	export let onPrefetch: (threadId: string) => void

	export let openThreadMenuId: string | null
	export let onToggleMenu: (threadId: string) => void
	export let onCloseMenu: () => void

	export let onRequestEdit: (thread: Thread) => void
	export let onDeleteThread: (thread: Thread) => void | boolean | Promise<void | boolean>
</script>

<div class="group/chat relative min-w-0" role="listitem">
	<SidebarListItem
		{selected}
		radiusClass="rounded-container"
		paddingClass="px-4 py-2"
		className="gap-2 text-white"
		onPrefetch={() => onPrefetch(thread.id)}
		onSelect={async () => {
			await onOpenThread(thread.id)
		}}
		actionsVisibility={device.isTouch ? 'always' : 'hover'}
	>
		<div class="min-w-0 overflow-hidden">
			<div class="flex items-center gap-2">
				<span class="overflow-hidden text-sm font-medium text-ellipsis whitespace-nowrap">
					{thread.title || 'untitled chat'}
				</span>
			</div>
			<div class="mt-0.5 flex items-center gap-2">
				{#if thread.tags && thread.tags.length > 0}
					<span
						class="min-w-0 flex-1 truncate text-xs text-white/45"
						title={thread.tags.join(', ')}
					>
						{thread.tags.join(' · ')}
					</span>
				{/if}
				<Timestamp
					timestamp={new Date(thread.last_activity_at ?? '')}
					mode="relative"
					minUnit="hour"
					className="shrink-0 text-xs text-white/50"
				/>
			</div>
		</div>

		{#snippet actions()}
			<button
				type="button"
				class="rounded-circle inline-flex h-8 w-8 cursor-pointer items-center justify-center border border-transparent bg-transparent text-white/50 transition-all duration-200 hover:bg-white/10 hover:text-white"
				onclick={(e) => {
					e.stopPropagation()
					onToggleMenu(thread.id)
				}}
				aria-label="thread actions"
			>
				<EllipsisHorizontal class="h-4 w-4" />
			</button>
		{/snippet}
	</SidebarListItem>

	{#if openThreadMenuId === thread.id}
		<div
			transition:scale={{ duration: 160, start: 0.96, opacity: 0 }}
			data-thread-menu
			class="animate-popup-right liquid-metal rounded-container absolute top-full right-2 z-50 mt-2 w-52 p-2 shadow-[0_24px_48px_rgba(12,10,30,0.55)]"
		>
			<button
				type="button"
				class="flex w-full cursor-pointer items-center gap-2 rounded-2xl border-none bg-transparent px-3 py-2 text-left text-sm text-white/80 transition-colors duration-150 hover:bg-white/10"
				onclick={(e) => {
					e.stopPropagation()
					onCloseMenu()
					modals.open('share-resource', {
						resource: 'thread',
						id: thread.id,
						title: thread.title ?? null,
					})
				}}
			>
				<Share class="h-4 w-4" />
				share
			</button>
			<button
				type="button"
				class="flex w-full cursor-pointer items-center gap-2 rounded-2xl border-none bg-transparent px-3 py-2 text-left text-sm text-white/80 transition-colors duration-150 hover:bg-white/10"
				onclick={(e) => {
					e.stopPropagation()
					onCloseMenu()
					onRequestEdit(thread)
				}}
			>
				<Pencil variant="solid" class="h-4 w-4" />
				edit
			</button>
			<button
				type="button"
				class="flex w-full cursor-pointer items-center gap-2 rounded-2xl border-none bg-transparent px-3 py-2 text-left text-sm text-white/80 transition-colors duration-150 hover:bg-white/10"
				onclick={(e) => {
					e.stopPropagation()
					onCloseMenu()
					console.log('thread action', 'archive', thread.id)
				}}
			>
				<ArchiveBox class="h-4 w-4" />
				archive
			</button>
			<div class="my-1 h-px w-full bg-white/10"></div>
			<div class="mt-1">
				<DeleteButton
					confirm={true}
					stopPropagation={true}
					modalText={{
						title: 'delete chat?',
						description: thread.title || 'untitled chat',
					}}
					onDelete={() => onDeleteThread(thread)}
				/>
			</div>
		</div>
	{/if}
</div>
