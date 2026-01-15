<script lang="ts">
	import { browser } from '$app/environment'
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import { page } from '$app/state'
	import type { StreamMessage } from '$lib/api/streaming'
	import { v1Client } from '$lib/api/v1/client'
	import ArchiveBox from '$lib/components/icons/ArchiveBox.svelte'
	import ChatPlus from '$lib/components/icons/ChatPlus.svelte'
	import ChatSidebarChatsSection from '$lib/components/sidebar/chat-sidebar/ChatSidebarChatsSection.svelte'
	import ChatSidebarHeader from '$lib/components/sidebar/chat-sidebar/ChatSidebarHeader.svelte'
	import ChatSidebarTopActions from '$lib/components/sidebar/chat-sidebar/ChatSidebarTopActions.svelte'
	import { useSidebar } from '$lib/contexts/sidebarContext.svelte'
	import { device } from '$lib/stores/device.svelte'
	import { openModal } from '$lib/stores/modals'
	import { onThreadEvent } from '$lib/stores/notifications'
	import { isLoggedIn, recentThreads, refreshThreads, type Thread } from '$lib/stores/session'
	import {
		invalidateAll as invalidateThreadCache,
		prefetchThread,
	} from '$lib/stores/threadCache.svelte'

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
	let confirmDeleteThread = $state<{ id: string; title: string } | null>(null)
	let isDeleting = $state(false)
	let deleteError = $state<string | null>(null)
	let generatingMetadataThreadId = $state<string | null>(null)

	let closeSwipePointerId = $state<number | null>(null)
	let closeSwipeStartX = $state(0)
	let closeSwipeStartY = $state(0)
	let closeSwipeActive = $state(false)

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
			invalidateThreadCache(threadId)

			// remove from list
			recentThreads.update((threads) => threads.filter((t) => t.id !== threadId))

			// if we're viewing this thread, navigate away
			if (page.url.pathname === `/c/${threadId}`) {
				// @ts-expect-error resolve typing is narrower than our constructed URL
				void goto(resolve('/' as never), { replaceState: true })
			}
		} else if (eventType === 'thread.updated' && threadId) {
			// invalidate cache on updates
			invalidateThreadCache(threadId)

			// move thread to top and update title if available
			const rawTitle =
				(typeof patch?.title === 'string' ? patch.title : null) ??
				(typeof data?.title === 'string' ? data.title : null)
			const rawTags =
				(Array.isArray(patch?.tags) ? patch.tags : null) ??
				(Array.isArray(data?.tags) ? data.tags : null)
			recentThreads.update((threads) => {
				const idx = threads.findIndex((t) => t.id === threadId)
				if (idx === -1) return threads

				const thread = threads[idx]
				const nextTags = rawTags
					? rawTags.filter((t): t is string => typeof t === 'string')
					: null
				const updated: Thread = {
					...thread,
					title: rawTitle ?? thread.title,
					tags: nextTags ?? thread.tags,
					last_activity_at: new Date().toISOString(),
				}

				// move to top
				return [updated, ...threads.slice(0, idx), ...threads.slice(idx + 1)]
			})
		} else if (eventType === 'thread.created') {
			// refresh to get the new thread (or we could add it directly)
			void refreshThreads({ limit: 25 })
		}
	}

	$effect(() => {
		if (device.isMobile) sidebar.closeChatSidebar()
	})

	function handleSearchClick() {
		sidebar.selectChat(null)
		const isAlreadyHome = page.url.pathname === '/' && chatParam === null
		if (isAlreadyHome && browser) {
			window.dispatchEvent(new CustomEvent('nokodo:focus-home-input'))
		} else {
			// @ts-expect-error resolve typing is narrower than our constructed URL
			void goto(resolve('/' as never), { keepFocus: true, noScroll: true })
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
					window.dispatchEvent(new CustomEvent('nokodo:focus-home-input'))
				} else {
					// @ts-expect-error resolve typing is narrower than our constructed URL
					void goto(resolve('/?chat=new' as never), { keepFocus: true, noScroll: true })
				}
				if (device.isMobile) sidebar.closeChatSidebar()
			},
		},
		{
			id: 'archived-chats',
			icon: ArchiveBox,
			label: 'archived chats',
			action: () => {
				openModal('archived-chats')
				if (device.isMobile) sidebar.closeChatSidebar()
			},
		},
	]

	$effect(() => {
		if ($isLoggedIn) void refreshThreads({ limit: 25 })
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
			// @ts-expect-error resolve typing is narrower than our constructed URL
			void goto(resolve(`/c/${threadId}` as never), {
				keepFocus: true,
				noScroll: true,
			})
		}
		if (device.isMobile) sidebar.closeChatSidebar()
	}

	function requestDeleteThread(thread: Thread) {
		confirmDeleteThread = {
			id: thread.id,
			title: thread.title || 'untitled chat',
		}
	}

	async function handleGenerateThreadMetadata(threadId: string): Promise<void> {
		generatingMetadataThreadId = threadId
		try {
			const updated = await generateThreadMetadata(threadId)
			if (!updated) return

			invalidateThreadCache(threadId)
			recentThreads.update((threads) => {
				const idx = threads.findIndex((t) => t.id === threadId)
				if (idx === -1) return threads
				const current = threads[idx]
				const next: Thread = {
					...current,
					title: updated.title ?? current.title,
					tags: updated.tags ?? current.tags,
					last_activity_at: updated.last_activity_at || new Date().toISOString(),
				}
				return [next, ...threads.slice(0, idx), ...threads.slice(idx + 1)]
			})
		} finally {
			generatingMetadataThreadId = null
		}
	}

	let routeChatId = $derived.by((): string | null => {
		const match = page.url.pathname.match(/^\/c\/([^/]+)/)
		return match?.[1] ?? null
	})

	let routeChatIsInSidebar = $derived.by((): boolean => {
		if (!routeChatId) return false
		return $recentThreads.some((t) => t.id === routeChatId)
	})

	// Keep selection synced with the current route.
	// - On /c/:id: select it if visible in the sidebar; otherwise clear selection.
	// - Anywhere else: clear selection.
	$effect(() => {
		if (routeChatId && routeChatIsInSidebar) {
			if (sidebar.selectedChatId !== routeChatId) sidebar.selectChat(routeChatId)
			return
		}
		if (sidebar.selectedChatId !== null) sidebar.selectChat(null)
	})

	function onCloseSwipePointerDown(event: PointerEvent) {
		if (!device.isMobile) return
		if (!sidebar.isChatSidebarOpen) return
		closeSwipePointerId = event.pointerId
		closeSwipeStartX = event.clientX
		closeSwipeStartY = event.clientY
		closeSwipeActive = true
		;(event.currentTarget as HTMLElement | null)?.setPointerCapture?.(event.pointerId)
	}

	function onCloseSwipePointerUp(event: PointerEvent) {
		if (!closeSwipeActive) return
		if (closeSwipePointerId !== event.pointerId) return
		const dx = event.clientX - closeSwipeStartX
		const dy = event.clientY - closeSwipeStartY
		closeSwipeActive = false
		closeSwipePointerId = null

		if (Math.abs(dx) <= 80) return
		if (Math.abs(dx) <= Math.abs(dy)) return
		// Close gesture: right-to-left
		if (dx < 0) sidebar.closeChatSidebar()
	}

	function onCloseSwipePointerCancel(event: PointerEvent) {
		if (closeSwipePointerId !== event.pointerId) return
		closeSwipeActive = false
		closeSwipePointerId = null
	}
	$effect(() => {
		if (!openThreadMenuId) return
		const handleDocClick = (event: MouseEvent) => {
			const target = event.target as HTMLElement | null
			if (!target) return
			if (target.closest('[data-thread-menu]')) return
			openThreadMenuId = null
		}
		document.addEventListener('click', handleDocClick)
		return () => document.removeEventListener('click', handleDocClick)
	})

	async function deleteThread(threadId: string): Promise<number | null> {
		const { response } = await v1Client().DELETE('/threads/{thread_id}', {
			params: { path: { thread_id: threadId } },
		})
		return response.status
	}

	async function generateThreadMetadata(threadId: string): Promise<Thread | null> {
		const { data, error } = await v1Client().POST('/threads/{thread_id}/metadata/generate', {
			params: {
				path: { thread_id: threadId },
			},
			body: { replace: false, model_id: null },
		})
		if (error || !data) return null
		return data
	}
