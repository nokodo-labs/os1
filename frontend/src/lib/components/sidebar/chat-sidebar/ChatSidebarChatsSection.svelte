<script lang="ts">
	import type { Thread } from '$lib/stores/session'

	import ChatBubble from '$lib/components/icons/ChatBubble.svelte'

	import ChatSidebarThreadRow from './ChatSidebarThreadRow.svelte'

	export let expandedContentVisible: boolean

	export let isLoggedIn: boolean
	export let threads: Thread[]
	export let selectedChatId: string | null

	export let openThreadMenuId: string | null
	export let generatingMetadataThreadId: string | null
	export let onPrefetchThread: (threadId: string) => void
	export let onOpenThread: (threadId: string) => void | Promise<void>

	export let onToggleMenu: (threadId: string) => void
	export let onCloseMenu: () => void
	export let onGenerateMetadata: (threadId: string) => void | Promise<void>
	export let onRequestDelete: (thread: Thread) => void
</script>

<!-- Chats Section -->
<div
	class="flex min-h-0 w-full flex-1 flex-col transition-opacity duration-200 ease-out {expandedContentVisible
		? 'opacity-100'
		: 'pointer-events-none opacity-0'}"
	aria-hidden={!expandedContentVisible}
>
	<hr class="my-2 border-white/10" />
	<div class="flex min-h-0 w-full flex-1 flex-col gap-1.5 overflow-hidden px-2">
		<div class="mb-1 flex items-center gap-2 px-3">
			<ChatBubble className="h-4 w-4 shrink-0 text-white/60" />
			<h3 class="text-xs font-semibold text-white/50 uppercase">chats</h3>
		</div>
		<div class="min-h-0 flex-1 overflow-y-auto">
			<div class="flex flex-col space-y-0.5">
				{#if !isLoggedIn}
					<div class="flex flex-1 flex-col items-center justify-center">
						<div
							class="rounded-container w-full overflow-hidden border border-white/10 bg-white/5 p-3 text-center text-sm whitespace-nowrap text-white/55"
						>
							log in to see your recent chats
						</div>
					</div>
				{:else if threads.length === 0}
					<div class="flex flex-1 flex-col items-center justify-center">
						<div
							class="rounded-container w-full overflow-hidden border border-white/10 bg-white/5 p-3 text-center text-sm whitespace-nowrap text-white/55"
						>
							no chats yet
						</div>
					</div>
				{:else}
					{#each threads as thread (thread.id)}
						<ChatSidebarThreadRow
							{thread}
							selected={selectedChatId === thread.id}
							onPrefetch={onPrefetchThread}
							{onOpenThread}
							{openThreadMenuId}
							{onToggleMenu}
							{onCloseMenu}
							{generatingMetadataThreadId}
							{onGenerateMetadata}
							{onRequestDelete}
						/>
					{/each}
				{/if}
			</div>
		</div>
	</div>
</div>
