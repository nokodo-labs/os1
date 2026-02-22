<script lang="ts">
	import { browser } from '$app/environment'
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import { page } from '$app/state'
	import { apiClient } from '$lib/api/client'
	import type { StreamMessage } from '$lib/api/streaming'
	import ChatSidebarChatsSection from '$lib/components/chat/sidebar/ChatSidebarChatsSection.svelte'
	import ChatSidebarHeader from '$lib/components/chat/sidebar/ChatSidebarHeader.svelte'
	import ChatSidebarTopActions from '$lib/components/chat/sidebar/ChatSidebarTopActions.svelte'
	import ArchiveBox from '$lib/components/icons/ArchiveBox.svelte'
	import ChatPlus from '$lib/components/icons/ChatPlus.svelte'
	import EditChatModal from '$lib/components/modals/EditChatModal.svelte'
	import { useSidebar } from '$lib/contexts/sidebarContext.svelte'
	import { chat, type Thread } from '$lib/stores/chat.svelte'
	import { device } from '$lib/stores/device.svelte'
	import { modals } from '$lib/stores/modals.svelte'
	import { onThreadEvent } from '$lib/stores/notifications.svelte'
	import { session } from '$lib/stores/session.svelte'

	// SSG-safe query param access
	const chatParam = $derived(browser ? page.url.searchParams.get('chat') : null)

	type SidebarContext = {
		readonly isOpen: boolean
		readonly isChatSidebarOpen: boolean
		readonly selectedChatId: string | null
		toggleSidebar: () => void
		toggleChatSidebar: () => void
		selectChat: (id: string | null) => void
		openSidebar: () => void
		closeSidebar: () => void
		openChatSidebar: () => void
		closeChatSidebar: () => void
	}

	const sidebar = useSidebar() as SidebarContext

	type SidebarItem = {
		id: string
		icon: typeof ChatPlus
		label: string
		action: () => void | Promise<void>
	}

	let openThreadMenuId = $state<string | null>(null)
	let editThread = $state<Thread | null>(null)
	let editTitle = $state('')
	let editTagsCsv = $state('')
	let isSavingEdit = $state(false)
	let editError = $state<string | null>(null)

	const sidebarTransitionMs = 300

	// these are intentionally decoupled from `sidebar.isChatSidebarOpen` so content can animate
	// during collapse/expand, instead of mounting/unmounting immediately.
	let isCompactLayout = $state(!sidebar.isChatSidebarOpen)
	let showTopLabels = $state(false)
	let renderExpandedContent = $state(sidebar.isChatSidebarOpen)
	let expandedContentVisible = $state(false)

	$effect(() => {
		const isOpen = sidebar.isChatSidebarOpen
		let compactTimeout: number | null = null
		let unmountTimeout: number | null = null

		if (isOpen) {
			isCompactLayout = false
			renderExpandedContent = true
			if (browser) {
				window.requestAnimationFrame(() => {
					expandedContentVisible = true
					showTopLabels = true
				})
			} else {
				expandedContentVisible = true
				showTopLabels = true
			}
		} else {
			showTopLabels = false
			expandedContentVisible = false

			if (browser) {
				compactTimeout = window.setTimeout(() => {
					isCompactLayout = true
				}, sidebarTransitionMs)
				unmountTimeout = window.setTimeout(() => {
					renderExpandedContent = false
				}, sidebarTransitionMs)
			} else {
				isCompactLayout = true
				renderExpandedContent = false
			}
		}

		return () => {
			if (!browser) return
			if (compactTimeout !== null) window.clearTimeout(compactTimeout)
			if (unmountTimeout !== null) window.clearTimeout(unmountTimeout)
		}
	})

	// subscribe to thread events for real-time updates
	$effect(() => {
		const unsubscribe = onThreadEvent(handleThreadEvent)
		return unsubscribe
	})

	function handleThreadEvent(event: StreamMessage): void {
		const eventType = event.type
		const data = event.data as Record<string, unknown> | undefined
		const threadId = (data?.thread_id as string) || (event.thread_id as string) || ''

		const patch = (data?.patch ?? null) as {
			title?: unknown
			tags?: unknown
		} | null

		if (eventType === 'thread.deleted' && threadId) {
			// invalidate cache
			chat.threadCache.invalidateAll(threadId)

			// remove from list
			chat.removeRecentThread(threadId)

			// if we're viewing this thread, navigate away
			if (page.url.pathname === `/c/${threadId}`) {
				void goto(resolve('/'), { replaceState: true })
			}
		} else if (eventType === 'thread.updated' && threadId) {
			// invalidate cache on updates
			chat.threadCache.invalidateAll(threadId)

			// move thread to top and update title if available
			const rawTitle =
				(typeof patch?.title === 'string' ? patch.title : null) ??
				(typeof data?.title === 'string' ? data.title : null)
			const rawTags =
				(Array.isArray(patch?.tags) ? patch.tags : null) ??
				(Array.isArray(data?.tags) ? data.tags : null)
			chat.updateRecentThread(threadId, (thread) => {
				const nextTags = rawTags
					? rawTags.filter((t): t is string => typeof t === 'string')
					: null
				return {
					...thread,
					title: rawTitle ?? thread.title,
					tags: nextTags ?? thread.tags,
					last_activity_at: new Date().toISOString(),
				}
			})
		} else if (eventType === 'thread.created') {
			// refresh to get the new thread (or we could add it directly)
			void chat.refreshThreads({ limit: 25 })
		}
	}

	$effect(() => {
		if (device.isMobile) sidebar.closeChatSidebar()
	})

	function handleSearchClick() {
		sidebar.selectChat(null)
		const isAlreadyHome = page.url.pathname === '/' && chatParam === null
		if (isAlreadyHome && browser) {
			window.dispatchEvent(new CustomEvent('focus:chat-input'))
		} else {
			void goto(resolve('/'), { keepFocus: true, noScroll: true })
		}
		if (device.isMobile) sidebar.closeChatSidebar()
	}

	const items: SidebarItem[] = [
		{
			id: 'new-chat',
			icon: ChatPlus,
			label: 'new chat',
			action: async () => {
				sidebar.selectChat(null)
				const isAlreadyNew = page.url.pathname === '/' && chatParam === 'new'
				if (isAlreadyNew && browser) {
					window.dispatchEvent(new CustomEvent('focus:chat-input'))
				} else {
					window.dispatchEvent(new CustomEvent('focus:chat-input'))
					void goto(resolve('/?chat=new' as unknown as '/'), {
						keepFocus: true,
						noScroll: true,
					})
				}
				if (device.isMobile) sidebar.closeChatSidebar()
			},
		},
		{
			id: 'archived-chats',
			icon: ArchiveBox,
			label: 'archived chats',
			action: () => {
				modals.open('archived-chats')
				if (device.isMobile) sidebar.closeChatSidebar()
			},
		},
	]

	$effect(() => {
		if (session.isLoggedIn) void chat.refreshThreads({ limit: 25 })
	})

	function toggleThreadMenu(threadId: string) {
		openThreadMenuId = openThreadMenuId === threadId ? null : threadId
	}

	function closeThreadMenu() {
		openThreadMenuId = null
	}

	async function openThread(threadId: string): Promise<void> {
		sidebar.selectChat(threadId)
		if (page.url.pathname !== `/c/${threadId}`) {
			void goto(resolve(`/c/${threadId}`), {
				keepFocus: true,
				noScroll: true,
			})
		}
		if (device.isMobile) sidebar.closeChatSidebar()
	}

	function requestEditThread(thread: Thread) {
		closeThreadMenu()
		editError = null
		editThread = thread
	}

	async function handleDeleteThread(thread: Thread): Promise<boolean> {
		try {
			const status = await deleteThread(thread.id)
			if (status !== 204) return false

			sidebar.selectChat(null)
			await chat.refreshThreads({ limit: 25 })

			if (page.url.pathname === `/c/${thread.id}`) {
				await goto(resolve('/'), {
					keepFocus: true,
					noScroll: true,
				})
			}

			return true
		} catch {
			return false
		}
	}

	$effect(() => {
		if (!editThread) return
		editTitle = editThread.title ?? ''
		editTagsCsv = Array.isArray(editThread.tags) ? editThread.tags.join(', ') : ''
	})

	function closeEditModal(): void {
		if (isSavingEdit) return
		editThread = null
		editError = null
	}

	function cancelEditModal(): void {
		editThread = null
		editError = null
	}

	function saveEditModal(): void {
		void (async () => {
			isSavingEdit = true
			editError = null
			try {
				console.log('edit chat save', {
					threadId: editThread?.id,
					title: editTitle,
					tagsCsv: editTagsCsv,
				})
				editThread = null
			} catch {
				editError = 'could not save changes'
			} finally {
				isSavingEdit = false
			}
		})()
	}

	let routeChatId = $derived.by((): string | null => {
		const match = page.url.pathname.match(/^\/c\/([^/]+)/)
		return match?.[1] ?? null
	})

	let routeChatIsInSidebar = $derived.by((): boolean => {
		if (!routeChatId) return false
		return chat.recentThreads.some((t) => t.id === routeChatId)
	})

	// keep selection synced with the current route.
	// - on /c/:id: select it if visible in the sidebar; otherwise clear selection.
	// - anywhere else: clear selection.
	$effect(() => {
		if (routeChatId && routeChatIsInSidebar) {
			if (sidebar.selectedChatId !== routeChatId) sidebar.selectChat(routeChatId)
			return
		}
		if (sidebar.selectedChatId !== null) sidebar.selectChat(null)
	})

	/** svelte action: adds a click listener that expands the collapsed sidebar on desktop. */
	function expandOnClick(node: HTMLElement) {
		const handler = (event: MouseEvent) => {
			if (device.isMobile) return
			if (sidebar.isChatSidebarOpen) return
			const target = event.target as HTMLElement | null
			if (target?.closest('button, [role="button"], a')) return
			sidebar.openChatSidebar()
		}
		node.addEventListener('click', handler)
		return { destroy: () => node.removeEventListener('click', handler) }
	}

	async function deleteThread(threadId: string): Promise<number | null> {
		const { response } = await apiClient().DELETE('/v1/threads/{thread_id}', {
			params: { path: { thread_id: threadId } },
		})
		return response.status
	}
