<script lang="ts">
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import { page } from '$app/state'
	import type { StreamMessage } from '$lib/api/streaming'
	import { v1Client } from '$lib/api/v1/client'
	import ArchiveBox from '$lib/components/icons/ArchiveBox.svelte'
	import ChatBubble from '$lib/components/icons/ChatBubble.svelte'
	import ChatPlus from '$lib/components/icons/ChatPlus.svelte'
	import ChevronLeft from '$lib/components/icons/ChevronLeft.svelte'
	import EllipsisHorizontal from '$lib/components/icons/EllipsisHorizontal.svelte'
	import Search from '$lib/components/icons/Search.svelte'
	import Sidebar from '$lib/components/icons/Sidebar.svelte'
	import Sparkles from '$lib/components/icons/Sparkles.svelte'
	import * as ScrollArea from '$lib/components/ui/scroll-area'
	import * as Separator from '$lib/components/ui/separator'
	import * as Tooltip from '$lib/components/ui/tooltip'
	import { useSidebar } from '$lib/contexts/sidebarContext.svelte'
	import { openModal } from '$lib/stores/modals'
	import { onThreadEvent } from '$lib/stores/notifications'
	import { isLoggedIn, recentThreads, refreshThreads, type Thread } from '$lib/stores/session'
	import {
		invalidateAll as invalidateThreadCache,
		prefetchThread,
	} from '$lib/stores/threadCache.svelte'

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

	let openThreadMenuId = $state<string | null>(null)
	let confirmDeleteThread = $state<{ id: string; title: string } | null>(null)
	let isDeleting = $state(false)
	let deleteError = $state<string | null>(null)
	let generatingMetadataThreadId = $state<string | null>(null)

	type TriggerProps = Record<string, unknown>

	let isMobile = $state(false)
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
			if (typeof window !== 'undefined') {
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

			if (typeof window !== 'undefined') {
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
			if (typeof window === 'undefined') return
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
		if (typeof window === 'undefined') return
		const mq = window.matchMedia('(max-width: 888px)')
		const update = () => {
			isMobile = mq.matches
			if (isMobile) sidebar.closeChatSidebar()
		}
		update()
		mq.addEventListener('change', update)
		return () => mq.removeEventListener('change', update)
	})

	function handleSearchClick() {
		sidebar.selectChat(null)
		const isAlreadyHome =
			page.url.pathname === '/' && page.url.searchParams.get('chat') === null
		if (isAlreadyHome && typeof window !== 'undefined') {
			window.dispatchEvent(new CustomEvent('nokodo:focus-home-input'))
		} else {
			// @ts-expect-error resolve typing is narrower than our constructed URL
			void goto(resolve('/' as never), { keepFocus: true, noScroll: true })
		}
		if (isMobile) sidebar.closeChatSidebar()
	}

	interface SidebarItem {
		id: string
		icon: typeof Search
		label: string
		action: () => void | Promise<void>
	}

	const items: SidebarItem[] = [
		{
			id: 'new-chat',
			icon: ChatPlus,
			label: 'new chat',
			action: async () => {
				sidebar.selectChat(null)
				const isAlreadyNew =
					page.url.pathname === '/' && page.url.searchParams.get('chat') === 'new'
				if (isAlreadyNew && typeof window !== 'undefined') {
					window.dispatchEvent(new CustomEvent('nokodo:focus-home-input'))
				} else {
					// @ts-expect-error resolve typing is narrower than our constructed URL
					void goto(resolve('/?chat=new' as never), { keepFocus: true, noScroll: true })
				}
				if (isMobile) sidebar.closeChatSidebar()
			},
		},
		{
			id: 'archived-chats',
			icon: ArchiveBox,
			label: 'archived chats',
			action: () => {
				openModal('archived-chats')
			},
		},
	]

	$effect(() => {
		if ($isLoggedIn) void refreshThreads({ limit: 25 })
	})

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
		if (!isMobile) return
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

	function formatTime(iso: string): string {
		const date = new Date(iso)
		if (Number.isNaN(date.getTime())) return ''
		const now = Date.now()
		const diff = now - date.getTime()
		const hours = Math.floor(diff / 3_600_000)
		if (hours < 1) return 'just now'
		if (hours < 24) return `${hours}h ago`
		return date.toLocaleDateString()
	}
</script>

