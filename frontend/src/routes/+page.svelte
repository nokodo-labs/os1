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
		type SuggestionAction,
	} from '$lib/components/home/HomeSuggestions.svelte'
	import ChatPlus from '$lib/components/icons/ChatPlus.svelte'
	import EyeSlash from '$lib/components/icons/EyeSlash.svelte'
	import { useDebugUi } from '$lib/contexts/debugUiContext.svelte'
	import { useSystemChrome } from '$lib/contexts/systemChromeContext.svelte'
	import { accentStore } from '$lib/stores/accent.svelte'
	import { agents } from '$lib/stores/agents.svelte'
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

	// optimistic chat state shown while create_and_run is streaming
	let optimisticContent = $state<string | null>(null)
	let createAndRunAbort = $state<AbortController | null>(null)

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
		pageTitleStore.pageTitle = isChatMode ? 'new chat' : 'home'
	})

	let showChatBanner = $state(false)

	// ============ VIEW TRANSITIONS FOR QUERY PARAM CHANGES ============
	// the root layout intentionally skips same-path navigations.
	// home uses query params for in-place mode switches (e.g. /?chat=new), so we
	// enable VT only for same-path navigations.
	// we track the transition's finished promise so cross-page navigation can
	// wait for the in-page animation to complete (avoids stacking two VTs).
	let inPageTransitionDone: Promise<void> | null = null

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

			if (vt?.finished) {
				inPageTransitionDone = vt.finished.then(
					() => {},
					() => {}
				)
			}
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

	// inject island context actions
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
			// the same stream - no abort, no duplicate run request.
			// thread_created was already consumed; remaining events are ChatStreamDelta.
			chat.pendingCreateAndRun = {
				threadId: thread.id,
				stream: generator as AsyncGenerator<
					import('$lib/api/streaming').ChatStreamDelta,
					void,
					unknown
				>,
			}

			// wait for any in-page view transition (home -> chat layout) to finish
			// before starting cross-page navigation so the two VTs don't conflict
			if (inPageTransitionDone) {
				await inPageTransitionDone
				inPageTransitionDone = null
			}

			// navigate seamlessly - replaceState so back goes to home, not /?chat=new
			await goto(resolve(`/c/${thread.id}`), {
				keepFocus: true,
				noScroll: true,
				replaceState: true,
			})
			return
		} catch (e) {
			if (!controller.signal.aborted) {
				chatStartError = e instanceof Error ? e.message : 'could not start chat. try again.'
			}
			isGenerating = false
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
		chatStartError = null
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
		} else if (action.type === 'pulse') {
			chrome.setPulse(action.message)
			window.setTimeout(() => chrome.setPulse(null), 1800)
		}
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
		<div class="relative flex-1 overflow-y-auto" style="scrollbar-gutter: stable;">
			<div
				class="mx-auto flex min-h-full w-full flex-col {device.isMobile ? '' : 'max-w-7xl'}"
				style="padding-left: var(--spacing-page-x); padding-right: var(--spacing-page-x); padding-top: var(--chrome-island-offset); padding-bottom: 96px;"
			>
				{#if optimisticContent}
					<!-- optimistic chat: user message + assistant (loading / error) -->
					<div class="flex flex-1 flex-col gap-6 py-4">
						<div class="space-y-3">
							<UserChatMessage
								content={optimisticContent}
								timestamp={new Date()}
								tailStyle={preferences.data.appearance.bubbleTailStyle ?? 'none'}
								showTail={preferences.data.appearance.bubbleTailStyle !== 'none'}
							/>
							<AssistantChatMessage
								content={chatStartError ?? ''}
								tone={chatStartError ? 'error' : 'default'}
								isLastMessage={true}
								isRunActive={!chatStartError && isGenerating}
								isStreaming={!chatStartError && isGenerating}
								showStreamingPlaceholder={false}
								modelName={agents.list.find((a) => a.id === selectedAgent.id)
									?.name ?? 'assistant'}
								avatarUrl={agents.list.find((a) => a.id === selectedAgent.id)
									?.profile_image_url ?? null}
							>
								{#snippet lead()}
									{#if !chatStartError}
										<div
											class="assistant-markdown text-[0.95rem] leading-relaxed text-white/60"
										>
											<div class="my-3">
												<ChatGptLoadingIndicator />
											</div>
										</div>
									{/if}
								{/snippet}
								{#snippet actions()}
									{#if chatStartError}
										<button
											type="button"
											class="rounded-xl bg-transparent px-3 py-1.5 text-sm text-white/70 transition-colors hover:text-white/95"
											onclick={() => {
												chatStartError = null
												optimisticContent = null
											}}
										>
											dismiss
										</button>
									{/if}
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
					<h1 class="text-4xl font-medium text-white">
						hi <span
							class="bg-clip-text text-transparent [-webkit-background-clip:text] [-webkit-text-fill-color:transparent]"
							style="background-image: linear-gradient(to bottom right, var(--accent-primary), var(--accent-primary));"
							>{session.userDisplay.name}</span
						>
					</h1>
					<p class="text-xl text-white/60">good afternoon</p>
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
						bind:keyHandler={suggestionsKeyHandler}
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
