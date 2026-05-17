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
	const isSearchMode = $derived(browser ? page.url.searchParams.has('search') : false)

	function handleHome() {
		sidebar?.selectChat?.(null)
		const isAlreadyHome = page.url.pathname === '/' && chatParam === null && !isSearchMode
		if (isAlreadyHome) {
			window.dispatchEvent(new CustomEvent('focus:chat-input'))
			return
		}
		void goto(resolve('/'), { keepFocus: true, noScroll: true })
	}

	const isHomeLayout = $derived(page.url.pathname === '/' && chatParam === null && !isSearchMode)

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
	class="overflow-visible rounded-full px-3 py-3 shadow-[0_32px_64px_rgba(12,10,30,0.45)]"
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
					class="island-context-actions flex h-full items-center"
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
				<div class="text-foreground/70 max-w-160 truncate text-sm">
					{chrome.island.pulse}
				</div>
			{/if}
		</div>

		<!-- right: stable controls + PWA actions + user -->
		<div class="island-right-controls flex h-full items-center justify-end gap-0">
			<!-- PWA: update button (supersedes install) -->
			{#if showUpdate}
				<button
					class="island-pwa-btn flex cursor-pointer items-center justify-center text-amber-400/90 transition-transform duration-300 hover:scale-[1.05] hover:text-amber-300 active:scale-[0.97] disabled:cursor-default disabled:opacity-70 disabled:hover:scale-100"
					onclick={() => void applyUpdate()}
					disabled={swUpdate.applyingUpdate}
					aria-busy={swUpdate.applyingUpdate}
					aria-label="update available"
				>
					<ArrowUpCircle class="island-pwa-icon" strokeWidth="2" />
					<span
						class="island-pwa-label text-xs font-medium transition-all duration-300 {labelVisible
							? 'max-w-20 pr-2.5 pl-1 opacity-100'
							: 'max-w-0 opacity-0'}"
					>
						update
					</span>
				</button>
			{/if}

			<!-- PWA: install button -->
			{#if showInstall}
				<button
					class="island-pwa-btn text-foreground/80 hover:text-foreground flex cursor-pointer items-center justify-center transition-transform duration-300 hover:scale-[1.05] active:scale-[0.97]"
					onclick={promptInstall}
					aria-label="install app"
				>
					<Download class="island-pwa-icon" strokeWidth="2" />
					<span
						class="island-pwa-label text-xs font-medium transition-all duration-300 {labelVisible
							? 'max-w-20 pr-2.5 pl-1 opacity-100'
							: 'max-w-0 opacity-0'}"
					>
						install
					</span>
				</button>
			{/if}

			{#if !isHomeLayout}
				<button
					class="text-foreground/80 hover:text-foreground flex cursor-pointer items-center justify-center transition-transform duration-300 hover:scale-[1.05] active:scale-[0.97]"
					onclick={handleHome}
					aria-label="home"
				>
					<Home variant="solid" />
				</button>
			{/if}

			<button
				class="text-foreground/80 hover:text-foreground flex cursor-pointer items-center justify-center transition-transform duration-300 hover:scale-[1.05] active:scale-[0.97]"
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
	/* direct island controls only; composite controls keep their own inner layout */
	:global(.island-context-actions) {
		gap: 0;
	}
	:global(.island-context-actions > *) {
		height: 100%;
	}

	:global(.island-context-actions > button),
	:global(.island-right-controls > button) {
		display: inline-flex;
		height: 100%;
		min-width: 0;
		align-items: center;
		justify-content: center;
		padding: 0;
		line-height: 1;
	}

	:global(.island-pwa-btn) {
		display: inline-flex;
		height: 100%;
		min-width: 0;
		align-items: center;
		justify-content: center;
		padding: 0;
		line-height: 1;
	}

	:global(.island-context-actions > button > svg),
	:global(.island-right-controls > button > svg) {
		height: 60%;
		width: auto;
	}

	:global(.island-pwa-icon) {
		height: 60%;
		width: auto;
		flex: 0 0 auto;
	}

	/* label collapse: overflow hidden + whitespace nowrap for smooth max-width animation */
	:global(.island-pwa-label) {
		overflow: hidden;
		white-space: nowrap;
	}
</style>
