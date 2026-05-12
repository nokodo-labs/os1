<script lang="ts">
	import type { Thread } from '$lib/stores/chat.svelte'

	import EmptyState from '$lib/components/EmptyState.svelte'
	import FloatingScrollTopButton from '$lib/components/FloatingScrollTopButton.svelte'
	import ChatBubble from '$lib/components/icons/ChatBubble.svelte'
	import LoadingMoreIndicator from '$lib/components/LoadingMoreIndicator.svelte'
	import type { ResourceProjectOption } from '$lib/components/widgets/ResourceProjectsMenu.svelte'
	import { device } from '$lib/stores/device.svelte'
	import { projects } from '$lib/stores/projects.svelte'
	import { canEditAccessLevel, resourceAccess } from '$lib/stores/resourceAccess.svelte'
	import SvelteVirtualList from '@humanspeak/svelte-virtual-list'
	import { tick } from 'svelte'

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

	type ChatSidebarRow =
		| { kind: 'header'; id: 'header' }
		| { kind: 'thread'; id: string; thread: Thread }
		| { kind: 'loading'; id: 'loading' }

	let listShellEl = $state<HTMLDivElement | null>(null)
	let listViewportEl = $state<HTMLElement | null>(null)

	const manageableProjectOptions = $derived.by((): ResourceProjectOption[] =>
		projects.list
			.filter((project) =>
				canEditAccessLevel(resourceAccess.level('project', project.id, project.owner_id))
			)
			.map((project) => ({
				id: project.id,
				name: project.name,
				owner_id: project.owner_id,
			}))
	)
	const lastThreadId = $derived(threads.at(-1)?.id ?? null)
	const threadRows = $derived.by((): ChatSidebarRow[] => {
		const rows: ChatSidebarRow[] = [{ kind: 'header', id: 'header' }]
		for (const thread of threads) rows.push({ kind: 'thread', id: thread.id, thread })
		if (isLoadingMoreThreads) rows.push({ kind: 'loading', id: 'loading' })
		return rows
	})

	function requestLoadMoreThreads(): void | Promise<void> {
		if (!isLoggedIn || !hasMoreThreads || isLoadingMoreThreads) return
		return onLoadMoreThreads()
	}

	$effect(() => {
		if (!isLoggedIn || !expandedContentVisible) return
		void projects.load()
	})

	$effect(() => {
		if (!isLoggedIn || !expandedContentVisible) return
		for (const project of projects.list) {
			void resourceAccess.ensure('project', project.id, project.owner_id)
		}
	})

	$effect(() => {
		const shell = listShellEl
		const rowCount = threadRows.length
		if (!shell || rowCount === 0) {
			listViewportEl = null
			return
		}

		let cancelled = false
		void tick().then(() => {
			if (cancelled) return
			const viewport = shell.querySelector('.chat-sidebar-thread-viewport')
			listViewportEl = viewport instanceof HTMLElement ? viewport : null
		})
		return () => {
			cancelled = true
		}
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
		{#if !isLoggedIn}
			<div class="px-3">
				<div class="mt-2 mb-1 flex items-center gap-2 px-2">
					<ChatBubble class="text-foreground/70 h-4 w-4 shrink-0" />
					<h3 class="text-foreground/60 text-xs font-semibold uppercase">chats</h3>
				</div>
				<EmptyState label="log in to see your recent chats" compact class="flex-1" />
			</div>
		{:else if threads.length === 0}
			<div class="px-3">
				<div class="mt-2 mb-1 flex items-center gap-2 px-2">
					<ChatBubble class="text-foreground/70 h-4 w-4 shrink-0" />
					<h3 class="text-foreground/60 text-xs font-semibold uppercase">chats</h3>
				</div>
				<EmptyState label="no chats yet" compact class="flex-1" />
			</div>
		{:else}
			<div bind:this={listShellEl} class="relative min-h-0 w-full flex-1 overflow-hidden">
				<SvelteVirtualList
					items={threadRows}
					defaultEstimatedItemHeight={54}
					bufferSize={16}
					loadMoreThreshold={12}
					hasMore={hasMoreThreads && !isLoadingMoreThreads}
					onLoadMore={requestLoadMoreThreads}
					containerClass="relative h-full min-h-0 w-full overflow-hidden"
					viewportClass="chat-sidebar-thread-viewport absolute inset-0 w-full overflow-y-auto"
					contentClass="relative min-h-full w-full"
					itemsClass="absolute top-0 left-0 flex w-full flex-col gap-0.5 px-3"
				>
					{#snippet renderItem(row)}
						{#if row.kind === 'header'}
							<div class="mt-2 mb-1 flex items-center gap-2 px-2">
								<ChatBubble class="text-foreground/70 h-4 w-4 shrink-0" />
								<h3 class="text-foreground/60 text-xs font-semibold uppercase">
									chats
								</h3>
							</div>
						{:else if row.kind === 'loading'}
							<LoadingMoreIndicator className="py-3" label="loading more chats" />
						{:else}
							<div
								class={row.thread.id === lastThreadId && !isLoadingMoreThreads
									? device.isMobile
										? 'pb-20'
										: 'pb-5'
									: ''}
							>
								<ChatSidebarThreadRow
									thread={row.thread}
									selected={selectedChatId === row.thread.id}
									onPrefetch={onPrefetchThread}
									{onOpenThread}
									{openThreadMenuId}
									{onToggleMenu}
									{onCloseMenu}
									{onRequestEdit}
									{onDeleteThread}
									projectOptions={manageableProjectOptions}
								/>
							</div>
						{/if}
					{/snippet}
				</SvelteVirtualList>
				<FloatingScrollTopButton target={listViewportEl} />
			</div>
		{/if}
	</div>
</div>