</script>

{#if device.isMobile}
	<button
		type="button"
		class="fixed inset-0 z-40 border-none bg-black/40 transition-opacity duration-300 ease-in-out {sidebar.isChatSidebarOpen
			? 'opacity-100'
			: 'pointer-events-none opacity-0'}"
		aria-label="close sidebar"
		onclick={() => sidebar.closeChatSidebar()}
		tabindex={sidebar.isChatSidebarOpen ? 0 : -1}
	></button>
{/if}

<aside
	class="chat-sidebar fixed inset-y-0 left-0 z-50 h-screen overflow-hidden border-r border-white/14 backdrop-blur-[20px] transition-all duration-300 ease-in-out {sidebar.isChatSidebarOpen
		? ''
		: 'group'} {device.isMobile
		? 'w-full'
		: sidebar.isChatSidebarOpen
			? 'w-72'
			: 'w-18'} {sidebar.isChatSidebarOpen
		? 'translate-x-0'
		: device.isMobile
			? 'pointer-events-none -translate-x-full'
			: 'translate-x-0'}"
	style="background-color: var(--accent-bg);{device.isMobile
		? ''
		: ' view-transition-name: chat-sidebar;'}"
	inert={device.isMobile ? !sidebar.isChatSidebarOpen : undefined}
	use:expandOnClick
