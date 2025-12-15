<script lang="ts">
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import ChatInputLiquidGlass from '$lib/components/chat/ChatInput.svelte'
	import AppsGrid from '$lib/components/home/AppsGrid.svelte'
	import HomeSuggestions, {
		type HomeSuggestion,
	} from '$lib/components/home/HomeSuggestions.svelte'
	import AppNotification from '$lib/components/icons/AppNotification.svelte'
	import ArchiveBox from '$lib/components/icons/ArchiveBox.svelte'
	import Cog6 from '$lib/components/icons/Cog6.svelte'
	import Search from '$lib/components/icons/Search.svelte'
	import { useDebugUi } from '$lib/contexts/debugUiContext.svelte'
	import { useSystemChrome } from '$lib/contexts/systemChromeContext.svelte'
	import { openModal } from '$lib/stores/modals'
	import { fade } from 'svelte/transition'

	let inputValue = $state('')
	let isGenerating = $state(false)
	let selectedModel = $state('gpt-4')

	let showSuggestions = $state(false)
	let highlightedIndex = $state(-1)
	let isSuggestionNavigationActive = $state(false)

	const chrome = useSystemChrome()
	const debugUi = useDebugUi()

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
			selectedAgent: selectedModel,
			onAgentChange: (agentId: string) => (selectedModel = agentId),
		})
	})

	$effect(() => {
		return () => chrome.setAgentSelector(null)
	})

	async function navigateToChat(threadId: string, content: string) {
		const target = `/chats/${threadId}?q=${encodeURIComponent(content)}`
		// Assume View Transitions API exists (per requirement), but keep a safe fallback.
		const start = (
			document as unknown as {
				startViewTransition?: (cb: () => Promise<void> | void) => void
			}
		).startViewTransition
		if (start) {
			// Must be invoked with `document` as `this`.
			start.call(document, async () => {
				// @ts-expect-error resolve typing is narrower than our constructed URL
				await goto(resolve(target as never), { keepFocus: true, noScroll: true })
			})
			return
		}
		// @ts-expect-error resolve typing is narrower than our constructed URL
		await goto(resolve(target as never), { keepFocus: true, noScroll: true })
	}

	function handleSendMessage(content: string) {
		// Create a new thread ID (mock)
		const threadId = Date.now().toString()
		// Navigate to the chat page with a view transition
		void navigateToChat(threadId, content)
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
			openModal('settings')
			return
		}

		if (suggestion.id === 'archived-chats') {
			inputValue = ''
			openModal('archived-chats')
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

<!-- Scrollable Area (kept for layout parity with /chats/[id]) -->
<div class="flex-1 overflow-y-auto">
	<div class="mx-auto flex min-h-full w-full max-w-7xl flex-col px-8 pt-8 pb-32"></div>
</div>

<!-- Input Area (Fixed Bottom) -->
<div class="absolute right-0 bottom-0 left-0 z-10 pt-10 pb-8">
	<div class="mx-auto w-full max-w-7xl px-8">
		<div
			style="view-transition-name: chat-input;"
			class="relative -translate-y-[40vh] transition-all duration-500 ease-in-out"
		>
			<div
				style="view-transition-name: landing-greeting;"
				class="mb-12 flex flex-col items-center justify-center gap-2 text-center"
				in:fade={{ duration: 200 }}
			>
				<h1 class="text-4xl font-medium text-white">
					hi <span
						class="bg-clip-text text-transparent [-webkit-background-clip:text] [-webkit-text-fill-color:transparent]"
						style="background-image: linear-gradient(to bottom right, var(--accent-secondary), var(--accent-primary));"
						>admin</span
					>
				</h1>
				<p class="text-xl text-white/60">good afternoon</p>
			</div>
			<ChatInputLiquidGlass
				bind:value={inputValue}
				onSubmit={handleSendMessage}
				onStop={handleStopGeneration}
				onKeyDown={handleHomeInputKeyDown}
				{isGenerating}
				placeholder="send a message"
			/>

			<div class="absolute top-full right-0 left-0 mt-14">
				<div style="view-transition-name: apps-grid;" class="relative">
					<AppsGrid iconShape={debugUi.appsGridIconShape} />

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
	</div>
</div>
