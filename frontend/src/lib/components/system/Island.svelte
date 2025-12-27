<script lang="ts">
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import { page } from '$app/state'
	import AppNotification from '$lib/components/icons/AppNotification.svelte'
	import ChatBubbleDotted from '$lib/components/icons/ChatBubbleDotted.svelte'
	import ChevronDown from '$lib/components/icons/ChevronDown.svelte'
	import Home from '$lib/components/icons/Home.svelte'
	import Sidebar from '$lib/components/icons/Sidebar.svelte'
	import UserProfileTrigger from '$lib/components/sidebar/UserProfileTrigger.svelte'
	import { useSidebar } from '$lib/contexts/sidebarContext.svelte'
	import { useSystemChrome } from '$lib/contexts/systemChromeContext.svelte'
	import { activeThread, refreshSession, userDisplay } from '$lib/stores/session'
	import ChatBubbleDottedChecked from '../icons/ChatBubbleDottedChecked.svelte'

	interface Agent {
		id: string
		name: string
		description?: string
	}

	type SidebarContext = {
		selectChat?: (id: string | null) => void
		toggleChatSidebar?: () => void
		openChatSidebar?: () => void
		closeChatSidebar?: () => void
		isChatSidebarOpen?: boolean
	}

	const chrome = useSystemChrome()
	const sidebar = useSidebar() as SidebarContext | null

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

	$effect(() => {
		void refreshSession()
	})

	// Mock agent data (until backend-driven)
	const agents: Agent[] = [
		{ id: 'gpt-4', name: 'GPT-4', description: 'most capable model' },
		{ id: 'gpt-4-turbo', name: 'GPT-4 Turbo', description: 'faster, optimized' },
		{ id: 'claude-3-opus', name: 'Claude 3 Opus', description: "anthropic's flagship" },
		{ id: 'claude-3-sonnet', name: 'Claude 3 Sonnet', description: 'balanced performance' },
		{ id: 'gemini-pro', name: 'Gemini Pro', description: "google's advanced model" },
		{ id: 'llama-3', name: 'Llama 3', description: 'open source powerhouse' },
	]

	let isAgentDropdownOpen = $state(false)

	let currentAgent = $derived(
		agents.find((a) => a.id === chrome.island.agentSelector?.selectedAgent) || agents[0]
	)

	function handleClickOutside(event: MouseEvent) {
		const target = event.target as HTMLElement
		if (!target.closest('.agent-selector')) {
			isAgentDropdownOpen = false
		}
	}

	function toggleAgentDropdown() {
		isAgentDropdownOpen = !isAgentDropdownOpen
	}

	function selectAgent(agentId: string) {
		isAgentDropdownOpen = false
		chrome.island.agentSelector?.onAgentChange(agentId)
	}

	function navigateWithTransition(target: string) {
		const targetUrl = new URL(target, page.url)
		const isSamePath = targetUrl.pathname === page.url.pathname
		const isSameSearch = targetUrl.search === page.url.search
		if (isSamePath && isSameSearch) return

		if (isSamePath) {
			// Within the same route (e.g. / <-> /?chat=temp), avoid the ViewTransition
			// overlay so controls stay interactive during the CSS transition.
			// @ts-expect-error resolve typing is narrower than our constructed URL
			void goto(resolve(target as never), { keepFocus: true, noScroll: true })
			return
		}

		const start = (
			document as unknown as {
				startViewTransition?: (cb: () => Promise<void> | void) => void
			}
		).startViewTransition

		const go = async () => {
			// @ts-expect-error resolve typing is narrower than our constructed URL
			await goto(resolve(target as never), { keepFocus: true, noScroll: true })
		}

		if (start) {
			start.call(document, go)
			return
		}

		void go()
	}

	function handleHome() {
		sidebar?.selectChat?.(null)
		navigateWithTransition('/')
	}

	function handleTemporaryChat() {
		sidebar?.selectChat?.(null)
		navigateWithTransition('/?chat=temp')
	}

	const isTemporaryChatActive = $derived(
		page.url.searchParams.get('chat') === 'temp' || ($activeThread?.is_temporary ?? false)
	)
	const isHomeLayout = $derived(
		page.url.pathname === '/' && page.url.searchParams.get('chat') === null
	)

	function handleTemporaryChatToggle() {
		if (isTemporaryChatActive) {
			handleHome()
			return
		}
		handleTemporaryChat()
	}

	$effect(() => {
		if (!chrome.island.agentSelector) {
			isAgentDropdownOpen = false
		}
	})

	$effect(() => {
		if (isAgentDropdownOpen) {
			document.addEventListener('click', handleClickOutside)
			return () => document.removeEventListener('click', handleClickOutside)
		}
	})
</script>