>
	<!-- gradient overlay (replaces ::before pseudo-element) -->
	<div
		class="pointer-events-none absolute inset-0 bg-linear-to-br from-white/12 via-white/7 to-transparent opacity-70 transition-opacity duration-200 group-hover:opacity-100"
	></div>
	<div
		class="pointer-events-none absolute inset-0 bg-white/5 opacity-0 transition-opacity duration-200 group-hover:opacity-100"
	></div>

	<div class="relative z-20 flex h-full min-h-0 w-full flex-col items-center gap-3 pt-4 pb-0">
		<div class="w-full px-3">
			<ChatSidebarHeader
				isChatSidebarOpen={sidebar.isChatSidebarOpen}
				{isCompactLayout}
				{showTopLabels}
				onHomeClick={() => {
					if (!sidebar.isChatSidebarOpen) {
						sidebar.toggleChatSidebar()
					}
					sidebar.selectChat(null)
				}}
				onCloseClick={() => sidebar.closeChatSidebar()}
			/>
		</div>

		<div class="w-full px-3" aria-hidden="true">
			<div
				class="h-px w-full bg-linear-to-r from-transparent via-white/18 to-transparent"
			></div>
		</div>

		<div class="w-full px-3">
			<ChatSidebarTopActions {showTopLabels} {items} onSearchClick={handleSearchClick} />
		</div>

		{#if renderExpandedContent}
			<ChatSidebarChatsSection
				{expandedContentVisible}
				isLoggedIn={session.isLoggedIn}
				threads={chat.recentThreads}
				selectedChatId={sidebar.selectedChatId}
				{openThreadMenuId}
				onPrefetchThread={(threadId) => chat.threadCache.prefetchThread(threadId)}
				onOpenThread={openThread}
				onToggleMenu={toggleThreadMenu}
				onCloseMenu={closeThreadMenu}
				onRequestEdit={requestEditThread}
				onDeleteThread={handleDeleteThread}
			/>
		{/if}
	</div>
</aside>

<EditChatModal
	open={editThread !== null}
	thread={editThread}
	bind:title={editTitle}
	bind:tagsCsv={editTagsCsv}
	error={editError}
	isSaving={isSavingEdit}
	onClose={closeEditModal}
	onCancel={cancelEditModal}
	onSave={saveEditModal}
/>
