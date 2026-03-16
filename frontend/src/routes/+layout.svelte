<script lang="ts">
	import { goto, onNavigate } from '$app/navigation'
	import { resolve } from '$app/paths'
	import { page } from '$app/state'
	import { markAuthReady } from '$lib/auth/session.svelte'
	import BackgroundManager, {
		type BackgroundConfig,
	} from '$lib/components/backgrounds/BackgroundManager.svelte'
	import ChatSidebar from '$lib/components/chat/sidebar/ChatSidebar.svelte'
	import AddFriendsModal from '$lib/components/modals/AddFriendsModal.svelte'
	import ArchivedChatsModal from '$lib/components/modals/ArchivedChatsModal.svelte'
	import ConfirmDeleteModal from '$lib/components/modals/ConfirmDeleteModal.svelte'
	import CreateGroupModal from '$lib/components/modals/CreateGroupModal.svelte'
	import FileDetailsModal from '$lib/components/modals/FileDetailsModal.svelte'
	import MemoriesModal from '$lib/components/modals/MemoriesModal.svelte'
	import ResourceAccessModal from '$lib/components/modals/ResourceAccessModal.svelte'
	import ShareResourceModal from '$lib/components/modals/ShareResourceModal.svelte'
	import SplashController from '$lib/components/SplashController.svelte'
	import BackendReconnect from '$lib/components/system/BackendReconnect.svelte'
	import Dock from '$lib/components/system/Dock.svelte'
	import Island from '$lib/components/system/Island.svelte'
	import NotificationToast from '$lib/components/system/NotificationToast.svelte'
	import PendingApproval from '$lib/components/system/PendingApproval.svelte'
	import { getMediaUrls } from '$lib/config/media'
	import { createDebugUiContext } from '$lib/contexts/debugUiContext.svelte'
	import { createSidebarContext, useSidebar } from '$lib/contexts/sidebarContext.svelte'
	import { createSystemChromeContext } from '$lib/contexts/systemChromeContext.svelte'
	import { createThemeContext, setThemeContext } from '$lib/contexts/themeContext.svelte'
	import { initApp } from '$lib/init'
	import { appReadiness } from '$lib/stores/appReadiness.svelte'
	import { background } from '$lib/stores/background.svelte'
	import { device } from '$lib/stores/device.svelte'
	import { modals } from '$lib/stores/modals.svelte'
	import { notifications } from '$lib/stores/notifications.svelte'
	import { pageTitleStore } from '$lib/stores/pageTitle.svelte'
	import { permissions } from '$lib/stores/permissions.svelte'
	import { settingsState } from '$lib/stores/settings.svelte'
	import '$lib/styles/liquid-glass.css'
	import { onDestroy, onMount, tick } from 'svelte'
	import '../app.css'

	const PUBLIC_PATHS = new Set(['/login', '/signup'])

	const DEFAULT_BACKGROUND_CONFIG: BackgroundConfig = {
		clouds2TexturePath: '/backgrounds/noise.png',
	}

	type ViewTransitionCapableDocument = Document & {
		startViewTransition?: (
			cb: () => Promise<void> | void
		) => { finished?: Promise<unknown> } | void
	}

	// global View Transitions hook.
	// this ensures transitions run for ALL navigations (links, goto(), back/forward popstate).
	// we intentionally skip same-path navigations (e.g. / <-> /?chat=new) so in-page
	// animations keep controls interactive without the ViewTransition overlay.
	/** home or chat page - transitions between these keep the sidebar filter */
	function isChatOrHome(pathname: string): boolean {
		return pathname === '/' || pathname.startsWith('/c/')
	}

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

			// keep sidebar backdrop-filter when both sides are home/chat pages
			const bothChatOrHome = isChatOrHome(from.pathname) && isChatOrHome(to.pathname)
			if (bothChatOrHome) {
				root.dataset.vtKeepFilter = '1'
			}

			const transition = start.call(document, async () => {
				resolve()
				await navigation.complete
			})

			const done = () => {
				delete root.dataset.vtActive
				delete root.dataset.vtKeepFilter
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

	// access gate state
	let pendingApproval = $state<boolean>(false)
	let backendUnreachable = $state<boolean>(false)

	// reactive media asset URLs from settings
	const mediaUrls = $derived(getMediaUrls())
	let { children } = $props()

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
			// align the island shell left edge with the main content area
			islandEl.style.setProperty('--island-left', `${mainRect.left}px`)
			// also expose on :root so portal'd elements (AddContext) can read it
			document.documentElement.style.setProperty('--island-left', `${mainRect.left}px`)
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
		const { authenticated, token, backendUnreachable: unreachable } = await initApp()

		if (unreachable) {
			backendUnreachable = true
			return
		}

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
			// access gate
			await permissions.load()
			if (permissions.list !== null && !permissions.hasPermission('frontend:access')) {
				pendingApproval = true
			}
		}
	})

	const isAuthRoute = $derived.by(() => {
		const path = page.url.pathname
		return path === '/login' || path === '/signup'
	})

	// auth pages (and backend-unreachable screen) use the admin-configured auth background
	$effect(() => {
		if (isAuthRoute || backendUnreachable) {
			background.setPage(background.auth)
		} else {
			background.clearPage()
		}
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
	{#if mediaUrls.manifest}
		<link rel="manifest" href={mediaUrls.manifest} />
	{/if}
	{#if mediaUrls.favicon}
		<link rel="icon" href={mediaUrls.favicon} />
	{/if}
	{#if mediaUrls.appleTouchIcon}
		<link rel="apple-touch-icon" href={mediaUrls.appleTouchIcon} />
	{/if}
	<meta
		name="apple-mobile-web-app-title"
		content={settingsState.data?.branding?.site_name ?? 'nokodo'}
	/>
</svelte:head>

<SplashController />

<!-- BackgroundManager handles all backgrounds with smooth transitions -->
<BackgroundManager
	type={background.resolved}
	config={{
		...DEFAULT_BACKGROUND_CONFIG,
		...(background.pageConfig || {}),
		color: background.resolvedStaticColor,
	}}
	onReady={handleBackgroundReady}
>
	{#if backendUnreachable}
		<BackendReconnect />
	{:else if pendingApproval}
		<PendingApproval
			supportEmail={settingsState.data?.branding?.support_email ?? null}
			adminEmail={settingsState.data?.branding?.admin_email ?? null}
		/>
	{:else if isAuthRoute}
		<div class="h-app relative z-1 flex">
			<div
				class="relative flex min-w-0 flex-1 flex-col overflow-y-auto"
				style="touch-action: pan-y; overscroll-behavior-y: contain;"
			>
				{@render children()}
			</div>
		</div>
	{:else}
		<div class="h-app relative z-1 flex">
			{#if isChatSwipeEligibleRoute}
				<!-- sidebar (fixed; desktop reserves a rail, mobile uses overlay) -->
				<ChatSidebar />
				<div
					class="h-full shrink-0 transition-[width] duration-300 ease-in-out {sidebarSpacerWidthClass}"
				></div>
			{/if}

			{#if hasLeftLayoutInset && !device.isMobile && chrome.layout.leftWidthClass}
				<!-- generic left layout inset spacer (master/detail scaffolds render the actual sidebar) -->
				<div class="h-full shrink-0 {chrome.layout.leftWidthClass}"></div>
			{/if}

			<!-- main content -->
			<div
				class="main-content-shell no-scrollbar relative flex min-h-0 min-w-0 flex-1 flex-col overflow-y-auto pt-[calc(var(--chrome-island-offset,0px)+16px)]"
				role="main"
				style="touch-action: pan-y; overscroll-behavior-y: contain;"
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

			<AddFriendsModal open={modals.isOpen('add-friends')} onClose={modals.close} />
			<ArchivedChatsModal open={modals.isOpen('archived-chats')} onClose={modals.close} />
			<ConfirmDeleteModal
				open={modals.isOpen('confirm-delete')}
				payload={modals.confirmDeletePayload}
				onClose={modals.close}
			/>
			<CreateGroupModal open={modals.isOpen('create-group')} onClose={modals.close} />
			<FileDetailsModal
				open={modals.isOpen('file-details')}
				payload={modals.fileDetailsPayload}
				onClose={modals.close}
			/>
			<MemoriesModal open={modals.isOpen('memories')} onClose={modals.close} />
			<ResourceAccessModal
				open={modals.isOpen('resource-access')}
				payload={modals.resourceAccessPayload}
				onClose={modals.close}
			/>
			<ShareResourceModal
				open={modals.isOpen('share-resource')}
				payload={modals.shareResourcePayload}
				onClose={modals.close}
			/>
		</div>
	{/if}

	<!-- toasts (global, above all content) -->
	<NotificationToast
		toasts={chrome.isDockOpen
			? notifications.toasts.filter((t) => t.type === 'ephemeral')
			: notifications.toasts}
		onDismiss={(id: string) => notifications.dismissToast(id)}
		onSwipeDismiss={(id: string) => {
			const toast = notifications.toasts.find((t) => t.id === id)
			if (toast && toast.type === 'notification') {
				const match = notifications.list.find(
					(n) => !n.dismissed && n.event_id === toast.eventId
				)
				if (match) void notifications.delete(match.id)
			}
			notifications.dismissToast(id)
		}}
		onClick={(id: string) => {
			const toast = notifications.toasts.find((t) => t.id === id)
			notifications.dismissToast(id)
			if (toast?.type === 'notification') chrome.openDock()
		}}
	/>
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
