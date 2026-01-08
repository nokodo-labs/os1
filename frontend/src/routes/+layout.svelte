<script lang="ts">
	import { onNavigate } from '$app/navigation'
	import { page } from '$app/stores'
	import { eventStreamClient } from '$lib/api/streaming'
	import { getAccessToken } from '$lib/auth/session'
	import type { BackgroundType } from '$lib/components/backgrounds/BackgroundManager.svelte'
	import BackgroundManager from '$lib/components/backgrounds/BackgroundManager.svelte'
	import ArchivedChatsModal from '$lib/components/modals/ArchivedChatsModal.svelte'
	import SettingsModal from '$lib/components/modals/SettingsModal.svelte'
	import ChatSidebar from '$lib/components/sidebar/ChatSidebar.svelte'
	import SplashController from '$lib/components/SplashController.svelte'
	import Dock from '$lib/components/system/Dock.svelte'
	import Island from '$lib/components/system/Island.svelte'
	import * as Tooltip from '$lib/components/ui/tooltip'
	import { createDebugUiContext } from '$lib/contexts/debugUiContext.svelte'
	import { createSidebarContext, useSidebar } from '$lib/contexts/sidebarContext.svelte'
	import { createSystemChromeContext } from '$lib/contexts/systemChromeContext.svelte'
	import { createThemeContext } from '$lib/contexts/themeContext.svelte'
	import { appReadiness } from '$lib/stores/appReadiness.svelte'
	import { activeModal, closeModal } from '$lib/stores/modals'
	import '$lib/styles/liquid-glass.css'
	import { onDestroy, onMount, tick } from 'svelte'
	import '../app.css'

	type ViewTransitionCapableDocument = Document & {
		startViewTransition?: (cb: () => Promise<void> | void) => void
	}

	// Global View Transitions hook.
	// This ensures transitions run for ALL navigations (links, goto(), back/forward popstate).
	// We intentionally skip same-path navigations (e.g. / <-> /?chat=new) so in-page
	// animations keep controls interactive without the ViewTransition overlay.
	onNavigate((navigation) => {
		const start = (document as ViewTransitionCapableDocument).startViewTransition
		if (!start) return

		const from = navigation.from?.url
		const to = navigation.to?.url
		if (!from || !to) return
		if (from.pathname === to.pathname) return

		return new Promise<void>((resolve) => {
			start.call(document, async () => {
				resolve()
				await navigation.complete
			})
		})
	})

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

	// Gate initial page paint behind the splash.
	const backgroundBlocker = appReadiness.createBlocker()
	function handleBackgroundReady() {
		backgroundBlocker.done()
	}
	onDestroy(() => {
		backgroundBlocker.done()
	})

	onMount(async () => {
		// Ensure the first route has had a chance to render + paint.
		await tick()
		await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()))
		appReadiness.markShellReady()
	})

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

	let mainContentShell = $state<HTMLElement | null>(null)
	let islandShell = $state<HTMLElement | null>(null)
	let islandOffsetPx = $state(0)

	$effect(() => {
		const mainEl = mainContentShell
		const islandEl = islandShell
		if (!mainEl || !islandEl) return
		const update = () => {
			const mainRect = mainEl.getBoundingClientRect()
			const islandRect = islandEl.getBoundingClientRect()
			islandOffsetPx = Math.max(0, Math.round(islandRect.bottom - mainRect.top))
		}
		update()
		const ro = new ResizeObserver(update)
		ro.observe(mainEl)
		ro.observe(islandEl)
		window.addEventListener('resize', update)
		return () => {
			window.removeEventListener('resize', update)
			ro.disconnect()
		}
	})

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

<SplashController />

<Tooltip.Provider>
	<!-- Background Manager handles all backgrounds with smooth transitions -->
	<BackgroundManager
		type={currentBackground}
		config={{ color: '#0a0a0a' }}
		onReady={handleBackgroundReady}
	>
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
					style={`touch-action: pan-y; --chrome-island-offset: ${islandOffsetPx}px;`}
					bind:this={mainContentShell}
					onpointerdown={onMainPointerDown}
					onpointermove={onMainPointerMove}
					onpointerup={onMainPointerUp}
					onpointercancel={onMainPointerCancel}
				>
					<!-- System chrome: island (top header) -->
					<div
						class="pointer-events-none absolute top-0 right-0 left-0 z-30 mx-auto w-full max-w-7xl px-[clamp(10px,4vw,32px)] pt-[clamp(12px,4vw,32px)]"
						bind:this={islandShell}
					>
						<div class="pointer-events-auto">
							<Island />
						</div>
					</div>

					{@render children()}
				</div>

				<!-- System chrome: dock (right sidebar overlay) -->
				{#if chrome.isDockOpen && !isMobileViewport}
					<div
						class="fixed inset-0 z-20"
						role="presentation"
						aria-hidden="true"
						onclick={() => chrome.closeDock()}
					></div>
				{/if}
				<div
					class="dock-shell fixed top-0 right-0 bottom-0 z-30 w-[min(31rem,calc(100vw-3rem))] px-6 pt-8 pb-8 {chrome.isDockOpen
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
						<Dock />
					</div>
				</div>

				<SettingsModal
					open={$activeModal === 'settings'}
					onClose={() => closeModal()}
					{theme}
					bind:currentBackground
				/>
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
