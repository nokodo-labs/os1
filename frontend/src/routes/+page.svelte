<script lang="ts">
	import { browser } from '$app/environment'
	import { goto, onNavigate } from '$app/navigation'
	import { resolve } from '$app/paths'
	import { page } from '$app/state'
	import { runCreateAndRunStream } from '$lib/api/streaming'
	import { getAccessToken } from '$lib/auth/session.svelte'
	import AgentSelector from '$lib/components/chat/AgentSelector.svelte'
	import AssistantChatMessage from '$lib/components/chat/AssistantChatMessage.svelte'
	import ChatGptLoadingIndicator from '$lib/components/chat/ChatGptLoadingIndicator.svelte'
	import ChatInput from '$lib/components/chat/ChatInput.svelte'
	import ChatSidebarToggleButton from '$lib/components/chat/ChatSidebarToggleButton.svelte'
	import TemporaryChatToggleButton from '$lib/components/chat/TemporaryChatToggleButton.svelte'
	import UserChatMessage from '$lib/components/chat/UserChatMessage.svelte'
	import AppsGrid from '$lib/components/home/AppsGrid.svelte'
	import HomeSuggestions, {
		type HomeSuggestion,
	} from '$lib/components/home/HomeSuggestions.svelte'
	import AppNotification from '$lib/components/icons/AppNotification.svelte'
	import ArchiveBox from '$lib/components/icons/ArchiveBox.svelte'
	import ChatPlus from '$lib/components/icons/ChatPlus.svelte'
	import Cog6 from '$lib/components/icons/Cog6.svelte'
	import EyeSlash from '$lib/components/icons/EyeSlash.svelte'
	import Search from '$lib/components/icons/Search.svelte'
	import { useDebugUi } from '$lib/contexts/debugUiContext.svelte'
	import { useSystemChrome } from '$lib/contexts/systemChromeContext.svelte'
	import { accentStore } from '$lib/stores/accent.svelte'
	import { agents } from '$lib/stores/agents.svelte'
	import { appNavigation } from '$lib/stores/appNavigation.svelte'
	import { chat } from '$lib/stores/chat.svelte'
	import { device } from '$lib/stores/device.svelte'
	import { modals } from '$lib/stores/modals.svelte'
	import { pageTitleStore } from '$lib/stores/pageTitle.svelte'
	import { preferences } from '$lib/stores/preferences.svelte'
	import { selectedAgent } from '$lib/stores/selectedAgent.svelte'
	import { session } from '$lib/stores/session.svelte'
	import { fade } from 'svelte/transition'

	let inputValue = $state(chat.getDraft('home'))
	let isGenerating = $state(false)
	let focusToken = $state(0)
	let showSuggestions = $state(false)
	let highlightedIndex = $state(-1)
	let isSuggestionNavigationActive = $state(false)

	// optimistic chat state shown while create_and_run is streaming
	let optimisticContent = $state<string | null>(null)
	let createAndRunAbort = $state<AbortController | null>(null)

	const chrome = useSystemChrome()
	const debugUi = useDebugUi()

	// set accent color for auto accent colors feature
	$effect(() => {
		accentStore.set('lilac')
	})

	type ChatMode = 'new' | 'temp' | null

	const chatMode = $derived.by((): ChatMode => {
		if (!browser) return null
		const chat = page.url.searchParams.get('chat')
		if (chat === 'new' || chat === 'temp') return chat
		return null
	})

	const isChatMode = $derived(chatMode === 'new' || chatMode === 'temp')
	const isTemporaryChatMode = $derived(chatMode === 'temp')

	$effect(() => {
		pageTitleStore.pageTitle = isChatMode ? 'new chat' : 'home'
	})

	let showChatBanner = $state(false)

	// ============ VIEW TRANSITIONS FOR QUERY PARAM CHANGES ============
	// the root layout intentionally skips same-path navigations.
	// home uses query params for in-place mode switches (e.g. /?chat=new), so we
	// enable VT only for same-path navigations.
	onNavigate((navigation) => {
		const start = document.startViewTransition
		if (!start) return

		const from = navigation.from?.url
		const to = navigation.to?.url
		if (!from || !to) return
		if (from.pathname !== to.pathname) return
		if (from.search === to.search) return

		return new Promise<void>((resolve) => {
			start.call(document, async () => {
				resolve()
				await navigation.complete
			})
		})
	})

	// ============ EFFECTS ============
	// explicit focus requests from buttons (new chat, temp chat, etc)
	$effect(() => {
		if (!browser) return
		const handler = () => {
			focusToken += 1
		}
		window.addEventListener('focus:chat-input', handler)
		return () => window.removeEventListener('focus:chat-input', handler)
	})

	// auto-focus on route/mode changes (desktop only - mobile skips to avoid keyboard popup)
	let lastAutoFocusKey = $state<string | null>(null)
	$effect(() => {
		if (!browser) return
		if (device.isMobile) return
		if (page.url.pathname !== '/') return
		const chat = page.url.searchParams.get('chat')
		if (chat !== null && chat !== 'new' && chat !== 'temp') return
		const key = `${page.url.pathname}?chat=${chat ?? ''}`
		if (key === lastAutoFocusKey) return
		lastAutoFocusKey = key
		focusToken += 1
	})

	let chatStartError = $state<string | null>(null)
	$effect(() => {
		let timeoutId: number | null = null
		if (isChatMode) {
			showChatBanner = false
			timeoutId = window.setTimeout(() => {
				showChatBanner = true
			}, 420) as unknown as number
		} else {
			showChatBanner = false
			// abort any in-progress create_and_run when leaving chat mode
			if (createAndRunAbort) {
				createAndRunAbort.abort()
				createAndRunAbort = null
				isGenerating = false
				optimisticContent = null
			}
		}
		return () => {
			if (timeoutId !== null) window.clearTimeout(timeoutId)
		}
	})

	// sync input draft to chat store so it persists across navigation
	$effect(() => {
		chat.setDraft('home', inputValue)
	})

	const normalizedQuery = $derived(inputValue.trim().toLowerCase())
	const suggestions = $derived.by((): HomeSuggestion[] => {
		if (!normalizedQuery) return []
		const all: HomeSuggestion[] = [
			{
				id: 'search',
				title: `search for "${inputValue.trim()}"`,
				subtitle: 'use ↑↓ then enter to select',
				icon: Search,
			},
			{
				id: 'settings',
				title: 'settings',
				subtitle: 'open preferences',
				icon: Cog6,
			},
			{
				id: 'archived-chats',
				title: 'archived chats',
				subtitle: 'browse archived threads',
				icon: ArchiveBox,
			},
			{
				id: 'dock',
				title: chrome.isDockOpen ? 'hide dock' : 'show dock',
				subtitle: 'notifications + control center',
				icon: AppNotification,
			},
		]
		const scored = all
			.map((s) => {
				const hay = `${s.title} ${s.subtitle ?? ''}`.toLowerCase()
				const score = s.title.toLowerCase().startsWith(normalizedQuery)
					? 3
					: hay.includes(normalizedQuery)
						? 1
						: 0
				return { s, score }
			})
			.filter((x) => x.score > 0)
			.sort((a, b) => b.score - a.score)
			.map((x) => x.s)
		return scored.slice(0, 6)
	})

	$effect(() => {
		const hasQuery = inputValue.trim().length > 0
		showSuggestions = hasQuery
		isSuggestionNavigationActive = false
		if (!hasQuery) highlightedIndex = -1
		if (highlightedIndex >= suggestions.length) highlightedIndex = -1
	})

	// inject Island context actions (agent selector, sidebar toggle, temp chat toggle)
	$effect(() => {
		chrome.setContextActions(islandContextActions)
		return () => chrome.setContextActions(null)
	})

	// ============ NAVIGATION HELPERS ============
	async function setHomeChatMode(mode: Exclude<ChatMode, null>, opts?: { replace?: boolean }) {
		chatStartError = null
		const navOpts = {
			keepFocus: true,
			noScroll: true,
			replaceState: opts?.replace ?? false,
		}
		if (mode === 'temp') {
			await goto(resolve('/?chat=temp' as unknown as '/'), navOpts)
		} else {
			await goto(resolve('/?chat=new' as unknown as '/'), navOpts)
		}
	}

	async function createThreadAndNavigate(content: string): Promise<void> {
		const token = getAccessToken()
		if (!token) {
			chatStartError = 'please log in again'
			inputValue = content
			return
		}

		if (!selectedAgent.id) {
			chatStartError = 'select an agent first'
			inputValue = content
			return
		}

		// show optimistic UI immediately
		optimisticContent = content
		isGenerating = true
		inputValue = ''

		const controller = new AbortController()
		createAndRunAbort = controller

		try {
			const generator = runCreateAndRunStream({
				agentId: selectedAgent.id,
				input: content,
				isTemporary: isTemporaryChatMode,
				signal: controller.signal,
			})

			const first = await generator.next()
			if (first.done || !first.value || first.value.event !== 'thread_created') {
				throw new Error('could not start chat')
			}

			const thread = first.value.data as unknown as import('$lib/stores/chat.svelte').Thread
			chat.threadCache.set(thread)
			chat.activeThread = thread
			createAndRunAbort = null

			// hand off the live generator so the chat page continues consuming
			// the same stream — no abort, no duplicate run request.
			// thread_created was already consumed; remaining events are ChatStreamDelta.
			chat.pendingCreateAndRun = {
				threadId: thread.id,
				stream: generator as AsyncGenerator<
					import('$lib/api/streaming').ChatStreamDelta,
					void,
					unknown
				>,
			}

			// navigate seamlessly — replaceState so back goes to home, not /?chat=new
			await goto(resolve(`/c/${thread.id}`), {
				keepFocus: true,
				noScroll: true,
				replaceState: true,
			})
			return
		} catch (e) {
			if (!controller.signal.aborted) {
				chatStartError = e instanceof Error ? e.message : 'could not start chat. try again.'
				inputValue = content
			}
			isGenerating = false
			optimisticContent = null
			createAndRunAbort = null
		}
	}

	function handleSendMessage(content: string) {
		chatStartError = null
		void (async () => {
			if (!isChatMode) {
				await setHomeChatMode('new', { replace: true })
			}
			await createThreadAndNavigate(content)
		})()
	}

	function handleStopGeneration() {
		createAndRunAbort?.abort()
		isGenerating = false
		optimisticContent = null
	}

	function selectSuggestion(suggestion: HomeSuggestion) {
		showSuggestions = false
		highlightedIndex = -1
		isSuggestionNavigationActive = false
		if (suggestion.id === 'settings') {
			inputValue = ''
			void goto(resolve(appNavigation.getEntryRoute('settings')), {
				keepFocus: true,
				noScroll: true,
			})
			return
		}
		if (suggestion.id === 'archived-chats') {
			inputValue = ''
			modals.open('archived-chats')
			return
		}
		if (suggestion.id === 'dock') {
			inputValue = ''
			chrome.toggleDock()
			return
		}
		if (suggestion.id === 'search') {
			chrome.setPulse(`search: ${inputValue.trim()}`)
			window.setTimeout(() => chrome.setPulse(null), 1800)
			return
		}
	}

	function handleHomeInputKeyDown(event: KeyboardEvent): boolean {
		if (!showSuggestions || suggestions.length === 0) return false
		if (event.key === 'ArrowDown') {
			event.preventDefault()
			isSuggestionNavigationActive = true
			highlightedIndex =
				highlightedIndex < 0 ? 0 : (highlightedIndex + 1) % suggestions.length
			return true
		}
		if (event.key === 'ArrowUp') {
			event.preventDefault()
			isSuggestionNavigationActive = true
			highlightedIndex =
				highlightedIndex < 0
					? suggestions.length - 1
					: (highlightedIndex - 1 + suggestions.length) % suggestions.length
			return true
		}
		if (event.key === 'Escape') {
			event.preventDefault()
			showSuggestions = false
			highlightedIndex = -1
			isSuggestionNavigationActive = false
			return true
		}
		if (event.key === 'Enter' && !event.shiftKey) {
			if (!isSuggestionNavigationActive || highlightedIndex < 0) return false
			event.preventDefault()
			selectSuggestion(suggestions[highlightedIndex])
			return true
		}
		return false
	}
