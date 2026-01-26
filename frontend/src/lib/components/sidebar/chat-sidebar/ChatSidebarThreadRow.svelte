<script lang="ts">
	import Timestamp from '$lib/components/Timestamp.svelte'
	import type { Thread } from '$lib/stores/chat.svelte'

	import DeleteButton from '$lib/components/DeleteButton.svelte'
	import ArchiveBox from '$lib/components/icons/ArchiveBox.svelte'
	import EllipsisHorizontal from '$lib/components/icons/EllipsisHorizontal.svelte'
	import Pencil from '$lib/components/icons/Pencil.svelte'
	import Share from '$lib/components/icons/Share.svelte'
	import { modals } from '$lib/stores/modals.svelte'

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

<div class="group/chat relative min-w-0" role="listitem" onmouseenter={() => onPrefetch(thread.id)}>
	<div
		class="rounded-container relative flex cursor-pointer items-center justify-between gap-2 border border-transparent bg-transparent px-4 py-2 pr-12 text-left text-white transition-all duration-200 hover:border-white/10 hover:bg-white/5 {selected
			? 'shadow-[inset_0_2px_8px_rgba(255,255,255,0.1)]'
			: ''}"
		style={selected
			? 'background-color: var(--accent-bg); border-color: var(--accent-border);'
			: ''}
		onclick={async () => {
			await onOpenThread(thread.id)
		}}
		role="button"
		tabindex="0"
		onkeydown={async (e) => {
			if (e.key === 'Enter' || e.key === ' ') {
				e.preventDefault()
				await onOpenThread(thread.id)
			}
		}}
	>
		<div class="min-w-0 flex-1 overflow-hidden">
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

		<button
			type="button"
			class="absolute top-1/2 right-2 flex h-8 w-8 -translate-y-1/2 items-center justify-center rounded-full border border-transparent bg-transparent text-white/50 opacity-0 transition-all duration-200 group-hover/chat:opacity-100 hover:bg-white/10 hover:text-white"
			onclick={(e) => {
				e.stopPropagation()
				onToggleMenu(thread.id)
			}}
			aria-label="thread actions"
		>
			<EllipsisHorizontal className="h-4 w-4" />
		</button>

		{#if openThreadMenuId === thread.id}
			<div
				data-thread-menu
				class="liquid-metal rounded-container absolute top-full right-2 z-50 mt-2 w-52 p-2 shadow-[0_24px_48px_rgba(12,10,30,0.55)]"
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
					<Share className="h-4 w-4" />
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
					<Pencil className="h-4 w-4" />
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
					<ArchiveBox className="h-4 w-4" />
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
</div>
