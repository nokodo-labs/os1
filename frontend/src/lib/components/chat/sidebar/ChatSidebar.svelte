<script lang="ts">
	import { browser } from '$app/environment'
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import { page } from '$app/state'
	import { deleteThread, updateThread } from '$lib/chat/threadActions'
	import ChatSidebarChatsSection from '$lib/components/chat/sidebar/ChatSidebarChatsSection.svelte'
	import ChatSidebarHeader from '$lib/components/chat/sidebar/ChatSidebarHeader.svelte'
	import ChatSidebarTopActions from '$lib/components/chat/sidebar/ChatSidebarTopActions.svelte'
	import ArchiveBox from '$lib/components/icons/ArchiveBox.svelte'
	import ChatPlus from '$lib/components/icons/ChatPlus.svelte'
	import ChatPropertiesModal from '$lib/components/modals/ChatPropertiesModal.svelte'
	import { useSidebar } from '$lib/contexts/sidebarContext.svelte'
	import { chat, type Thread } from '$lib/stores/chat.svelte'
	import { device } from '$lib/stores/device.svelte'
	import { modals } from '$lib/stores/modals.svelte'

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
	let editTags = $state<string[]>([])
	let isSavingEdit = $state(false)
	let editError = $state<string | null>(null)

	const sidebarTransitionMs = 300

	// these are intentionally decoupled from `sidebar.isChatSidebarOpen` so content can animate
	// during collapse/expand, instead of mounting/unmounting immediately.
	let isCompactLayout = $state(!sidebar.isChatSidebarOpen)
	let showTopLabels = $state(false)
	let renderExpandedContent = $state(sidebar.isChatSidebarOpen)
	let expandedContentVisible = $state(false)
	let didRequestInitialThreads = $state(false)

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
		if (!session.isLoggedIn) {
			didRequestInitialThreads = false
			return
		}
		if (didRequestInitialThreads) return
		didRequestInitialThreads = true
		if (chat.recentThreads.length === 0) {
			void chat.refreshThreads({ limit: 25 })
			return
		}
		void chat.fetchUnreadCounts()
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
		editTags = Array.isArray(editThread.tags) ? [...editThread.tags] : []
	})

	function closeEditModal(): void {
		if (isSavingEdit) return
		editThread = null
		editError = null
	}

	function saveEditModal(): void {
		if (isSavingEdit) return
		void (async () => {
			if (!editThread) return
			isSavingEdit = true
			editError = null

			const threadId = editThread.id
			const newTitle = editTitle.trim()
			const newTags = editTags

			const ok = await updateThread(threadId, newTitle, newTags)
			if (ok) {
				editThread = null
			} else {
				editError = 'could not save changes'
			}

			isSavingEdit = false
		})()
	}

	function shareEditThread(): void {
		if (!editThread) return
		const thread = editThread
		editThread = null
		editError = null
		modals.open('resource-access', {
			resourceType: 'thread',
			resourceId: thread.id,
			title: thread.title ?? thread.id,
		})
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
	class="chat-sidebar border-foreground/14 fixed inset-y-0 left-0 z-50 h-screen overflow-hidden border-r backdrop-blur-[20px] transition-all duration-300 ease-in-out {sidebar.isChatSidebarOpen
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
	style="background-color: var(--accent-bg);"
	inert={device.isMobile ? !sidebar.isChatSidebarOpen : undefined}
	use:expandOnClick
>
	<!-- gradient overlay (replaces ::before pseudo-element) -->
	<div
		class="from-foreground/12 via-foreground/7 pointer-events-none absolute inset-0 bg-linear-to-br to-transparent opacity-70 transition-opacity duration-200 group-hover:opacity-100"
	></div>
	<div
		class="bg-foreground/5 pointer-events-none absolute inset-0 opacity-0 transition-opacity duration-200 group-hover:opacity-100"
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
				class="via-foreground/18 h-px w-full bg-linear-to-r from-transparent to-transparent"
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
				isLoadingMoreThreads={chat.isLoadingMoreThreads}
				hasMoreThreads={chat.hasMoreThreads}
				onPrefetchThread={(threadId) => chat.threadCache.prefetchThread(threadId)}
				onOpenThread={openThread}
				onLoadMoreThreads={() => chat.loadMoreThreads()}
				onToggleMenu={toggleThreadMenu}
				onCloseMenu={closeThreadMenu}
				onRequestEdit={requestEditThread}
				onDeleteThread={handleDeleteThread}
			/>
		{/if}
	</div>
</aside>

<ChatPropertiesModal
	open={editThread !== null}
	thread={editThread}
	bind:title={editTitle}
	bind:tags={editTags}
	error={editError}
	isSaving={isSavingEdit}
	onClose={closeEditModal}
	onShare={shareEditThread}
	onSave={saveEditModal}
/>
