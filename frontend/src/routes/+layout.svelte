<script lang="ts">
	import { page } from '$app/stores'
	import { configureApiAuth } from '$lib/api/auth'
	import { eventStreamClient } from '$lib/api/eventStream'
	import { getAccessToken } from '$lib/auth/session'
	import type { BackgroundType } from '$lib/components/backgrounds/BackgroundManager.svelte'
	import BackgroundManager from '$lib/components/backgrounds/BackgroundManager.svelte'
	import DebugMenu from '$lib/components/debug/DebugMenu.svelte'
	import ChevronRight from '$lib/components/icons/ChevronRight.svelte'
	import ArchivedChatsModal from '$lib/components/modals/ArchivedChatsModal.svelte'
	import SettingsModal from '$lib/components/modals/SettingsModal.svelte'
	import ChatSidebar from '$lib/components/sidebar/ChatSidebar.svelte'
	import Dock from '$lib/components/system/Dock.svelte'
	import Island from '$lib/components/system/Island.svelte'
	import * as Tooltip from '$lib/components/ui/tooltip'
	import { createDebugUiContext } from '$lib/contexts/debugUiContext.svelte'
	import { createSidebarContext, useSidebar } from '$lib/contexts/sidebarContext.svelte'
	import { createSystemChromeContext } from '$lib/contexts/systemChromeContext.svelte'
	import { createThemeContext } from '$lib/contexts/themeContext.svelte'
	import { activeModal, closeModal } from '$lib/stores/modals'
	import '$lib/styles/liquid-glass.css'
	import '../app.css'

	configureApiAuth()

	// Initialize event stream if already logged in (page load/refresh)
	const existingToken = getAccessToken()
	if (existingToken) {
		eventStreamClient.connect(existingToken)
	}

	// Initialize sidebar context
	createSidebarContext()
	const sidebar = useSidebar() as {
		readonly isChatSidebarOpen: boolean
		openChatSidebar: () => void
		closeChatSidebar: () => void
	}
	// Initialize system chrome context
	const chrome = createSystemChromeContext()
	// DEV ONLY: Debug UI state (persisted locally)
	createDebugUiContext()
	// Initialize theme context
	const theme = createThemeContext()

	// DEV ONLY: Background switcher
	let currentBackground = $state<BackgroundType>('darkveil')
	let { children } = $props()

	const isAuthRoute = $derived.by(() => {
		const path = $page.url.pathname
		return path === '/login' || path === '/signup'
	})

	let isMobileViewport = $state(false)
	$effect(() => {
		if (typeof window === 'undefined') return
		const mq = window.matchMedia('(max-width: 888px)')
		const update = () => {
			isMobileViewport = mq.matches
		}
		update()
		mq.addEventListener('change', update)
		return () => mq.removeEventListener('change', update)
	})

	const isChatSwipeEligibleRoute = $derived.by(() => {
		const path = $page.url.pathname
		return path === '/' || path.startsWith('/c/')
	})

	const sidebarSpacerWidthClass = $derived.by(() => {
		if (isMobileViewport) return 'w-0'
		return sidebar.isChatSidebarOpen ? 'w-72' : 'w-18'
	})

	function maybeCloseDockFromMobileShellClick(event: MouseEvent) {
		if (!isMobileViewport) return
		if (!chrome.isDockOpen) return
		const target = event.target as HTMLElement | null
		if (!target) return
		if (target.closest('[data-dock-panel]')) return
		chrome.closeDock()
	}

	let dockSwipePointerId = $state<number | null>(null)
	let dockSwipeStartX = $state(0)
	let dockSwipeStartY = $state(0)
	let dockSwipeActive = $state(false)

	function onDockPointerDown(event: PointerEvent) {
		if (!isMobileViewport) return
		if (!chrome.isDockOpen) return
		const target = event.target as HTMLElement | null
		if (!target) return
		if (target.closest('[data-dock-panel]')) return

		dockSwipePointerId = event.pointerId
		dockSwipeStartX = event.clientX
		dockSwipeStartY = event.clientY
		dockSwipeActive = true
		;(event.currentTarget as HTMLElement | null)?.setPointerCapture?.(event.pointerId)
	}

	function onDockPointerMove(event: PointerEvent) {
		if (!dockSwipeActive) return
		if (dockSwipePointerId !== event.pointerId) return
		// Prevent the gesture from being consumed as a scroll.
		event.preventDefault()
	}

	function onDockPointerUp(event: PointerEvent) {
		if (!dockSwipeActive) return
		if (dockSwipePointerId !== event.pointerId) return
		const dx = event.clientX - dockSwipeStartX
		const dy = event.clientY - dockSwipeStartY
		dockSwipeActive = false
		dockSwipePointerId = null

		if (Math.abs(dx) <= 80) return
		if (Math.abs(dx) <= Math.abs(dy)) return
		// Mobile dock dismiss gesture: left-to-right
		if (dx > 0) chrome.closeDock()
	}

	function onDockPointerCancel(event: PointerEvent) {
		if (dockSwipePointerId !== event.pointerId) return
		dockSwipeActive = false
		dockSwipePointerId = null
	}

	let sidebarSwipePointerId = $state<number | null>(null)
	let sidebarSwipeStartX = $state(0)
	let sidebarSwipeStartY = $state(0)
	let sidebarSwipeActive = $state(false)

	function onMainPointerDown(event: PointerEvent) {
		if (!isMobileViewport) return
		if (!isChatSwipeEligibleRoute) return
		if (chrome.isDockOpen) return
		if (sidebar.isChatSidebarOpen) return
		// Only start from the left edge to avoid interfering with normal interactions
		if (event.clientX > 24) return

		sidebarSwipePointerId = event.pointerId
		sidebarSwipeStartX = event.clientX
		sidebarSwipeStartY = event.clientY
		sidebarSwipeActive = true
		;(event.currentTarget as HTMLElement | null)?.setPointerCapture?.(event.pointerId)
	}

	function onMainPointerMove(event: PointerEvent) {
		if (!sidebarSwipeActive) return
		if (sidebarSwipePointerId !== event.pointerId) return
		// Keep the gesture from being consumed as a scroll when we intend a horizontal swipe.
		event.preventDefault()
	}

	function onMainPointerUp(event: PointerEvent) {
		if (!sidebarSwipeActive) return
		if (sidebarSwipePointerId !== event.pointerId) return
		const dx = event.clientX - sidebarSwipeStartX
		const dy = event.clientY - sidebarSwipeStartY
		sidebarSwipeActive = false
		sidebarSwipePointerId = null

		if (Math.abs(dx) <= 80) return
		if (Math.abs(dx) <= Math.abs(dy)) return
		// Mobile sidebar reveal gesture: left-to-right
		if (dx > 0) sidebar.openChatSidebar()
	}

	function onMainPointerCancel(event: PointerEvent) {
		if (sidebarSwipePointerId !== event.pointerId) return
		sidebarSwipeActive = false
		sidebarSwipePointerId = null
	}
