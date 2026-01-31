<script lang="ts">
	import { browser } from '$app/environment'
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import { page } from '$app/state'
	import ChevronLeft from '$lib/components/icons/ChevronLeft.svelte'
	import HomeSolid from '$lib/components/icons/HomeSolid.svelte'
	import ListBullet from '$lib/components/icons/ListBullet.svelte'
	import Plus from '$lib/components/icons/Plus.svelte'
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

	function requestHomeInputFocus() {
		if (!browser) return
		window.dispatchEvent(new CustomEvent('nokodo:focus-home-input'))
	}

	function handleHome() {
		sidebar?.selectChat?.(null)
		const isAlreadyHome = page.url.pathname === '/' && chatParam === null
		if (isAlreadyHome) {
			requestHomeInputFocus()
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
		class="relative z-10 grid grid-cols-[1fr_auto_1fr] items-center gap-0 sm:gap-[clamp(6px,2.5vw,16px)]"
	>
		<!-- left: context actions (actions + page-injected contextActions) -->
		<div class="flex min-w-0 items-center gap-0 sm:gap-[clamp(6px,2.2vw,12px)]">
			{#if chrome.island.actions && chrome.island.actions.length > 0}
				<div class="flex items-center gap-1 sm:gap-2">
					{#each chrome.island.actions as action (action.id)}
						<button
							class="group flex h-12 w-auto min-w-8 cursor-pointer items-center justify-center gap-2 rounded-2xl border-none bg-transparent px-2 text-white/80 transition-transform duration-150 hover:scale-[1.05] hover:text-white active:scale-[0.97] sm:px-3"
							onclick={action.onClick}
							aria-label={action.ariaLabel ?? action.label}
							type="button"
						>
							{#if action.icon === 'plus'}
								<Plus className="h-5 w-5" />
							{:else if action.icon === 'list'}
								<ListBullet className="h-5 w-5" />
							{:else if action.icon === 'chevron-left'}
								<ChevronLeft className="h-5 w-5" strokeWidth="2" />
							{/if}
							{#if action.label}
								<span class="hidden text-sm font-medium text-white/85 sm:inline">
									{action.label}
								</span>
							{/if}
						</button>
					{/each}
				</div>
			{/if}

			{#if chrome.island.contextActions}
				{@render chrome.island.contextActions()}
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
					<HomeSolid className="h-6 w-6" />
				</button>
			{/if}

			<button
				class="flex h-12 w-auto min-w-8 cursor-pointer items-center justify-center px-1 text-white/80 transition-transform duration-300 hover:scale-[1.05] hover:text-white active:scale-[0.97] md:w-12 md:px-0"
				onclick={() => chrome.toggleDock()}
				aria-label={chrome.isDockOpen ? 'close dock' : 'open dock'}
				aria-expanded={chrome.isDockOpen}
			>
				<Sidebar className="h-6 w-6 rotate-180" />
			</button>

			<UserProfileTrigger user={session.userDisplay} placement="header" isExpanded={false} />
		</div>
	</div>
</header>