</script>

{#snippet islandContextActions()}
	<AgentSelector
		selectedAgent={selectedAgent.id}
		onAgentChange={(agentId) => selectedAgent.set(agentId)}
	/>
	{#if device.isMobile}
		<ChatSidebarToggleButton />
	{/if}
	<TemporaryChatToggleButton />
{/snippet}

{#if isChatMode}
	<!-- ═══════════════ CHAT MODE LAYOUT ═══════════════ -->
	<!-- absolute positioning mirrors the chat page layout so content aligns
	     exactly during the view transition (the main shell's padding is bypassed). -->
	<div class="absolute inset-0 flex flex-col">
		<!-- scrollable content area -->
		<div class="min-h-0 flex-1 overflow-y-auto">
			<div
				class="mx-auto flex min-h-full w-full flex-col {device.isMobile ? '' : 'max-w-7xl'}"
				style="padding-left: var(--spacing-page-x); padding-right: var(--spacing-page-x); padding-top: var(--chrome-island-offset); padding-bottom: 96px;"
			>
				{#if optimisticContent}
					<!-- optimistic chat: user message + loading assistant -->
					<div class="flex flex-1 flex-col gap-6 py-4">
						<div class="space-y-3">
							<UserChatMessage
								content={optimisticContent}
								timestamp={new Date()}
								tailStyle={preferences.data.appearance.bubbleTailStyle ?? 'none'}
								showTail={preferences.data.appearance.bubbleTailStyle !== 'none'}
							/>
						</div>
						<div class="space-y-3">
							<AssistantChatMessage
								content=""
								isLastMessage={true}
								isRunActive={true}
								isStreaming={true}
								showStreamingPlaceholder={false}
								modelName={agents.list.find((a) => a.id === selectedAgent.id)
									?.name ?? 'assistant'}
								avatarUrl={agents.list.find((a) => a.id === selectedAgent.id)
									?.profile_image_url ?? null}
							>
								{#snippet lead()}
									<div
										class="assistant-markdown text-[0.95rem] leading-relaxed text-white/60"
									>
										<div class="my-3">
											<ChatGptLoadingIndicator />
										</div>
									</div>
								{/snippet}
							</AssistantChatMessage>
						</div>
					</div>
				{:else if showChatBanner}
					<div
						class="flex flex-1 items-center justify-center py-16"
						in:fade={{ duration: 220 }}
						out:fade={{ duration: 120 }}
					>
						<div class="max-w-md text-center">
							<div
								class="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-white/5 text-white/85"
							>
								{#if isTemporaryChatMode}
									<EyeSlash class="h-7 w-7" />
								{:else}
									<ChatPlus class="h-7 w-7" />
								{/if}
							</div>
							{#if isTemporaryChatMode}
								<h2 class="text-2xl font-semibold text-white/90">temporary chat</h2>
								<p class="mt-2 text-sm text-white/60">
									messages here won't be saved
								</p>
							{:else}
								<h2 class="text-2xl font-semibold text-white/90">new chat</h2>
							{/if}
						</div>
					</div>
				{/if}
			</div>
		</div>

		<!-- bottom input (absolute bottom, matching chat page layout) -->
		<div class="absolute right-0 bottom-0 left-0 z-10 shrink-0 pt-4 pb-4">
			<div
				class="relative mx-auto w-full {device.isMobile ? '' : 'max-w-7xl'}"
				style="padding-left: var(--spacing-page-x); padding-right: var(--spacing-page-x);"
			>
				{#if chatStartError}
					<div
						class="mb-4 rounded-xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white/70"
					>
						{chatStartError}
					</div>
				{/if}
				<div style="view-transition-name: chat-input;">
					<ChatInput
						bind:value={inputValue}
						onSubmit={handleSendMessage}
						onStop={handleStopGeneration}
						onKeyDown={handleHomeInputKeyDown}
						{isGenerating}
						placeholder="send a message"
						{focusToken}
					/>
				</div>
			</div>
		</div>
	</div>
{:else}
	<!-- ═══════════════ HOME MODE LAYOUT ═══════════════ -->

	<!-- stay in normal flow so the column matches the island + sidebar spacing -->
	<div class="flex min-h-0 flex-1 flex-col">
		<div
			class="mx-auto flex w-full flex-1 flex-col pb-2 {device.isMobile ? '' : 'max-w-7xl'}"
			style="padding-left: var(--spacing-page-x); padding-right: var(--spacing-page-x);"
		>
			<!-- top spacer: pushes content toward vertical center -->
			<div class="flex-[0.6]"></div>

			<!-- greeting -->
			<div
				style="view-transition-name: landing-greeting;"
				class="mb-12 flex flex-col items-center justify-center gap-2 text-center"
			>
				<h1 class="text-4xl font-medium text-white">
					hi <span
						class="bg-clip-text text-transparent [-webkit-background-clip:text] [-webkit-text-fill-color:transparent]"
						style="background-image: linear-gradient(to bottom right, var(--accent-primary), var(--accent-primary));"
						>{session.userDisplay.name}</span
					>
				</h1>
				<p class="text-xl text-white/60">good afternoon</p>
			</div>

			<!-- input -->
			<div style="view-transition-name: chat-input;">
				<ChatInput
					bind:value={inputValue}
					onSubmit={handleSendMessage}
					onStop={handleStopGeneration}
					onKeyDown={handleHomeInputKeyDown}
					{isGenerating}
					placeholder="send a message"
					{focusToken}
				/>
			</div>

			<!-- apps grid: flex-1 fills remaining vertical space -->
			<div
				style="view-transition-name: apps-grid;"
				class="relative min-h-0 flex-1 {device.isMobile ? 'mt-6' : 'mt-14'}"
			>
				<AppsGrid iconShape={debugUi.appsGridIconShape} fullWidth={device.isMobile} />

				<!-- suggestions overlay: sits on TOP of apps grid -->
				<div class="absolute top-0 right-0 left-0 z-20 -mt-10">
					<HomeSuggestions
						open={showSuggestions}
						query={inputValue}
						{suggestions}
						{highlightedIndex}
						onHighlight={(i) => {
							highlightedIndex = i
							isSuggestionNavigationActive = true
						}}
						onSelect={selectSuggestion}
					/>
				</div>
			</div>
		</div>
	</div>
{/if}
