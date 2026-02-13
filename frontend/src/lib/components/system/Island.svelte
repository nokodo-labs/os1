<script lang="ts">
	import { browser } from '$app/environment'
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import { page } from '$app/state'
	import LiquidGlass from '$lib/components/effects/LiquidGlass.svelte'
	import Home from '$lib/components/icons/Home.svelte'
	import Sidebar from '$lib/components/icons/Sidebar.svelte'
	import UserProfileTrigger from '$lib/components/system/UserProfileTrigger.svelte'
	import { useSidebar } from '$lib/contexts/sidebarContext.svelte'
	import { useSystemChrome } from '$lib/contexts/systemChromeContext.svelte'
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
</script>

<LiquidGlass
	tag="header"
	class="overflow-visible rounded-full px-[clamp(5px,2vw,14px)] py-3 shadow-[0_32px_64px_rgba(12,10,30,0.45)]"
	style="view-transition-name: island;"
>
	<div
		class="relative z-10 grid min-w-0 grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center"
		style="height: var(--chrome-island-height);"
	>
		<!-- left: context actions (page-injected via chrome.setContextActions) -->
		<div class="flex h-full items-center">
			{#if chrome.island.contextActions}
				<!-- default accent color for all context actions; pages can override with inline styles -->
				<div
					class="island-context-actions flex h-full items-center gap-1"
					style="color: var(--accent-primary, white);"
				>
					{@render chrome.island.contextActions()}
				</div>
			{/if}
		</div>

		<!-- center: pulse area -->
		<div class="flex h-full min-w-0 items-center justify-center">
			{#if chrome.island.pulse}
				<div class="max-w-160 truncate text-sm text-white/70">
					{chrome.island.pulse}
				</div>
			{/if}
		</div>

		<!-- right: stable controls + user -->
		<div class="island-right-controls flex h-full items-center justify-end">
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

	/* only target direct button children of right controls, not nested menus */
	:global(.island-right-controls > button) {
		height: 100%;
	}
	:global(.island-right-controls > button > svg) {
		height: 60%;
		width: auto;
	}
</style>
