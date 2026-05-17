<script lang="ts">
	import { browser } from '$app/environment'
	import { goto, onNavigate } from '$app/navigation'
	import { resolve } from '$app/paths'
	import { page } from '$app/state'
	import {
		SEARCH_RESOURCE_TYPES,
		runCreateAndRunStream,
		type RunInput,
		type SearchResourceType,
	} from '$lib/api/streaming'
	import { getAccessToken } from '$lib/auth/session.svelte'
	import { deriveToolChoice, type RunModifiers } from '$lib/chat/attachments'
	import AgentSelector from '$lib/components/chat/AgentSelector.svelte'
	import ChatInput from '$lib/components/chat/ChatInput.svelte'
	import ChatSidebarToggleButton from '$lib/components/chat/ChatSidebarToggleButton.svelte'
	import TemporaryChatToggleButton from '$lib/components/chat/TemporaryChatToggleButton.svelte'
	import AppsGrid from '$lib/components/home/AppsGrid.svelte'
	import HomeSearchMode from '$lib/components/home/HomeSearchMode.svelte'
	import HomeSuggestions, {
		type SuggestionAction,
	} from '$lib/components/home/HomeSuggestions.svelte'
	import ChatPlus from '$lib/components/icons/ChatPlus.svelte'
	import EyeSlash from '$lib/components/icons/EyeSlash.svelte'
	import Search from '$lib/components/icons/Search.svelte'
	import { useDebugUi } from '$lib/contexts/debugUiContext.svelte'
	import { useSystemChrome } from '$lib/contexts/systemChromeContext.svelte'
	import { accentStore } from '$lib/stores/accent.svelte'
	import { chat } from '$lib/stores/chat.svelte'
	import { device } from '$lib/stores/device.svelte'
	import { modals } from '$lib/stores/modals.svelte'
	import { pageTitleStore } from '$lib/stores/pageTitle.svelte'
	import { selectedAgent } from '$lib/stores/selectedAgent.svelte'
	import { session } from '$lib/stores/session.svelte'
	import { newTypeid } from '$lib/utils/typeid'
	import { fade } from 'svelte/transition'

	let inputValue = $state(chat.getDraft('home'))
	let searchInputValue = $state('')
	let submittedSearchQuery = $state('')
	let searchResourceTypes = $state<SearchResourceType[]>([...SEARCH_RESOURCE_TYPES])
	let focusToken = $state(0)
	let searchFocusToken = $state(0)

	// abort controller for in-flight create_and_run
	let createAndRunAbort = $state<AbortController | null>(null)
	let isGenerating = $state(false)

	// keyboard handler exposed by HomeSuggestions
	let suggestionsKeyHandler = $state<((event: KeyboardEvent) => boolean) | undefined>(undefined)

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
		const q = page.url.searchParams.get('q')
		if (chat === 'temp') return 'temp'
		if (chat === 'new' || q) return 'new'
		return null
	})

	const isChatMode = $derived(chatMode === 'new' || chatMode === 'temp')
	const isTemporaryChatMode = $derived(chatMode === 'temp')
	const isTemporaryChatActionActive = $derived(
		isTemporaryChatMode || (chat.activeThread?.is_temporary ?? false)
	)
	const searchModeQuery = $derived.by((): string | null => {
		if (!browser) return null
		if (!page.url.searchParams.has('search')) return null
		return page.url.searchParams.get('search') ?? ''
	})
	const isSearchMode = $derived(searchModeQuery !== null)

	// auto-send ?q= query param as a new chat message (runs once per unique q value).
	// the effect reactively waits for auth + agent readiness so it doesn't fire
	// before initApp() completes or before an agent is resolved.
	let lastAutoSentQuery = $state<string | null>(null)
	$effect(() => {
		if (!browser) return
		const q = page.url.searchParams.get('q')
		if (!q) return
		if (q === lastAutoSentQuery) return

		// reactive guards: re-runs automatically when token/agent become available
		const token = getAccessToken()
		if (!token) return
		if (!selectedAgent.id) return

		lastAutoSentQuery = q
		handleSendMessage(q)
	})

	$effect(() => {
		pageTitleStore.pageTitle = isSearchMode ? 'search' : isChatMode ? 'new chat' : 'home'
	})

	let lastSearchModeQuery = $state<string | null>(null)
	const activeModeBanner = $derived.by((): 'new' | 'temp' | 'search' | null => {
		if (isSearchMode) return submittedSearchQuery.trim() ? null : 'search'
		if (isChatMode) return isTemporaryChatMode ? 'temp' : 'new'
		return null
	})

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
			const vt = start.call(document, async () => {
				resolve()
				await navigation.complete
			}) as { finished?: Promise<unknown> } | void

			// swallow rejections so unfinished transitions don't cause unhandled errors
			if (vt?.finished) vt.finished.catch(() => {})
		})
	})

	// ============ EFFECTS ============
	// explicit focus requests from buttons (new chat, temp chat, etc)
	$effect(() => {
		if (!browser) return
		const handler = () => {
			if (device.isMobile) return
			focusToken += 1
		}
		window.addEventListener('focus:chat-input', handler)
		return () => window.removeEventListener('focus:chat-input', handler)
	})

	$effect(() => {
		if (!browser) return
		const handler = () => {
			if (device.isMobile) return
			searchFocusToken += 1
		}
		window.addEventListener('focus:home-search', handler)
		return () => window.removeEventListener('focus:home-search', handler)
	})

	$effect(() => {
		const q = searchModeQuery
		if (q === null) return
		if (q === lastSearchModeQuery) return
		lastSearchModeQuery = q
		searchInputValue = q
		submittedSearchQuery = q
	})

	// auto-focus on route/mode changes (desktop only - mobile skips to avoid keyboard popup)
	let lastAutoFocusKey = $state<string | null>(null)
	$effect(() => {
		if (!browser) return
		if (device.isMobile) return
		if (page.url.pathname !== '/') return
		if (isSearchMode) return
		const chat = page.url.searchParams.get('chat')
		if (chat !== null && chat !== 'new' && chat !== 'temp') return
		const key = `${page.url.pathname}?chat=${chat ?? ''}`
		if (key === lastAutoFocusKey) return
		lastAutoFocusKey = key
		focusToken += 1
	})

	let chatStartError = $state<string | null>(null)
	$effect(() => {
		if (isChatMode || isSearchMode) return
		// abort any in-progress create_and_run when leaving chat mode
		if (createAndRunAbort) {
			createAndRunAbort.abort()
			createAndRunAbort = null
			isGenerating = false
		}
	})

	// sync input draft to chat store so it persists across navigation
	$effect(() => {
		chat.setDraft('home', inputValue)
	})

	// inject island context actions
	$effect(() => {
		chrome.setContextActions(islandContextActions)
		return () => chrome.setContextActions(null)
	})

	// ============ NAVIGATION HELPERS ============

	async function createThreadAndNavigate(
		content: string,
		modifiers?: RunModifiers
	): Promise<void> {
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

		isGenerating = true
		inputValue = ''

		// generate a client-side thread ID so we can navigate immediately
		const threadId = newTypeid('thread')
		const now = new Date().toISOString()

		// build RunInput shape
		const runInput: RunInput = { text: content || null }
		if (modifiers?.attachments && modifiers.attachments.length > 0) {
			runInput.attachment_ids = modifiers.attachments.map((a) => a.fileId)
		}

		const toolChoice = modifiers ? deriveToolChoice(modifiers) : null

		const controller = new AbortController()
		createAndRunAbort = controller

		try {
			// cache an optimistic thread stub so the chat page can render immediately
			const optimisticThread: import('$lib/stores/chat.svelte').Thread = {
				id: threadId,
				owner_id: '',
				title: null,
				tags: [],
				is_archived: false,
				is_temporary: isTemporaryChatMode,
				project_ids: [],
				created_at: now,
				updated_at: now,
				last_activity_at: now,
			}
			chat.threadCache.set(optimisticThread)
			chat.activeThread = optimisticThread

			const generator = runCreateAndRunStream({
				agentId: selectedAgent.id,
				input: runInput,
				threadId,
				isTemporary: isTemporaryChatMode,
				toolChoice,
				signal: controller.signal,
			})

			// hand off the full generator (including thread_created) to the chat page
			chat.pendingCreateAndRun = {
				threadId,
				text: content.trim(),
				attachments: modifiers?.attachments ?? [],
				stream: generator,
			}

			createAndRunAbort = null

			// navigate immediately - replaceState so back goes to home, not /?chat=new
			await goto(resolve(`/c/${threadId}`), {
				keepFocus: true,
				noScroll: true,
				replaceState: true,
			})
		} catch (e) {
			if (!controller.signal.aborted) {
				chatStartError = e instanceof Error ? e.message : 'could not start chat. try again.'
			}
			isGenerating = false
			createAndRunAbort = null
		}
	}

	function handleSendMessage(content: string, modifiers?: RunModifiers) {
		chatStartError = null
		void createThreadAndNavigate(content, modifiers)
	}

	function handleStopGeneration() {
		createAndRunAbort?.abort()
		isGenerating = false
		chatStartError = null
	}

	function handleSearchSubmit(content: string) {
		const q = content.trim()
		submittedSearchQuery = q
		const target = q ? `/?search=${encodeURIComponent(q)}` : '/?search'
		void goto(resolve(target as unknown as '/'), {
			keepFocus: true,
			noScroll: true,
			replaceState: true,
		})
	}

	function handleSearchClear() {
		searchInputValue = ''
		submittedSearchQuery = ''
		void goto(resolve('/?search' as unknown as '/'), {
			keepFocus: true,
			noScroll: true,
			replaceState: true,
		})
	}

	function handleOpenSearchMode() {
		inputValue = ''
		if (browser) window.dispatchEvent(new CustomEvent('focus:home-search'))
		if (isSearchMode) {
			return
		}
		void goto(resolve('/?search' as unknown as '/'), { keepFocus: true, noScroll: true })
	}

	function handleSuggestionAction(action: SuggestionAction) {
		if (action.type === 'navigate') {
			inputValue = ''
			void goto(resolve(action.path), { keepFocus: true, noScroll: true })
		} else if (action.type === 'modal') {
			inputValue = ''
			modals.open(action.id)
		} else if (action.type === 'toggle-dock') {
			inputValue = ''
			chrome.toggleDock()
		} else if (action.type === 'search') {
			inputValue = ''
			const q = action.query.trim()
			searchInputValue = q
			submittedSearchQuery = q
			const target = q ? `/?search=${encodeURIComponent(q)}` : '/?search'
			void goto(resolve(target as unknown as '/'), { keepFocus: true, noScroll: true })
		} else if (action.type === 'pulse') {
			chrome.setPulse(action.message)
			window.setTimeout(() => chrome.setPulse(null), 1800)
		}
	}
