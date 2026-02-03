<script lang="ts">
	import { browser } from '$app/environment'
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import { page } from '$app/state'
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

<header
	class="liquid-glass max-h-22 overflow-visible rounded-full px-[clamp(10px,4vw,28px)] py-5 shadow-[0_32px_64px_rgba(12,10,30,0.45)]"
	style="view-transition-name: island;"
>
	<div
		class="relative z-10 grid min-w-0 grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-0 sm:gap-[clamp(6px,2.5vw,16px)]"
	>
		<!-- left: context actions (page-injected via chrome.setContextActions) -->
		<div class="flex min-w-0 items-center gap-0 sm:gap-[clamp(6px,2.2vw,12px)]">
			{#if chrome.island.contextActions}
				<!-- default accent color for all context actions; pages can override with inline styles -->
				<div class="flex items-center gap-1" style="color: var(--accent-primary, white);">
					{@render chrome.island.contextActions()}
				</div>
			{/if}
		</div>

		<!-- center: pulse area -->
		<div class="flex min-w-0 items-center justify-center">
			{#if chrome.island.pulse}
				<div class="max-w-160 truncate text-sm text-white/70">
					{chrome.island.pulse}
				</div>
			{/if}
		</div>

		<!-- right: stable controls + user -->
		<div class="flex items-center justify-end gap-0 sm:gap-2">
			{#if !isHomeLayout}
				<button
					class="flex h-12 w-auto min-w-8 cursor-pointer items-center justify-center px-1 text-white/80 transition-transform duration-300 hover:scale-[1.05] hover:text-white active:scale-[0.97] md:w-12 md:px-0"
					onclick={handleHome}
					aria-label="home"
				>
					<Home variant="solid" class="h-6 w-6" />
				</button>
			{/if}

			<button
				class="flex h-12 w-auto min-w-8 cursor-pointer items-center justify-center px-1 text-white/80 transition-transform duration-300 hover:scale-[1.05] hover:text-white active:scale-[0.97] md:w-12 md:px-0"
				onclick={() => chrome.toggleDock()}
				aria-label={chrome.isDockOpen ? 'close dock' : 'open dock'}
				aria-expanded={chrome.isDockOpen}
			>
				<Sidebar variant="solid" class="h-6 w-6 rotate-180" />
			</button>

			<UserProfileTrigger user={session.userDisplay} placement="header" isExpanded={false} />
		</div>
	</div>
</header>