</script>

<Tooltip.Provider>
	<!-- Background Manager handles all backgrounds with smooth transitions -->
	<BackgroundManager type={currentBackground} config={{ color: '#0a0a0a' }}>
		<!-- DEV ONLY: Debug Menu -->
		<DebugMenu {theme} bind:currentBackground />

		{#if isAuthRoute}
			<div class="relative z-1 flex h-screen">
				<div class="relative flex min-w-0 flex-1 flex-col">
					{@render children()}
				</div>
			</div>
		{:else}
			<div class="relative z-1 flex h-screen">
				<!-- Sidebar (fixed; desktop reserves a rail, mobile uses overlay) -->
				<ChatSidebar />
				<div
					class="h-screen shrink-0 transition-[width] duration-300 ease-in-out {sidebarSpacerWidthClass}"
				></div>

				{#if isMobileViewport && isChatSwipeEligibleRoute && !chrome.isDockOpen && !sidebar.isChatSidebarOpen}
					<div
						class="fixed inset-y-0 left-0 z-20 w-6"
						role="presentation"
						style="touch-action: pan-y;"
						onpointerdown={onMainPointerDown}
						onpointermove={onMainPointerMove}
						onpointerup={onMainPointerUp}
						onpointercancel={onMainPointerCancel}
					></div>
				{/if}

				<!-- Main Content -->
				<div
					class="relative flex min-w-0 flex-1 flex-col"
					style="touch-action: pan-y;"
					onpointerdown={onMainPointerDown}
					onpointermove={onMainPointerMove}
					onpointerup={onMainPointerUp}
					onpointercancel={onMainPointerCancel}
				>
					<!-- System chrome: island (top header) -->
					<div
						class="mx-auto w-full max-w-7xl px-[clamp(10px,4vw,32px)] pt-[clamp(12px,4vw,32px)]"
					>
						<Island />
					</div>

					{@render children()}
				</div>

				<!-- System chrome: dock (right sidebar overlay) -->
				<div
					class="dock-shell fixed top-0 right-0 bottom-0 z-30 px-6 pt-8 pb-8 {chrome.isDockOpen
						? 'pointer-events-auto'
						: 'pointer-events-none'}"
					role="presentation"
					style="touch-action: pan-y;"
					onclick={maybeCloseDockFromMobileShellClick}
					onpointerdown={onDockPointerDown}
					onpointermove={onDockPointerMove}
					onpointerup={onDockPointerUp}
					onpointercancel={onDockPointerCancel}
				>
					<div
						class="relative h-full w-full transition-all duration-300 ease-out {chrome.isDockOpen
							? 'translate-x-0 opacity-100'
							: 'translate-x-full opacity-0'}"
					>
						{#if chrome.isDockOpen && !isMobileViewport}
							<button
								type="button"
								class="absolute top-1/2 left-0 z-40 flex h-12 w-12 -translate-x-1/2 -translate-y-1/2 items-center justify-center text-white/80 transition-transform duration-150 hover:scale-[1.05] hover:text-white active:scale-[0.97]"
								onclick={() => chrome.closeDock()}
								aria-label="close dock"
							>
								<ChevronRight className="h-6 w-6" />
							</button>
						{/if}
						<Dock />
					</div>
				</div>

				<SettingsModal open={$activeModal === 'settings'} onClose={() => closeModal()} />
				<ArchivedChatsModal
					open={$activeModal === 'archived-chats'}
					onClose={() => closeModal()}
				/>
			</div>
		{/if}
	</BackgroundManager>
</Tooltip.Provider>

<style>
	@media (max-width: 888px) {
		.dock-shell {
			left: 0;
			width: 100%;
			padding-left: 1rem;
			padding-right: 1rem;
		}
	}
</style>