<div style="view-transition-name: chat-header;">
	<header
		class="liquid-glass mt-5 mb-0 max-h-[88px] overflow-hidden rounded-full px-[clamp(10px,4vw,28px)] py-5 shadow-[0_32px_64px_rgba(12,10,30,0.45)]"
	>
		<span class="liquid-glass__highlight" aria-hidden="true"></span>

		<div
			class="liquid-glass__content grid grid-cols-[1fr_auto_1fr] items-center gap-[clamp(6px,2.5vw,16px)]"
		>
			<!-- left: adaptive controls -->
			<div class="flex min-w-0 items-center gap-[clamp(6px,2.2vw,12px)]">
				{#if chrome.island.agentSelector}
					<div class="agent-selector relative flex min-w-0 items-center gap-2">
						<button
							class="flex min-w-0 cursor-pointer items-center gap-2 rounded-2xl border-none bg-transparent px-[clamp(8px,2.5vw,16px)] py-2 transition-all duration-200 hover:bg-white/5 active:scale-[0.98]"
							onclick={toggleAgentDropdown}
							aria-expanded={isAgentDropdownOpen}
							aria-haspopup="listbox"
						>
							<span
								class="min-w-0 truncate bg-clip-text text-xl font-semibold whitespace-nowrap text-transparent [-webkit-background-clip:text] [-webkit-text-fill-color:transparent]"
								style="background-image: linear-gradient(to bottom right, var(--accent-secondary), var(--accent-primary));"
								>{currentAgent.name}</span
							>
							<span style="color: var(--accent-secondary);">
								<ChevronDown
									className="transition-transform duration-200 w-4 h-4 {isAgentDropdownOpen
										? 'rotate-180'
										: ''}"
									strokeWidth="2"
								/>
							</span>
						</button>

						{#if isAgentDropdownOpen}
							<div
								class="liquid-glass z-1000 min-w-64 animate-[dropdown-appear_0.2s_ease] rounded-3xl p-2 shadow-[0_24px_48px_rgba(12,10,30,0.5)]"
								style="position: absolute; top: calc(100% + 0.5rem); left: 0;"
							>
								<span class="liquid-glass__highlight" aria-hidden="true"></span>
								<ul class="liquid-glass__content m-0 list-none p-0" role="listbox">
									{#each agents as agent (agent.id)}
										<li
											role="option"
											aria-selected={agent.id ===
												chrome.island.agentSelector.selectedAgent}
										>
											<button
												class="flex w-full cursor-pointer flex-col items-start gap-0.5 rounded-2xl border-none bg-transparent px-4 py-3 text-left transition-all duration-150 hover:bg-white/8"
												style={agent.id ===
												chrome.island.agentSelector.selectedAgent
													? 'background-color: var(--accent-bg);'
													: ''}
												onclick={() => selectAgent(agent.id)}
											>
												<span
													class="text-[0.9375rem] font-semibold text-white/95"
													>{agent.name}</span
												>
												{#if agent.description}
													<span
														class="text-[0.8125rem] text-[rgba(225,225,255,0.6)]"
														>{agent.description}</span
													>
												{/if}
											</button>
										</li>
									{/each}
								</ul>
							</div>
						{/if}
					</div>

					{#if isMobileViewport}
						<button
							class="flex h-12 w-12 cursor-pointer items-center justify-center text-white/80 transition-transform duration-150 hover:scale-[1.05] hover:text-white active:scale-[0.97]"
							onclick={() => sidebar?.toggleChatSidebar?.()}
							aria-label={sidebar?.isChatSidebarOpen
								? 'close sidebar'
								: 'open sidebar'}
							aria-expanded={sidebar?.isChatSidebarOpen}
						>
							<Sidebar className="h-6 w-6" />
						</button>
					{/if}

					<button
						class="flex h-12 w-12 cursor-pointer items-center justify-center text-white/80 transition-transform duration-150 hover:scale-[1.05] hover:text-white active:scale-[0.97]"
						onclick={handleTemporaryChatToggle}
						aria-label="temporary chat"
					>
						{#if isTemporaryChatActive}
							<ChatBubbleDottedChecked className="h-6 w-6" />
						{:else}
							<ChatBubbleDotted className="h-6 w-6" />
						{/if}
					</button>
				{/if}
			</div>

			<!-- center: activity area -->
			<div class="flex min-w-0 items-center justify-center">
				{#if chrome.island.activityText}
					<div class="max-w-160 truncate text-sm text-white/70">
						{chrome.island.activityText}
					</div>
				{/if}
			</div>

			<!-- right: controls + user -->
			<div class="flex items-center justify-end gap-2">
				<div
					class="overflow-hidden transition-[max-width,opacity,transform] duration-200 ease-out {isHomeLayout
						? 'pointer-events-none max-w-0 -translate-x-1 opacity-0'
						: 'max-w-12 translate-x-0 opacity-100'}"
				>
					<button
						class="flex h-12 w-12 cursor-pointer items-center justify-center text-white/80 transition-transform duration-150 hover:scale-[1.05] hover:text-white active:scale-[0.97]"
						onclick={handleHome}
						aria-label="home"
					>
						<Home className="h-6 w-6" />
					</button>
				</div>

				<button
					class="flex h-12 w-12 cursor-pointer items-center justify-center text-white/80 transition-transform duration-150 hover:scale-[1.05] hover:text-white active:scale-[0.97]"
					onclick={() => chrome.toggleDock()}
					aria-label={chrome.isDockOpen ? 'close dock' : 'open dock'}
					aria-expanded={chrome.isDockOpen}
				>
					<AppNotification className="h-6 w-6" />
				</button>

				<UserProfileTrigger user={$userDisplay} placement="header" isExpanded={false} />
			</div>
		</div>
	</header>
</div>

<style>
	@keyframes dropdown-appear {
		from {
			opacity: 0;
			transform: translateX(-50%) translateY(-0.5rem);
		}
		to {
			opacity: 1;
			transform: translateX(-50%) translateY(0);
		}
	}
</style>
