<script lang="ts">
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import { page } from '$app/state'
	import { getV1BaseUrl } from '$lib/api/v1/client'
	import { getAccessToken } from '$lib/auth/session'
	import ArchiveBox from '$lib/components/icons/ArchiveBox.svelte'
	import ChatBubble from '$lib/components/icons/ChatBubble.svelte'
	import ChatPlus from '$lib/components/icons/ChatPlus.svelte'
	import ChevronLeft from '$lib/components/icons/ChevronLeft.svelte'
	import EllipsisHorizontal from '$lib/components/icons/EllipsisHorizontal.svelte'
	import Search from '$lib/components/icons/Search.svelte'
	import Sidebar from '$lib/components/icons/Sidebar.svelte'
	import * as ScrollArea from '$lib/components/ui/scroll-area'
	import * as Separator from '$lib/components/ui/separator'
	import * as Tooltip from '$lib/components/ui/tooltip'
	import { useSidebar } from '$lib/contexts/sidebarContext.svelte'
	import { openModal } from '$lib/stores/modals'
	import { isLoggedIn, recentThreads, refreshThreads } from '$lib/stores/session'

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

	type TriggerProps = Record<string, unknown>

	let isMobile = $state(false)
	let closeSwipePointerId = $state<number | null>(null)
	let closeSwipeStartX = $state(0)
	let closeSwipeStartY = $state(0)
	let closeSwipeActive = $state(false)

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
		// TODO: Open global search overlay
		console.log('Open global search')
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
				// For same-route navigations (/?chat=new), avoid ViewTransition overlays.
				await goto('/?chat=new', { keepFocus: true, noScroll: true })
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
		const token = getAccessToken()
		if (!token) return null

		const res = await fetch(`${getV1BaseUrl()}/threads/${threadId}`, {
			method: 'DELETE',
			headers: {
				Authorization: `Bearer ${token}`,
			},
		})
		return res.status
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
	class="chat-sidebar group fixed inset-y-0 left-0 z-50 h-screen border-r border-white/10 backdrop-blur-[20px] backdrop-saturate-180 transition-[width,transform] duration-300 ease-in-out {isMobile
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

	<div
		class="pointer-events-none relative z-20 flex h-full w-full flex-col items-center gap-2 px-3 py-4 *:pointer-events-auto"
	>
		<!-- Logo / Brand with Close Button -->
		<!-- Removed gap-2 to prevent left-shift when close button is hidden -->
		<div
			class="relative flex w-full items-center {sidebar.isChatSidebarOpen
				? 'justify-between'
				: 'justify-start'}"
		>
			<button
				class="group relative flex items-center justify-center {sidebar.isChatSidebarOpen
					? 'max-w-[calc(100%-2.5rem)] flex-1'
					: ''} h-12 w-12 shrink-0 cursor-pointer border-none bg-transparent p-0 text-white/80 transition-transform duration-150 hover:scale-[1.05] hover:text-white active:scale-[0.97]"
				style="z-index: 10;"
				onclick={() => {
					if (!sidebar.isChatSidebarOpen) {
						sidebar.toggleChatSidebar()
					}
					sidebar.selectChat(null)
				}}
				aria-label="Home"
			>
				<div class="relative flex shrink-0 items-center justify-center">
					<!-- Changed animate-bounce to animate-float (custom) for symmetrical oscillation -->
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
					<!-- Increased left margin for logo from ml-1 to ml-3 -->
					<!-- Removed {#if} block, used CSS transition for width/opacity for smooth reveal -->
					<div
						class="flex items-center overflow-hidden transition-[max-width,opacity,margin] duration-300 ease-in-out {sidebar.isChatSidebarOpen
							? 'ml-3 max-w-[220px] opacity-100'
							: 'ml-0 max-w-0 opacity-0'}"
					>
						<img
							src="https://nokodo.net/media/images/logo_full.svg"
							alt="nokodo logo"
							class="h-7 w-auto -translate-y-[5px] object-contain"
						/>
					</div>
				</div>
			</button>

			<!-- Close button (only when expanded) -->
			<!-- Added absolute positioning or z-index to ensure clickable -->
			<button
				class="relative z-20 flex h-8 shrink-0 cursor-pointer items-center justify-center border-none bg-transparent text-white/70 transition-transform duration-150 hover:scale-[1.05] hover:text-white active:scale-[0.97] {sidebar.isChatSidebarOpen
					? 'ml-auto w-8 opacity-100'
					: 'pointer-events-none w-0 overflow-hidden opacity-0'}"
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
		<Tooltip.Root delayDuration={300} disabled={sidebar.isChatSidebarOpen}>
			<Tooltip.Trigger>
				{#snippet child({ props }: { props: TriggerProps })}
					<button
						{...props}
						class="relative flex h-12 w-full shrink-0 cursor-pointer items-center justify-start gap-3 rounded-xl border border-transparent bg-transparent px-3 py-0 text-white transition-all duration-200 hover:border-white/10 hover:bg-white/5"
						onclick={handleSearchClick}
						aria-label="Search"
					>
						<Search className="h-5 w-5 shrink-0" />
						<span
							class="text-sm font-medium whitespace-nowrap transition-[opacity,width] duration-300 {sidebar.isChatSidebarOpen
								? 'w-auto opacity-100'
								: 'w-0 overflow-hidden opacity-0'}">search</span
						>
					</button>
				{/snippet}
			</Tooltip.Trigger>
			{#if !sidebar.isChatSidebarOpen}
				<Tooltip.Content
					side="right"
					class="rounded-lg border border-white/10 bg-black/90 px-3 py-2 text-sm text-white shadow-[0_4px_12px_rgba(0,0,0,0.3)]"
				>
					<p>search</p>
				</Tooltip.Content>
			{/if}
		</Tooltip.Root>

		<!-- Main Actions -->
		{#each items as item (item.id)}
			{@const Icon = item.icon}
			<Tooltip.Root delayDuration={300} disabled={sidebar.isChatSidebarOpen}>
				<Tooltip.Trigger>
					{#snippet child({ props }: { props: TriggerProps })}
						<button
							{...props}
							class="relative flex h-12 w-full shrink-0 cursor-pointer items-center justify-start gap-3 rounded-xl border border-transparent bg-transparent px-3 py-0 text-white transition-all duration-200 hover:border-white/10 hover:bg-white/5"
							onclick={item.action}
							aria-label={item.label}
						>
							<Icon className="h-5 w-5 shrink-0" />
							<span
								class="text-sm font-medium whitespace-nowrap transition-[opacity,width] duration-300 {sidebar.isChatSidebarOpen
									? 'w-auto opacity-100'
									: 'w-0 overflow-hidden opacity-0'}">{item.label}</span
							>
						</button>
					{/snippet}
				</Tooltip.Trigger>
				{#if !sidebar.isChatSidebarOpen}
					<Tooltip.Content
						side="right"
						class="rounded-lg border border-white/10 bg-black/90 px-3 py-2 text-sm text-white shadow-[0_4px_12px_rgba(0,0,0,0.3)]"
					>
						<p>{item.label}</p>
					</Tooltip.Content>
				{/if}
			</Tooltip.Root>
		{/each}

		<!-- Chats Section -->
		<Separator.Root class="my-2 bg-white/10" />
		<div
			class="flex w-full flex-1 flex-col gap-2 overflow-hidden px-2 transition-[opacity,transform] duration-300 ease-in-out {sidebar.isChatSidebarOpen
				? 'translate-x-0 opacity-100'
				: 'pointer-events-none -translate-x-2 opacity-0'}"
		>
			<div class="mb-1 flex items-center gap-2 px-3">
				<ChatBubble className="h-4 w-4 shrink-0 text-white/60" />
				<h3 class="text-xs font-semibold text-white/50 uppercase">chats</h3>
			</div>
			<ScrollArea.Root class="h-full">
				<div class="space-y-1">
					{#if !$isLoggedIn}
						<div
							class="rounded-xl border border-white/10 bg-white/5 p-3 text-sm text-white/55"
						>
							log in to see your recent chats
						</div>
					{:else if $recentThreads.length === 0}
						<div
							class="rounded-xl border border-white/10 bg-white/5 p-3 text-sm text-white/55"
						>
							no chats yet
						</div>
					{:else}
						{#each $recentThreads as thread (thread.id)}
							<div class="group/chat relative">
								<div
									class="relative flex cursor-pointer items-center justify-between gap-2 rounded-xl border border-transparent bg-transparent p-3 pr-12 text-left text-white transition-all duration-200 hover:border-white/10 hover:bg-white/5 {sidebar.selectedChatId ===
									thread.id
										? 'shadow-[inset_0_2px_8px_rgba(255,255,255,0.1)]'
										: ''}"
									style={sidebar.selectedChatId === thread.id
										? 'background-color: var(--accent-bg); border-color: var(--accent-border);'
										: ''}
									onclick={async () => {
										sidebar.selectChat(thread.id)
										await goto(resolve(`/c/${thread.id}`), {
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
											await goto(resolve(`/c/${thread.id}`), {
												keepFocus: true,
												noScroll: true,
											})
										}
									}}
								>
									<div class="min-w-0 flex-1">
										<div class="mb-1 flex items-center gap-2">
											<span
												class="overflow-hidden text-sm font-medium text-ellipsis whitespace-nowrap"
											>
												{thread.title || 'untitled chat'}
											</span>
										</div>
										<span class="text-xs text-white/50">
											{formatTime(thread.last_activity_at ?? '')}
										</span>
									</div>

									<button
										type="button"
										class="absolute top-1/2 right-2 flex h-8 w-8 -translate-y-1/2 items-center justify-center rounded-lg border border-transparent bg-transparent text-white/50 opacity-0 transition-all duration-200 group-hover/chat:opacity-100 hover:bg-white/10 hover:text-white"
										onclick={(e) => {
											e.stopPropagation()
											openThreadMenuId =
												openThreadMenuId === thread.id ? null : thread.id
										}}
										aria-label="thread actions"
									>
										<EllipsisHorizontal className="h-4 w-4" />
									</button>

									{#if openThreadMenuId === thread.id}
										<div
											data-thread-menu
											class="absolute top-full right-2 z-50 mt-2 w-52 rounded-2xl border border-white/10 bg-black/60 p-2 shadow-[0_24px_48px_rgba(12,10,30,0.55)]"
										>
											{#each ['share', 'download', 'rename', 'clone', 'move', 'archive'] as action}
												<button
													type="button"
													class="flex w-full cursor-pointer items-center rounded-xl border-none bg-transparent px-3 py-2 text-left text-sm text-white/80 transition-colors duration-150 hover:bg-white/10"
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
												class="mt-1 flex w-full cursor-pointer items-center rounded-xl border-none bg-transparent px-3 py-2 text-left text-sm text-white/80 transition-colors duration-150 hover:bg-white/10"
												onclick={(e) => {
													e.stopPropagation()
													openThreadMenuId = null
													confirmDeleteThread = {
														id: thread.id,
														title: thread.title || 'untitled chat',
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
			class="liquid-glass w-full max-w-sm rounded-3xl px-6 py-5 shadow-[0_32px_64px_rgba(12,10,30,0.6)]"
			onclick={(e) => e.stopPropagation()}
		>
			<span class="liquid-glass__highlight" aria-hidden="true"></span>
			<div class="liquid-glass__content">
				<div class="text-lg font-semibold text-white/90">delete chat?</div>
				<div class="mt-2 text-sm text-white/60">{confirmDeleteThread.title}</div>

				{#if deleteError}
					<div
						class="mt-3 rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white/70"
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
										await goto('/', { keepFocus: true, noScroll: true })
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
