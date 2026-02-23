<script lang="ts">
	import { browser } from '$app/environment'
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import { page } from '$app/state'
	import LiquidGlass from '$lib/components/effects/LiquidGlass.svelte'
	import ArrowUpCircle from '$lib/components/icons/ArrowUpCircle.svelte'
	import Download from '$lib/components/icons/Download.svelte'
	import Home from '$lib/components/icons/Home.svelte'
	import Sidebar from '$lib/components/icons/Sidebar.svelte'
	import WifiSlash from '$lib/components/icons/WifiSlash.svelte'
	import UserProfileTrigger from '$lib/components/system/UserProfileTrigger.svelte'
	import { useSidebar } from '$lib/contexts/sidebarContext.svelte'
	import { useSystemChrome } from '$lib/contexts/systemChromeContext.svelte'
	import { installPrompt, promptInstall } from '$lib/stores/installPrompt.svelte'
	import { network } from '$lib/stores/network.svelte'
	import { applyUpdate, swUpdate } from '$lib/stores/serviceWorker.svelte'
	import { session } from '$lib/stores/session.svelte'

	type SidebarContext = {
		selectChat?: (id: string | null) => void
	}

	const chrome = useSystemChrome()
	const sidebar = useSidebar() as SidebarContext | null

	$effect(() => {
		if (!browser) return
		void session.refresh()
	})

	const chatParam = $derived(browser ? page.url.searchParams.get('chat') : null)

	function handleHome() {
		sidebar?.selectChat?.(null)
		const isAlreadyHome = page.url.pathname === '/' && chatParam === null
		if (isAlreadyHome) {
			window.dispatchEvent(new CustomEvent('focus:chat-input'))
			return
		}
		void goto(resolve('/'), { keepFocus: true, noScroll: true })
	}

	const isHomeLayout = $derived(page.url.pathname === '/' && chatParam === null)

	// PWA state
	const isOffline = $derived(!network.online)
	const hasUpdate = $derived(swUpdate.updateAvailable)
	const canInstall = $derived(!installPrompt.isInstalled && installPrompt.canInstall)

	// update supersedes install; offline hides both
	const showUpdate = $derived(!isOffline && hasUpdate)
	const showInstall = $derived(!isOffline && !hasUpdate && canInstall)

	// label show/hide timing
	// labels appear on homepage navigation, then auto-hide after a few seconds.
	// they reappear every time the user navigates to homepage.
	const LABEL_VISIBLE_MS = 4000

	let labelVisible = $state(false)
	let labelTimer: ReturnType<typeof setTimeout> | null = null

	function showLabelBriefly() {
		if (labelTimer) clearTimeout(labelTimer)
		labelVisible = true
		labelTimer = setTimeout(() => {
			labelVisible = false
			labelTimer = null
		}, LABEL_VISIBLE_MS)
	}

	$effect(() => {
		if (!browser) return
		if (isHomeLayout && (showUpdate || showInstall)) {
			showLabelBriefly()
		}
	})

	// also flash labels when update/install first become available
	$effect(() => {
		if (!browser) return
		if (showUpdate || showInstall) {
			showLabelBriefly()
		}
	})
</script>

<LiquidGlass
	component="island"
	tag="header"
	class="overflow-visible rounded-full px-[clamp(5px,2vw,14px)] py-3 shadow-[0_32px_64px_rgba(12,10,30,0.45)]"
	style="view-transition-name: island;"
	blurRadius={4}