</script>

{#if device.isMobile && sidebar.isChatSidebarOpen}
	<!-- svelte-ignore a11y_click_events_have_key_events -->
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div class="fixed inset-0 z-40 bg-black/40" onclick={() => sidebar.closeChatSidebar()}></div>

	<!-- Right-edge swipe catcher to close fullscreen sidebar (mobile only) -->
	<div
		class="fixed inset-y-0 right-0 z-60 w-8"
		role="presentation"
		style="touch-action: pan-y;"
		onpointerdown={onCloseSwipePointerDown}
		onpointerup={onCloseSwipePointerUp}
		onpointercancel={onCloseSwipePointerCancel}
	></div>
{/if}

<aside
	class="chat-sidebar fixed inset-y-0 left-0 z-50 h-screen overflow-hidden border-r border-white/10 backdrop-blur-[20px] backdrop-saturate-180 transition-[width,transform] duration-300 ease-in-out {sidebar.isChatSidebarOpen
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
	aria-hidden={device.isMobile ? !sidebar.isChatSidebarOpen : false}
	onclick={(event) => {
		if (device.isMobile) return
		if (sidebar.isChatSidebarOpen) return
		const target = event.target as HTMLElement | null
		if (target?.closest('button, [role="button"], a')) return
		// Allow clicking anywhere in the collapsed sidebar to open it.
		// Buttons will still run their own actions.
		sidebar.openChatSidebar()
	}}
>
	<!-- Gradient overlay (replaces ::before pseudo-element) -->
	<div
		class="pointer-events-none absolute inset-0 bg-linear-to-br from-white/10 via-white/5 to-transparent opacity-70 transition-opacity duration-200 group-hover:opacity-100"
	></div>
	<div
		class="pointer-events-none absolute inset-0 bg-white/3 opacity-0 transition-opacity duration-200 group-hover:opacity-100"
	></div>

	<div class="relative z-20 flex h-full min-h-0 w-full flex-col items-center gap-1.5 px-3 py-4">
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

		<hr class="border-white/10" />

		<ChatSidebarTopActions {showTopLabels} {items} onSearchClick={handleSearchClick} />

		{#if renderExpandedContent}
			<ChatSidebarChatsSection
				{expandedContentVisible}
				isLoggedIn={$isLoggedIn}
				threads={$recentThreads}
				selectedChatId={sidebar.selectedChatId}
				{openThreadMenuId}
				{generatingMetadataThreadId}
				onPrefetchThread={(threadId) => prefetchThread(threadId)}
				onOpenThread={openThread}
				onToggleMenu={toggleThreadMenu}
				onCloseMenu={closeThreadMenu}
				onGenerateMetadata={handleGenerateThreadMetadata}
				onRequestDelete={requestDeleteThread}
			/>
		{/if}
	</div>
</aside>

{#if confirmDeleteThread}
	<!-- svelte-ignore a11y_click_events_have_key_events -->
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div
		class="fixed inset-0 z-60 flex items-center justify-center bg-black/55 px-6"
		onclick={() => {
			if (!isDeleting) {
				confirmDeleteThread = null
				deleteError = null
			}
		}}
	>
		<div
			class="liquid-glass rounded-container w-full max-w-sm px-6 py-5 shadow-[0_32px_64px_rgba(12,10,30,0.6)]"
			onclick={(e) => e.stopPropagation()}
		>
			<span class="liquid-glass__highlight" aria-hidden="true"></span>
			<div class="liquid-glass__content">
				<div class="text-lg font-semibold text-white/90">delete chat?</div>
				<div class="mt-2 text-sm text-white/60">{confirmDeleteThread.title}</div>

				{#if deleteError}
					<div
						class="mt-3 rounded-2xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white/70"
					>
						{deleteError}
					</div>
				{/if}

				<div class="mt-5 flex items-center justify-end gap-2">
					<button
						type="button"
						class="rounded-2xl border border-white/10 bg-transparent px-4 py-2 text-sm text-white/80 transition-colors duration-150 hover:bg-white/5"
						disabled={isDeleting}
						onclick={() => {
							confirmDeleteThread = null
							deleteError = null
						}}
					>
						cancel
					</button>
					<button
						type="button"
						class="rounded-2xl border border-white/10 bg-white/10 px-4 py-2 text-sm text-white/90 transition-colors duration-150 hover:bg-white/15 disabled:opacity-60"
						disabled={isDeleting}
						onclick={() => {
							void (async () => {
								if (!confirmDeleteThread) return
								isDeleting = true
								deleteError = null
								try {
									const status = await deleteThread(confirmDeleteThread.id)
									if (status !== 204) {
										deleteError = 'could not delete chat'
										return
									}

									sidebar.selectChat(null)
									await refreshThreads({ limit: 25 })

									if (page.url.pathname === `/c/${confirmDeleteThread.id}`) {
										// @ts-expect-error resolve typing is narrower than our constructed URL
										await goto(resolve('/' as never), {
											keepFocus: true,
											noScroll: true,
										})
									}

									confirmDeleteThread = null
								} catch {
									deleteError = 'could not delete chat'
								} finally {
									isDeleting = false
								}
							})()
						}}
					>
						{isDeleting ? 'deleting…' : 'delete'}
					</button>
				</div>
			</div>
		</div>
	</div>
{/if}
