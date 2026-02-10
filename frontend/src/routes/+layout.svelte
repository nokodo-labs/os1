<script lang="ts">
	import { goto, onNavigate } from '$app/navigation'
	import { resolve } from '$app/paths'
	import { page } from '$app/state'
	import { markAuthReady } from '$lib/auth/session.svelte'
	import type { BackgroundType } from '$lib/components/backgrounds/BackgroundManager.svelte'
	import BackgroundManager from '$lib/components/backgrounds/BackgroundManager.svelte'
	import ChatSidebar from '$lib/components/chat/sidebar/ChatSidebar.svelte'
	import ArchivedChatsModal from '$lib/components/modals/ArchivedChatsModal.svelte'
	import ShareResourceModal from '$lib/components/modals/ShareResourceModal.svelte'
	import SplashController from '$lib/components/SplashController.svelte'
	import Dock from '$lib/components/system/Dock.svelte'
	import Island from '$lib/components/system/Island.svelte'
	import NotificationToast from '$lib/components/system/NotificationToast.svelte'
	import PendingApproval from '$lib/components/system/PendingApproval.svelte'
	import { createDebugUiContext } from '$lib/contexts/debugUiContext.svelte'
	import { createSidebarContext, useSidebar } from '$lib/contexts/sidebarContext.svelte'
	import { createSystemChromeContext } from '$lib/contexts/systemChromeContext.svelte'
	import { createThemeContext, setThemeContext } from '$lib/contexts/themeContext.svelte'
	import { initApp } from '$lib/init'
	import { appReadiness } from '$lib/stores/appReadiness.svelte'
	import { device } from '$lib/stores/device.svelte'
	import { modals } from '$lib/stores/modals.svelte'
	import { notifications } from '$lib/stores/notifications.svelte'
	import { pageTitleStore } from '$lib/stores/pageTitle.svelte'
	import { permissions } from '$lib/stores/permissions.svelte'
	import { preferences } from '$lib/stores/preferences.svelte'
	import { settingsState } from '$lib/stores/settings.svelte'
	import '$lib/styles/liquid-glass.css'
	import { onDestroy, onMount, tick } from 'svelte'
	import '../app.css'

	const PUBLIC_PATHS = new Set(['/login', '/signup'])

	type ViewTransitionCapableDocument = Document & {
		startViewTransition?: (
			cb: () => Promise<void> | void
		) => { finished?: Promise<unknown> } | void
	}

	// global View Transitions hook.
	// this ensures transitions run for ALL navigations (links, goto(), back/forward popstate).
	// we intentionally skip same-path navigations (e.g. / <-> /?chat=new) so in-page
	// animations keep controls interactive without the ViewTransition overlay.
	onNavigate((navigation) => {
		const start = (document as ViewTransitionCapableDocument).startViewTransition
		if (!start) return

		const from = navigation.from?.url
		const to = navigation.to?.url
		if (!from || !to) return
		if (from.pathname === to.pathname) return

		return new Promise<void>((resolve) => {
			const root = document.documentElement
			root.dataset.vtActive = '1'

			const transition = start.call(document, async () => {
				resolve()
				await navigation.complete
			})

			const done = () => {
				delete root.dataset.vtActive
			}

			// prefer the ViewTransition lifecycle when available.
			if (transition && typeof transition === 'object' && transition.finished) {
				transition.finished.finally(done)
				return
			}
			// fallback: at least remove after navigation completes.
			navigation.complete.finally(done)
		})
	})

	// device is initialized via initApp() onMount to avoid hydration mismatch

	// initialize sidebar context
	createSidebarContext()
	const sidebar = useSidebar() as {
		readonly isChatSidebarOpen: boolean
		openChatSidebar: () => void
		closeChatSidebar: () => void
	}
	// initialize system chrome context
	const chrome = createSystemChromeContext()
	// DEV ONLY: Debug UI state (persisted locally)
	createDebugUiContext()
	// initialize theme context and make it available to child components
	const theme = createThemeContext()
	setThemeContext(theme)

	// background is directly reactive from the store
	const currentBackground = $derived.by(() => {
		const isAuth = page.url.pathname === '/login' || page.url.pathname === '/signup'
		if (isAuth) {
			const authBg: BackgroundType =
				settingsState.data?.ui?.auth_pages_background ?? 'lightrays'
			return authBg
		}
		return (
			preferences.data.appearance.background ??
			settingsState.data?.ui?.default_background ??
			'darkveil'
		)
	})

	// access gate state
	let pendingApproval = $state<boolean>(false)

	let { children } = $props()

	// Island offset tracking for fixed positioning with blur effect
	let mainContentShell = $state<HTMLElement | null>(null)
	let islandShell = $state<HTMLElement | null>(null)

	$effect(() => {
		const mainEl = mainContentShell
		const islandEl = islandShell
		if (!mainEl || !islandEl) return
		const update = () => {
			const mainRect = mainEl.getBoundingClientRect()
			const islandRect = islandEl.getBoundingClientRect()
			const offset = Math.max(0, Math.round(islandRect.bottom - mainRect.top))
			mainEl.style.setProperty('--chrome-island-offset', `${offset}px`)
			// set the island's left position to align with main content
			islandEl.style.setProperty('--island-left', `${mainRect.left}px`)
		}
		update()
		const ro = new ResizeObserver(update)
		ro.observe(mainEl)
		ro.observe(islandEl)
		window.addEventListener('resize', update)
		return () => {
			ro.disconnect()
			window.removeEventListener('resize', update)
		}
	})

	// gate initial page paint behind the splash.
	const backgroundBlocker = appReadiness.createBlocker()
	function handleBackgroundReady() {
		backgroundBlocker.done()
	}
	onDestroy(() => {
		backgroundBlocker.done()
	})

	onMount(async () => {
		// ensure the first route has had a chance to render + paint.
		await tick()
		await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()))
		appReadiness.markShellReady()

		// don't run auth redirects on not-found routes.
		// this keeps 404s visible even when the user is logged out.
		if (page.status === 404) {
			markAuthReady()
			return
		}

		// initialize app (auth restoration, settings, event stream)
		const { authenticated, token } = await initApp()
		const isPublic = PUBLIC_PATHS.has(page.url.pathname)

		// auth guard: redirect unauthenticated users from private routes
		if (!authenticated && !isPublic) {
			const next = page.url.pathname
			void goto(resolve('/login'), { replaceState: true, state: { next } })
			return
		}

		// auth guard: redirect authenticated users away from auth routes
		if (token && isPublic) {
			void goto(resolve('/'), { replaceState: true })
			return
		}

		pendingApproval = false
		if (token) {
			// access gate: show pending approval if user lacks frontend access
			await permissions.refresh()
			if (!permissions.hasPermission('frontend:access')) {
				pendingApproval = true
			}
		}
	})

	const isAuthRoute = $derived.by(() => {
		const path = page.url.pathname
		return path === '/login' || path === '/signup'
	})

	const isChatSwipeEligibleRoute = $derived.by(() => {
		const path = page.url.pathname
		return path === '/' || path.startsWith('/c/')
	})

	// generic left layout inset (used by master/detail scaffolds like reminders, settings)
	const hasLeftLayoutInset = $derived(chrome.layout.leftWidthClass !== null)

	const sidebarSpacerWidthClass = $derived.by(() => {
		if (!isChatSwipeEligibleRoute) return 'w-0'
		if (device.isMobile) return 'w-0'
		return sidebar.isChatSidebarOpen ? 'w-72' : 'w-18'
	})

	function maybeCloseDockFromMobileShellClick(event: MouseEvent) {
		if (!device.isMobile) return
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
		if (!device.isMobile) return
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
		// prevent the gesture from being consumed as a scroll.
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
		// mobile dock dismiss gesture: left-to-right
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
		if (!device.isMobile) return
		if (!isChatSwipeEligibleRoute) return
		if (chrome.isDockOpen) return
		if (sidebar.isChatSidebarOpen) return
		// only start from the left edge to avoid interfering with normal interactions
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
		// keep the gesture from being consumed as a scroll when we intend a horizontal swipe.
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
		// mobile sidebar reveal gesture: left-to-right
		if (dx > 0) sidebar.openChatSidebar()
	}

	function onMainPointerCancel(event: PointerEvent) {
		if (sidebarSwipePointerId !== event.pointerId) return
		sidebarSwipeActive = false
		sidebarSwipePointerId = null
	}