</script>

{#snippet modeBanner(mode: 'new' | 'temp' | 'search')}
	<div
		class="home-mode-banner flex flex-1 items-center justify-center py-16"
		style="view-transition-name: mode-banner;"
	>
		<div class="max-w-md text-center">
			<div
				class="bg-foreground/5 text-foreground/85 mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full"
			>
				{#if mode === 'temp'}
					<EyeSlash class="h-7 w-7" />
				{:else if mode === 'search'}
					<Search class="h-7 w-7" strokeWidth="2" />
				{:else}
					<ChatPlus class="h-7 w-7" />
				{/if}
			</div>
			{#if mode === 'temp'}
				<h2 class="text-foreground/90 text-2xl font-semibold">temporary chat</h2>
				<p class="text-foreground/60 mt-2 text-sm">messages here won't be saved</p>
			{:else if mode === 'search'}
				<h2 class="text-foreground/90 text-2xl font-semibold">find mode</h2>
			{:else}
				<h2 class="text-foreground/90 text-2xl font-semibold">new chat</h2>
			{/if}
		</div>
	</div>
{/snippet}

{#snippet islandContextActions()}
	<AgentSelector
		selectedAgent={selectedAgent.id}
		onAgentChange={(agentId) => selectedAgent.set(agentId)}
	/>
	{#if device.isMobile}
		<ChatSidebarToggleButton />
	{/if}
	{#if !isTemporaryChatActionActive}
		<TemporaryChatToggleButton />
	{/if}
	{#if !isSearchMode}
		<button
			type="button"
			class="flex cursor-pointer items-center justify-center opacity-80 transition-all duration-150 hover:scale-[1.05] hover:opacity-100 active:scale-[0.97]"
			style="color: var(--accent-primary);"
			onclick={handleOpenSearchMode}
			aria-label="search"
		>
			<Search class="h-[60%] w-auto" strokeWidth="2" />
		</button>
	{/if}
{/snippet}

{#if isChatMode || isSearchMode}
	<!-- active chat/search mode layout -->
	<div class="absolute inset-0 flex flex-col">
		<div class="relative flex-1 overflow-y-auto" style="scrollbar-gutter: stable;">
			<div
				class="mx-auto flex min-h-full w-full flex-col {device.isMobile ? '' : 'max-w-7xl'}"
				style="padding-left: var(--spacing-page-x); padding-right: var(--spacing-page-x); padding-top: calc(var(--chrome-island-offset, 0px) + var(--spacing-island-content)); padding-bottom: 72px;"
			>
				{#if isChatMode && chatStartError}
					<div class="flex flex-1 items-center justify-center py-16">
						<div class="max-w-md text-center">
							<p class="text-error text-sm">{chatStartError}</p>
							<button
								type="button"
								class="text-foreground/70 hover:text-foreground/95 mt-3 rounded-xl bg-transparent px-3 py-1.5 text-sm transition-colors"
								onclick={() => (chatStartError = null)}
							>
								dismiss
							</button>
						</div>
					</div>
				{:else if activeModeBanner}
					{@render modeBanner(activeModeBanner)}
				{:else if isSearchMode}
					<HomeSearchMode query={submittedSearchQuery} types={searchResourceTypes} />
				{/if}
			</div>
		</div>

		<div
			class="absolute right-0 bottom-0 left-0 z-10 pt-4 {device.virtualKeyboardOpen &&
			device.isMobile
				? 'pb-2'
				: 'pb-6'}"
		>
			<div
				class="relative mx-auto w-full {device.isMobile ? '' : 'max-w-7xl'}"
				style="padding-left: var(--spacing-page-x); padding-right: var(--spacing-page-x);"
			>
				<div class="transition-all duration-500 ease-in-out">
					{#if isSearchMode}
						<ChatInput
							bind:value={searchInputValue}
							mode="search"
							onSubmit={handleSearchSubmit}
							onClear={handleSearchClear}
							searchTypes={searchResourceTypes}
							onSearchTypesChange={(types) => (searchResourceTypes = types)}
							placeholder="search anything"
							focusToken={searchFocusToken}
							viewTransitionName="chat-input"
							clearOnSubmit={false}
						/>
					{:else}
						<ChatInput
							bind:value={inputValue}
							onSubmit={handleSendMessage}
							onStop={handleStopGeneration}
							onKeyDown={(e) => suggestionsKeyHandler?.(e) || false}
							{isGenerating}
							placeholder="send a message"
							{focusToken}
							viewTransitionName="chat-input"
						/>
					{/if}
				</div>
			</div>
		</div>
	</div>
{:else}
	<!-- ═══════════════ HOME MODE LAYOUT ═══════════════ -->

	<!-- stay in normal flow so the column matches the island + sidebar spacing -->
	<div class="flex min-h-0 flex-1 flex-col">
		<div
			class="mx-auto flex min-h-0 w-full flex-1 flex-col pb-2 {device.isMobile
				? ''
				: 'max-w-7xl'}"
			style="padding-left: var(--spacing-page-x); padding-right: var(--spacing-page-x);"
		>
			<!-- top spacer: pushes content toward vertical center (normal mode only) -->
			{#if !(device.virtualKeyboardOpen && device.isMobile)}
				<div class="flex-[0.6]"></div>
			{/if}

			<!-- greeting: hidden when virtual keyboard is open on mobile -->
			{#if !(device.virtualKeyboardOpen && device.isMobile)}
				<div
					out:fade={{ duration: 200 }}
					in:fade={{ duration: 300, delay: 150 }}
					style="view-transition-name: landing-greeting;"
					class="mb-12 flex flex-col items-center justify-center gap-2 text-center"
				>
					<h1 class="text-foreground text-4xl font-medium">
						hi <span
							class="bg-clip-text text-transparent [-webkit-background-clip:text] [-webkit-text-fill-color:transparent]"
							style="background-image: linear-gradient(to bottom right, var(--accent-primary), var(--accent-primary));"
							>{session.userDisplay.name}</span
						>
					</h1>
					<p class="text-foreground/60 text-xl">good afternoon</p>
				</div>
			{/if}

			<!-- input -->
			<div
				style="view-transition-name: chat-input;"
				class={device.virtualKeyboardOpen && device.isMobile ? 'order-last mt-3' : ''}
			>
				<ChatInput
					bind:value={inputValue}
					onSubmit={handleSendMessage}
					onStop={handleStopGeneration}
					onKeyDown={(e) => suggestionsKeyHandler?.(e) || false}
					{isGenerating}
					placeholder="send a message"
					{focusToken}
				/>
			</div>

			<!-- apps grid + suggestions -->
			<div
				class="relative flex min-h-0 flex-1 flex-col {device.virtualKeyboardOpen &&
				device.isMobile
					? 'order-first'
					: ''}"
			>
				<!-- suggestions: absolute on desktop, in-flow on mobile+keyboard -->
				<div
					class="flex min-h-0 flex-col {device.virtualKeyboardOpen && device.isMobile
						? 'flex-1 justify-end'
						: 'absolute top-0 right-0 left-0 z-20 max-h-full pt-3'}"
				>
					<HomeSuggestions
						query={inputValue}
						onAction={handleSuggestionAction}
						onKeyHandler={(h) => (suggestionsKeyHandler = h)}
					/>
				</div>

				<!-- apps grid (hidden when keyboard open) -->
				<div
					style="view-transition-name: apps-grid;"
					class="{device.virtualKeyboardOpen && device.isMobile
						? 'hidden'
						: 'flex min-h-0 flex-1 flex-col'} {device.isMobile ? 'mt-6' : 'mt-14'}"
				>
					<AppsGrid iconShape={debugUi.appsGridIconShape} fullWidth={device.isMobile} />
				</div>
			</div>
		</div>
	</div>
{/if}
