<script lang="ts">
	import type { Thread } from '$lib/stores/chat.svelte'

	import ChatBubble from '$lib/components/icons/ChatBubble.svelte'

	import ChatSidebarThreadRow from './ChatSidebarThreadRow.svelte'

	export let expandedContentVisible: boolean

	export let isLoggedIn: boolean
	export let threads: Thread[]
	export let selectedChatId: string | null

	export let openThreadMenuId: string | null
	export let onPrefetchThread: (threadId: string) => void
	export let onOpenThread: (threadId: string) => void | Promise<void>

	export let onToggleMenu: (threadId: string) => void
	export let onCloseMenu: () => void
	export let onRequestEdit: (thread: Thread) => void
	export let onDeleteThread: (thread: Thread) => void | boolean | Promise<void | boolean>
</script>

<!-- Chats Section -->
<div
	class="flex min-h-0 w-full flex-1 flex-col transition-opacity duration-200 ease-out {expandedContentVisible
		? 'opacity-100'
		: 'pointer-events-none opacity-0'}"
	inert={!expandedContentVisible || undefined}
>
	<div class="w-full px-3" aria-hidden="true">
		<div
			class="via-foreground/18 h-px w-full bg-linear-to-r from-transparent to-transparent"
		></div>
	</div>
	<div class="flex min-h-0 w-full flex-1 flex-col gap-1.5 overflow-hidden">
		<div class="mt-2 mb-1 flex items-center gap-2 px-5">
			<ChatBubble class="text-foreground/70 h-4 w-4 shrink-0" />
			<h3 class="text-foreground/60 text-xs font-semibold uppercase">chats</h3>
		</div>
		<div class="min-h-0 flex-1 overflow-y-auto">
			<div class="flex min-h-full flex-col space-y-0.5 px-3">
				{#if !isLoggedIn}
					<div class="flex flex-1 flex-col items-center justify-center">
						<div
							class="rounded-container border-foreground/14 bg-foreground/5 text-foreground/55 w-full overflow-hidden border p-3 text-center text-sm whitespace-nowrap"
						>
							log in to see your recent chats
						</div>
					</div>
				{:else if threads.length === 0}
					<div class="flex flex-1 flex-col items-center justify-center">
						<div
							class="rounded-container border-foreground/14 bg-foreground/5 text-foreground/55 w-full overflow-hidden border p-3 text-center text-sm whitespace-nowrap"
						>
							no chats yet
						</div>
					</div>
				{:else}
					{#each threads as thread, index (thread.id)}
						<div class={index === threads.length - 1 ? 'pb-5' : ''}>
							<ChatSidebarThreadRow
								{thread}
								selected={selectedChatId === thread.id}
								onPrefetch={onPrefetchThread}
								{onOpenThread}
								{openThreadMenuId}
								{onToggleMenu}
								{onCloseMenu}
								{onRequestEdit}
								{onDeleteThread}
							/>
						</div>
					{/each}
				{/if}
			</div>
		</div>
	</div>
</div>
