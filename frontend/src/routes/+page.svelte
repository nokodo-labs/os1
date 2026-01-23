<script lang="ts">
	import { browser } from '$app/environment'
	import { goto, onNavigate } from '$app/navigation'
	import { resolve } from '$app/paths'
	import { page } from '$app/state'
	import { apiClient } from '$lib/api/client'
	import { getJwtUserId } from '$lib/auth/jwt'
	import { getAccessToken } from '$lib/auth/session.svelte'
	import ChatInputLiquidGlass from '$lib/components/chat/ChatInput.svelte'
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
	import { modals } from '$lib/stores/modals.svelte'
	import { pageTitleStore } from '$lib/stores/pageTitle.svelte'
	import { selectedAgent } from '$lib/stores/selectedAgent.svelte'
	import { session } from '$lib/stores/session.svelte'
	import { fade } from 'svelte/transition'

	let inputValue = $state('')
	let isGenerating = $state(false)
	let focusToken = $state(0)
	let showSuggestions = $state(false)
	let highlightedIndex = $state(-1)
	let isSuggestionNavigationActive = $state(false)

	const chrome = useSystemChrome()
	const debugUi = useDebugUi()

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
	onNavigate((navigation) => {
		if (!document.startViewTransition) return

		return new Promise((resolve) => {
			document.startViewTransition(async () => {
				resolve()
				await navigation.complete
			})
		})
	})

	// ============ EFFECTS ============
	$effect(() => {
		if (!browser) return
		const handleRequestFocus = () => {
			focusToken += 1
		}
		window.addEventListener('nokodo:focus-home-input', handleRequestFocus)
		return () => window.removeEventListener('nokodo:focus-home-input', handleRequestFocus)
	})

	let lastAutoFocusKey = $state<string | null>(null)
	$effect(() => {
		if (!browser) return
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
		}
		return () => {
			if (timeoutId !== null) window.clearTimeout(timeoutId)
		}
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

	$effect(() => {
		chrome.setAgentSelector({
			selectedAgent: selectedAgent.id,
			onAgentChange: (agentId: string) => selectedAgent.set(agentId),
		})
	})

	$effect(() => {
		return () => chrome.setAgentSelector(null)
	})

	// ============ NAVIGATION HELPERS ============
	async function navigateToChat(threadId: string) {
		const target = `/c/${threadId}`
		// @ts-expect-error resolve typing is narrower than our constructed URL
		await goto(resolve(target as never), { keepFocus: true, noScroll: true })
	}

	async function setHomeChatMode(mode: Exclude<ChatMode, null>, opts?: { replace?: boolean }) {
		chatStartError = null
		const target = `/?chat=${mode}`
		// @ts-expect-error resolve typing is narrower than our constructed URL
		await goto(resolve(target as never), {
			keepFocus: true,
			noScroll: true,
			replaceState: opts?.replace ?? false,
		})
	}

	async function createThreadAndNavigate(content: string): Promise<void> {
		const token = getAccessToken()
		const userId = token ? getJwtUserId(token) : null
		if (!token || !userId) {
			chatStartError = 'please log in again'
			inputValue = content
			return
		}
		const { data, error } = await apiClient().POST('/v1/threads', {
			body: {
				owner_id: userId,
				is_archived: false,
				is_temporary: isTemporaryChatMode,
				tags: [],
				project_ids: [],
			},
		})
		if (error || !data) {
			chatStartError = 'could not start chat. try again.'
			inputValue = content
			return
		}
		session.activeThread = data
		session.pendingChatStart = { threadId: data.id, content }
		await navigateToChat(data.id)
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
		isGenerating = false
	}

	function selectSuggestion(suggestion: HomeSuggestion) {
		showSuggestions = false
		highlightedIndex = -1
		isSuggestionNavigationActive = false
		if (suggestion.id === 'settings') {
			inputValue = ''
			modals.open('settings')
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
			chrome.setActivityText(`search: ${inputValue.trim()}`)
			window.setTimeout(() => chrome.setActivityText(null), 1800)
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

{#if isChatMode}
	<!-- ═══════════════ CHAT MODE LAYOUT ═══════════════ -->

	<!-- keep everything inside the main content column so it aligns with the island and shifts with the sidebar -->
	<div class="flex min-h-0 flex-1 flex-col">
		<!-- scrollable content area -->
		<div class="min-h-0 flex-1 overflow-y-auto">
			<div
				class="mx-auto flex min-h-full w-full max-w-7xl flex-col px-[clamp(10px,4vw,32px)] pt-[clamp(12px,4vw,32px)] pb-8"
			>
				{#if showChatBanner}
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
									<EyeSlash className="h-7 w-7" />
								{:else}
									<ChatPlus className="h-7 w-7" />
								{/if}
							</div>
							{#if isTemporaryChatMode}
								<h2 class="text-2xl font-semibold text-white/90">
									temporary chat enabled
								</h2>
								<p class="mt-2 text-sm text-white/60">
									send a message to start. messages here won't be saved.
								</p>
							{:else}
								<h2 class="text-2xl font-semibold text-white/90">new chat</h2>
								<p class="mt-2 text-sm text-white/60">send a message to begin.</p>
							{/if}
						</div>
					</div>
				{/if}
			</div>
		</div>

		<!-- bottom input (non-fixed; stays aligned with island/sidebar) -->
		<div class="shrink-0 pt-4 pb-4">
			<div class="relative mx-auto w-full max-w-7xl px-[clamp(10px,4vw,32px)]">
				{#if chatStartError}
					<div
						class="mb-4 rounded-xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white/70"
					>
						{chatStartError}
					</div>
				{/if}
				<div style="view-transition-name: chat-input;">
					<ChatInputLiquidGlass
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
		<div class="mx-auto flex w-full max-w-7xl flex-1 flex-col px-[clamp(10px,4vw,32px)] pb-5">
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
						style="background-image: linear-gradient(to bottom right, var(--accent-secondary), var(--accent-primary));"
						>{session.userDisplay.name}</span
					>
				</h1>
				<p class="text-xl text-white/60">good afternoon</p>
			</div>

			<!-- input -->
			<div style="view-transition-name: chat-input;">
				<ChatInputLiquidGlass
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
			<div style="view-transition-name: apps-grid;" class="relative mt-14 min-h-0 flex-1">
				<AppsGrid iconShape={debugUi.appsGridIconShape} />

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
