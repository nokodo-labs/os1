<script lang="ts">
	import { tick } from 'svelte'

	import type { Thread } from '$lib/stores/chat.svelte'

	import ShimmerText from '$lib/components/effects/ShimmerText.svelte'
	import ChatBubble from '$lib/components/icons/ChatBubble.svelte'
	import { device } from '$lib/stores/device.svelte'

	import ChatSidebarThreadRow from './ChatSidebarThreadRow.svelte'

	interface Props {
		expandedContentVisible: boolean
		isLoggedIn: boolean
		threads: Thread[]
		selectedChatId: string | null
		isLoadingMoreThreads: boolean
		hasMoreThreads: boolean
		openThreadMenuId: string | null
		onPrefetchThread: (threadId: string) => void
		onOpenThread: (threadId: string) => void | Promise<void>
		onLoadMoreThreads: () => void | Promise<void>
		onToggleMenu: (threadId: string) => void
		onCloseMenu: () => void
		onRequestEdit: (thread: Thread) => void
		onDeleteThread: (thread: Thread) => void | boolean | Promise<void | boolean>
	}

	let {
		expandedContentVisible,
		isLoggedIn,
		threads,
		selectedChatId,
		isLoadingMoreThreads,
		hasMoreThreads,
		openThreadMenuId,
		onPrefetchThread,
		onOpenThread,
		onLoadMoreThreads,
		onToggleMenu,
		onCloseMenu,
		onRequestEdit,
		onDeleteThread,
	}: Props = $props()

	const LOAD_MORE_THRESHOLD_PX = 720

	let scrollContainer = $state<HTMLDivElement | null>(null)

	function requestLoadMoreThreads(): void {
		if (!scrollContainer || !isLoggedIn || !hasMoreThreads || isLoadingMoreThreads) return
		const remaining =
			scrollContainer.scrollHeight - scrollContainer.scrollTop - scrollContainer.clientHeight
		const threshold = Math.max(LOAD_MORE_THRESHOLD_PX, scrollContainer.clientHeight * 0.75)
		if (remaining > threshold) return
		void onLoadMoreThreads()
	}

	$effect(() => {
		void threads.length
		void expandedContentVisible
		void hasMoreThreads
		void isLoadingMoreThreads
		if (!expandedContentVisible || !hasMoreThreads || isLoadingMoreThreads) return
		void (async () => {
			await tick()
			requestLoadMoreThreads()
		})()
	})
</script>

<!-- Chats Section -->
<div
	class="flex min-h-0 flex-1 flex-col transition-opacity duration-200 ease-out {device.isMobile
		? 'w-full'
		: 'w-72 shrink-0'} {expandedContentVisible
		? 'opacity-100'
		: 'pointer-events-none opacity-0'}"
	inert={!expandedContentVisible || undefined}
>
	<div class="w-full px-3" aria-hidden="true">
		<div
			class="via-foreground/18 h-px w-full bg-linear-to-r from-transparent to-transparent"
		></div>
	</div>
	<div class="flex min-h-0 w-full flex-1 flex-col overflow-hidden">
		<div
			bind:this={scrollContainer}
			class="min-h-0 flex-1 overflow-y-auto"
			onscroll={requestLoadMoreThreads}
		>
			<div class="flex min-h-full flex-col space-y-0.5 px-3">
				<div class="mt-2 mb-1 flex items-center gap-2 px-2">
					<ChatBubble class="text-foreground/70 h-4 w-4 shrink-0" />
					<h3 class="text-foreground/60 text-xs font-semibold uppercase">chats</h3>
				</div>
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
						<div
							class={index === threads.length - 1
								? device.isMobile
									? 'pb-20'
									: 'pb-5'
								: ''}
						>
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
					{#if isLoadingMoreThreads}
						<div class="text-foreground/45 px-2 py-3 text-center text-xs font-medium">
							<ShimmerText className="inline-block">loading more chats</ShimmerText>
						</div>
					{/if}
				{/if}
			</div>
		</div>
	</div>
</div>