>
	<div
		class="relative z-10 grid min-w-0 grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center"
		style="height: var(--chrome-island-height);"
	>
		<!-- left: context actions (page-injected via chrome.setContextActions) -->
		<div class="flex h-full items-center">
			{#if chrome.island.contextActions}
				<div
					class="island-context-actions flex h-full items-center gap-1"
					style="color: var(--accent-primary, white);"
				>
					{@render chrome.island.contextActions()}
				</div>
			{/if}
		</div>

		<!-- center: pulse area / offline indicator -->
		<div class="flex h-full min-w-0 items-center justify-center">
			{#if isOffline}
				<div
					class="flex items-center gap-1.5 text-amber-400/90"
					role="status"
					aria-live="polite"
				>
					<WifiSlash class="size-3.5" strokeWidth="2.5" />
					<span class="text-xs font-medium">offline</span>
				</div>
			{:else if chrome.island.pulse}
				<div class="max-w-160 truncate text-sm text-white/70">
					{chrome.island.pulse}
				</div>
			{/if}
		</div>

		<!-- right: stable controls + PWA actions + user -->
		<div class="island-right-controls flex h-full items-center justify-end">
			<!-- PWA: update button (supersedes install) -->
			{#if showUpdate}
				<button
					class="island-pwa-btn flex cursor-pointer items-center justify-center gap-1.5 text-amber-400/90 transition-transform duration-300 hover:scale-[1.05] hover:text-amber-300 active:scale-[0.97]"
					onclick={applyUpdate}
					aria-label="update available"
				>
					<ArrowUpCircle strokeWidth="2" />
					<span
						class="island-pwa-label text-xs font-medium transition-all duration-300 {labelVisible
							? 'max-w-20 opacity-100'
							: 'max-w-0 opacity-0'}"
					>
						update
					</span>
				</button>
			{/if}

			<!-- PWA: install button -->
			{#if showInstall}
				<button
					class="island-pwa-btn flex cursor-pointer items-center justify-center gap-1.5 text-white/80 transition-transform duration-300 hover:scale-[1.05] hover:text-white active:scale-[0.97]"
					onclick={promptInstall}
					aria-label="install app"
				>
					<Download strokeWidth="2" />
					<span
						class="island-pwa-label text-xs font-medium transition-all duration-300 {labelVisible
							? 'max-w-20 opacity-100'
							: 'max-w-0 opacity-0'}"
					>
						install
					</span>
				</button>
			{/if}

			{#if !isHomeLayout}
				<button
					class="flex cursor-pointer items-center justify-center text-white/80 transition-transform duration-300 hover:scale-[1.05] hover:text-white active:scale-[0.97]"
					onclick={handleHome}
					aria-label="home"
				>
					<Home variant="solid" />
				</button>
			{/if}

			<button
				class="flex cursor-pointer items-center justify-center text-white/80 transition-transform duration-300 hover:scale-[1.05] hover:text-white active:scale-[0.97]"
				onclick={() => chrome.toggleDock()}
				aria-label={chrome.isDockOpen ? 'close dock' : 'open dock'}
				aria-expanded={chrome.isDockOpen}
			>
				<Sidebar variant="solid" class="rotate-180" />
			</button>

			<UserProfileTrigger user={session.userDisplay} placement="header" isExpanded={false} />
		</div>
	</div>
</LiquidGlass>

<style>
	/* only target direct children of context actions, not nested dropdown menus */
	:global(.island-context-actions > *) {
		height: 100%;
	}
	:global(.island-context-actions > * > svg),
	:global(.island-context-actions > button > svg) {
		height: 60%;
		width: auto;
	}
	/* handle trigger buttons nested inside wrapper elements (e.g. dropdown containers) */
	:global(.island-context-actions > div > button) {
		height: 100%;
	}
	:global(.island-context-actions > div > button > svg) {
		height: 60%;
		width: auto;
	}

	/* only target direct button children of right controls, not nested menus */
	:global(.island-right-controls > button) {
		height: 100%;
	}
	:global(.island-right-controls > button > svg) {
		height: 60%;
		width: auto;
	}

	/* PWA buttons: icon sizing matches other island buttons */
	:global(.island-pwa-btn) {
		height: 100%;
	}
	:global(.island-pwa-btn > svg) {
		height: 60%;
		width: auto;
	}

	/* label collapse: overflow hidden + whitespace nowrap for smooth max-width animation */
	:global(.island-pwa-label) {
		overflow: hidden;
		white-space: nowrap;
	}
</style>