</script>

<svelte:head>
	<title>{pageTitleStore.pageFullTitle}</title>
	{#if settingsState.data?.branding?.pwa_manifest_url}
		<link rel="manifest" href={settingsState.data.branding.pwa_manifest_url} />
	{/if}
</svelte:head>

<SplashController />

<!-- BackgroundManager handles all backgrounds with smooth transitions -->
<BackgroundManager
	type={currentBackground}
	config={{ color: '#0a0a0a' }}
	onReady={handleBackgroundReady}
>
	{#if pendingApproval}
		<PendingApproval
			supportEmail={settingsState.data?.branding?.support_email ?? null}
			adminEmail={settingsState.data?.branding?.admin_email ?? null}
		/>
	{:else if isAuthRoute}
		<div class="relative z-1 flex h-screen">
			<div class="relative flex min-w-0 flex-1 flex-col">
				{@render children()}
			</div>
		</div>
	{:else}
		<div class="relative z-1 flex h-screen">
			{#if isChatSwipeEligibleRoute}
				<!-- sidebar (fixed; desktop reserves a rail, mobile uses overlay) -->
				<ChatSidebar />
				<div
					class="h-screen shrink-0 transition-[width] duration-300 ease-in-out {sidebarSpacerWidthClass}"
				></div>
			{/if}

			{#if hasLeftLayoutInset && !device.isMobile && chrome.layout.leftWidthClass}
				<!-- generic left layout inset spacer (master/detail scaffolds render the actual sidebar) -->
				<div class="h-screen shrink-0 {chrome.layout.leftWidthClass}"></div>
			{/if}

			<!-- main content -->
			<div
				class="main-content-shell relative flex min-w-0 flex-1 flex-col overflow-y-auto pt-[calc(var(--chrome-island-offset,0px)+16px)]"
				role="main"
				style="touch-action: pan-y;"
				bind:this={mainContentShell}
				onpointerdown={onMainPointerDown}
				onpointermove={onMainPointerMove}
				onpointerup={onMainPointerUp}
				onpointercancel={onMainPointerCancel}
			>
				{@render children()}
			</div>

			<!-- system chrome: Island (top header) - fixed overlay for blur effect -->
			<div
				class="pointer-events-none fixed top-0 z-30 mx-auto w-full pt-3 sm:pt-6 lg:pt-8"
				style="left: var(--island-left, 0); right: 0; max-width: min(1280px, calc(100% - var(--island-left, 0px))); padding-left: var(--spacing-page-x); padding-right: var(--spacing-page-x);"
				bind:this={islandShell}
			>
				<div class="pointer-events-auto mx-auto max-w-7xl">
					<Island />
				</div>
			</div>

			<!-- system chrome: Dock (right sidebar overlay) -->
			{#if chrome.isDockOpen && !device.isMobile}
				<div
					class="fixed inset-0 z-20"
					role="presentation"
					aria-hidden="true"
					onclick={() => chrome.closeDock()}
				></div>
			{/if}
			<div
				class="dock-shell fixed top-0 right-0 bottom-0 z-30 w-[min(31rem,calc(100vw-3rem))] {chrome.isDockOpen
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
					class="dock-content h-full w-full px-6 pt-8 pb-8 backdrop-blur-[14px] transition-transform duration-300 ease-in-out {chrome.isDockOpen
						? 'translate-x-0'
						: 'translate-x-full'}"
					style="background-color: var(--accent-bg);"
				>
					<Dock />
				</div>
			</div>

			<ArchivedChatsModal open={modals.isOpen('archived-chats')} onClose={modals.close} />
			<ShareResourceModal
				open={modals.isOpen('share-resource')}
				payload={modals.shareResourcePayload}
				onClose={modals.close}
			/>
		</div>
	{/if}

	<!-- notification toasts (global, above all content) -->
	{#if !chrome.isDockOpen}
		<NotificationToast
			toasts={notifications.toasts}
			onDismiss={(id: string) => notifications.dismissToast(id)}
			onSwipeDismiss={(id: string) => {
				const toast = notifications.toasts.find((t) => t.id === id)
				if (toast) {
					const match = notifications.list.find((n) => {
						const data = n.event?.data as Record<string, unknown> | undefined
						return !n.dismissed && data?.title === toast.title
					})
					if (match) void notifications.delete(match.id)
				}
				notifications.dismissToast(id)
			}}
			onClick={(id: string) => {
				notifications.dismissToast(id)
				chrome.openDock()
			}}
		/>
	{/if}
</BackgroundManager>

<style>
	@media (max-width: 888px) {
		.dock-shell {
			left: 0;
			width: 100%;
		}

		.dock-content {
			padding-left: 1rem;
			padding-right: 1rem;
		}
	}
</style>