{#if isMobile && sidebar.isChatSidebarOpen}
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
	class="chat-sidebar group fixed inset-y-0 left-0 z-50 h-screen overflow-hidden border-r border-white/10 backdrop-blur-[20px] backdrop-saturate-180 transition-[width,transform] duration-300 ease-in-out {isMobile
		? 'w-full'
		: sidebar.isChatSidebarOpen
			? 'w-72'
			: 'w-18'} {sidebar.isChatSidebarOpen
		? 'translate-x-0'
		: isMobile
			? 'pointer-events-none -translate-x-full'
			: 'translate-x-0'}"
	style="background-color: var(--accent-bg);"
	aria-hidden={isMobile ? !sidebar.isChatSidebarOpen : false}
	onclick={() => {
		if (isMobile) return
		if (sidebar.isChatSidebarOpen) return
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
		<!-- Logo / Brand with Close Button -->
		<div class="relative grid w-full grid-cols-[auto_auto_auto] items-center">
			<button
				class="group relative flex h-12 w-12 shrink-0 cursor-pointer items-center justify-center rounded-full border border-transparent bg-transparent text-white/80 transition-all duration-200 hover:text-white"
				onclick={() => {
					if (!sidebar.isChatSidebarOpen) {
						sidebar.toggleChatSidebar()
					}
					sidebar.selectChat(null)
				}}
				aria-label="Home"
			>
				<!-- Symmetrical float animation (centered) -->
				<div
					class="relative flex h-8 w-8 shrink-0 animate-[float_3s_ease-in-out_infinite] items-center justify-center rounded-full shadow-[0_4px_12px_var(--accent-shadow),inset_0_2px_8px_rgba(255,255,255,0.3)] transition-[background,box-shadow] duration-300 group-hover:shadow-[0_6px_16px_var(--accent-shadow),inset_0_2px_8px_rgba(255,255,255,0.4)]"
					style="background: linear-gradient(to bottom right, var(--accent-primary), var(--accent-secondary));"
				>
					{#if !sidebar.isChatSidebarOpen}
						<div
							class="absolute flex scale-75 items-center justify-center text-white opacity-0 transition-all duration-300 group-hover:scale-100 group-hover:opacity-100"
						>
							<Sidebar className="h-4 w-4" />
						</div>
					{/if}
				</div>
			</button>

			<div
				class="flex flex-none items-center justify-center overflow-hidden px-2 transition-[opacity,transform] duration-200 ease-out {showTopLabels
					? 'translate-y-0 opacity-100'
					: '-translate-y-0.5 opacity-0'}"
				aria-hidden={!showTopLabels}
			>
				<img
					src="https://nokodo.net/media/images/logo_full.svg"
					alt="nokodo logo"
					class="h-7 w-auto shrink-0 -translate-y-[5px] object-contain"
				/>
			</div>

			<!-- Close button -->
			<button
				class="flex h-8 w-8 shrink-0 cursor-pointer items-center justify-center border border-transparent bg-transparent text-white/50 transition-all duration-200 hover:text-white active:scale-[0.97] {!isCompactLayout
					? 'opacity-100'
					: 'pointer-events-none opacity-0'}"
				onclick={(e) => {
					e.stopPropagation()
					sidebar.closeChatSidebar()
				}}
				aria-label="Close sidebar"
			>
				<ChevronLeft className="h-5 w-5" />
			</button>
		</div>

		<Separator.Root class="bg-white/10" />

		<!-- Search -->
		<Tooltip.Root delayDuration={300} disabled={!isCompactLayout}>
			<Tooltip.Trigger>
				{#snippet child({ props }: { props: TriggerProps })}
					<button
						{...props}
						class="relative flex h-12 w-full shrink-0 cursor-pointer items-center rounded-full border border-transparent bg-transparent py-0 text-white transition-all duration-200 hover:border-white/10 hover:bg-white/5"
						onclick={handleSearchClick}
						aria-label="Search"
					>
						<div class="flex h-12 w-12 shrink-0 items-center justify-center">
							<Search className="h-5 w-5" />
						</div>
						<span
							class="min-w-0 overflow-hidden text-sm font-medium whitespace-nowrap transition-[opacity,transform,max-width] duration-200 ease-out {showTopLabels
								? 'max-w-40 translate-x-0 opacity-100'
								: 'max-w-0 -translate-x-1 opacity-0'}"
							aria-hidden={!showTopLabels}
						>
							search
						</span>
					</button>
				{/snippet}
			</Tooltip.Trigger>
			{#if isCompactLayout}
				<Tooltip.Content
					side="right"
					class="rounded-2xl border border-white/10 bg-black/90 px-3 py-2 text-sm text-white shadow-[0_4px_12px_rgba(0,0,0,0.3)]"
				>
					<p>search</p>
				</Tooltip.Content>
			{/if}
		</Tooltip.Root>

		<!-- Main Actions -->
		{#each items as item (item.id)}
			{@const Icon = item.icon}
			<Tooltip.Root delayDuration={300} disabled={!isCompactLayout}>
				<Tooltip.Trigger>
					{#snippet child({ props }: { props: TriggerProps })}
						<button
							{...props}
							class="relative flex h-12 w-full shrink-0 cursor-pointer items-center rounded-full border border-transparent bg-transparent py-0 text-white transition-all duration-200 hover:border-white/10 hover:bg-white/5"
							onclick={item.action}
							aria-label={item.label}
						>
							<div class="flex h-12 w-12 shrink-0 items-center justify-center">
								<Icon className="h-5 w-5" />
							</div>
							<span
								class="min-w-0 overflow-hidden text-sm font-medium whitespace-nowrap transition-[opacity,transform,max-width] duration-200 ease-out {showTopLabels
									? 'max-w-44 translate-x-0 opacity-100'
									: 'max-w-0 -translate-x-1 opacity-0'}"
								aria-hidden={!showTopLabels}
							>
								{item.label}
							</span>
						</button>
					{/snippet}
				</Tooltip.Trigger>
				{#if isCompactLayout}
					<Tooltip.Content
						side="right"
						class="rounded-2xl border border-white/10 bg-black/90 px-3 py-2 text-sm text-white shadow-[0_4px_12px_rgba(0,0,0,0.3)]"
					>
						<p>{item.label}</p>
					</Tooltip.Content>
				{/if}
			</Tooltip.Root>
		{/each}

		{#if renderExpandedContent}
			<!-- Chats Section -->
			<div
				class="flex min-h-0 w-full flex-1 flex-col transition-[opacity,transform] duration-200 ease-out {expandedContentVisible
					? 'translate-x-0 opacity-100'
					: 'pointer-events-none -translate-x-1 opacity-0'}"
				aria-hidden={!expandedContentVisible}
			>
				<Separator.Root class="my-2 bg-white/10" />
				<div class="flex min-h-0 w-full flex-1 flex-col gap-1.5 overflow-hidden px-2">
					<div class="mb-1 flex items-center gap-2 px-3">
						<ChatBubble className="h-4 w-4 shrink-0 text-white/60" />
						<h3 class="text-xs font-semibold text-white/50 uppercase">chats</h3>
					</div>
					<ScrollArea.Root class="min-h-0 flex-1">
						<div class="flex flex-col space-y-0.5">
							{#if !$isLoggedIn}
								<div class="flex flex-1 flex-col items-center justify-center">
									<div
										class="rounded-container w-full overflow-hidden border border-white/10 bg-white/5 p-3 text-center text-sm whitespace-nowrap text-white/55"
									>
										log in to see your recent chats
									</div>
								</div>
							{:else if $recentThreads.length === 0}
								<div class="flex flex-1 flex-col items-center justify-center">
									<div
										class="rounded-container w-full overflow-hidden border border-white/10 bg-white/5 p-3 text-center text-sm whitespace-nowrap text-white/55"
									>
										no chats yet
									</div>
								</div>
							{:else}
								{#each $recentThreads as thread (thread.id)}
									<div
										class="group/chat relative min-w-0"
										role="listitem"
										onmouseenter={() => prefetchThread(thread.id)}
									>
										<div
											class="rounded-container relative flex cursor-pointer items-center justify-between gap-2 border border-transparent bg-transparent px-4 py-2 pr-12 text-left text-white transition-all duration-200 hover:border-white/10 hover:bg-white/5 {sidebar.selectedChatId ===
											thread.id
												? 'shadow-[inset_0_2px_8px_rgba(255,255,255,0.1)]'
												: ''}"
											style={sidebar.selectedChatId === thread.id
												? 'background-color: var(--accent-bg); border-color: var(--accent-border);'
												: ''}
											onclick={async () => {
												sidebar.selectChat(thread.id)
												if (page.url.pathname === `/c/${thread.id}`) return
												// @ts-expect-error resolve typing is narrower than our constructed URL
												void goto(resolve(`/c/${thread.id}` as never), {
													keepFocus: true,
													noScroll: true,
												})
											}}
											role="button"
											tabindex="0"
											onkeydown={async (e) => {
												if (e.key === 'Enter' || e.key === ' ') {
													e.preventDefault()
													sidebar.selectChat(thread.id)
													if (page.url.pathname === `/c/${thread.id}`)
														return
													// @ts-expect-error resolve typing is narrower than our constructed URL
													void goto(resolve(`/c/${thread.id}` as never), {
														keepFocus: true,
														noScroll: true,
													})
												}
											}}
										>
											<div class="min-w-0 flex-1 overflow-hidden">
												<div class="flex items-center gap-2">
													<span
														class="overflow-hidden text-sm font-medium text-ellipsis whitespace-nowrap"
													>
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
													<span class="shrink-0 text-xs text-white/50">
														{formatTime(thread.last_activity_at ?? '')}
													</span>
												</div>
											</div>

											<button
												type="button"
												class="absolute top-1/2 right-2 flex h-8 w-8 -translate-y-1/2 items-center justify-center rounded-full border border-transparent bg-transparent text-white/50 opacity-0 transition-all duration-200 group-hover/chat:opacity-100 hover:bg-white/10 hover:text-white"
												onclick={(e) => {
													e.stopPropagation()
													openThreadMenuId =
														openThreadMenuId === thread.id
															? null
															: thread.id
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
													{#if !thread.title || thread.title.trim() === '' || !thread.tags || thread.tags.length === 0}
														<button
															type="button"
															class="flex w-full cursor-pointer items-center gap-2 rounded-2xl border-none bg-transparent px-3 py-2 text-left text-sm text-white/80 transition-colors duration-150 hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-60"
															disabled={generatingMetadataThreadId ===
																thread.id}
															onclick={(e) => {
																e.stopPropagation()
																openThreadMenuId = null
																void (async () => {
																	generatingMetadataThreadId =
																		thread.id
																	try {
																		const updated =
																			await generateThreadMetadata(
																				thread.id
																			)
																		if (!updated) return

																		invalidateThreadCache(
																			thread.id
																		)
																		recentThreads.update(
																			(threads) => {
																				const idx =
																					threads.findIndex(
																						(t) =>
																							t.id ===
																							thread.id
																					)
																				if (idx === -1)
																					return threads
																				const current =
																					threads[idx]
																				const next: Thread =
																					{
																						...current,
																						title:
																							updated.title ??
																							current.title,
																						tags:
																							updated.tags ??
																							current.tags,
																						last_activity_at:
																							updated.last_activity_at ||
																							new Date().toISOString(),
																					}
																				return [
																					next,
																					...threads.slice(
																						0,
																						idx
																					),
																					...threads.slice(
																						idx + 1
																					),
																				]
																			}
																		)
																	} finally {
																		generatingMetadataThreadId =
																			null
																	}
																})()
															}}
														>
															<Sparkles className="h-4 w-4" />
															generate data
														</button>
														<div
															class="my-1 h-px w-full bg-white/10"
														></div>
													{/if}
													{#each ['share', 'download', 'rename', 'clone', 'move', 'archive'] as action (action)}
														<button
															type="button"
															class="flex w-full cursor-pointer items-center rounded-2xl border-none bg-transparent px-3 py-2 text-left text-sm text-white/80 transition-colors duration-150 hover:bg-white/10"
															onclick={(e) => {
																e.stopPropagation()
																openThreadMenuId = null
																console.log(
																	'thread action',
																	action,
																	thread.id
																)
															}}
														>
															{action}
														</button>
													{/each}
													<button
														type="button"
														class="mt-1 flex w-full cursor-pointer items-center rounded-2xl border-none bg-transparent px-3 py-2 text-left text-sm text-white/80 transition-colors duration-150 hover:bg-white/10"
														onclick={(e) => {
															e.stopPropagation()
															openThreadMenuId = null
															confirmDeleteThread = {
																id: thread.id,
																title:
																	thread.title || 'untitled chat',
															}
														}}
													>
														delete
													</button>
												</div>
											{/if}
										</div>
									</div>
								{/each}
							{/if}
						</div>
					</ScrollArea.Root>
				</div>
			</div>
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

<style>
	/* Symmetrical float animation (centered at 0, oscillates up/down) */
	@keyframes float {
		0%,
		100% {
			transform: translateY(0px);
		}
		50% {
			transform: translateY(-8px);
		}
	}
</style>
