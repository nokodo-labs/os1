<script module lang="ts">
	import type SearchIcon from '$lib/components/icons/Search.svelte'

	type IconComponent = typeof SearchIcon

	export type HomeSuggestion = {
		id: string
		title: string
		subtitle?: string
		icon: IconComponent
	}

	export type SuggestionAction =
		| { type: 'navigate'; path: string }
		| { type: 'modal'; id: 'archived-chats' }
		| { type: 'toggle-dock' }
		| { type: 'pulse'; message: string }
</script>

<script lang="ts">
	import { resolve } from '$app/paths'
	import { searchStream, type SearchResult } from '$lib/api/streaming'
	import LiquidGlass from '$lib/components/effects/LiquidGlass.svelte'
	import ShimmerText from '$lib/components/effects/ShimmerText.svelte'
	import AppNotification from '$lib/components/icons/AppNotification.svelte'
	import ArchiveBox from '$lib/components/icons/ArchiveBox.svelte'
	import BookOpen from '$lib/components/icons/BookOpen.svelte'
	import Calendar from '$lib/components/icons/Calendar.svelte'
	import ChatBubbles from '$lib/components/icons/ChatBubbles.svelte'
	import CheckBox from '$lib/components/icons/CheckBox.svelte'
	import ClockRotateRight from '$lib/components/icons/ClockRotateRight.svelte'
	import Cog6 from '$lib/components/icons/Cog6.svelte'
	import Document from '$lib/components/icons/Document.svelte'
	import Note from '$lib/components/icons/Note.svelte'
	import Search from '$lib/components/icons/Search.svelte'
	import Users from '$lib/components/icons/Users.svelte'
	import XMark from '$lib/components/icons/XMark.svelte'
	import { useSystemChrome } from '$lib/contexts/systemChromeContext.svelte'
	import { appNavigation } from '$lib/stores/appNavigation.svelte'
	import { preferences } from '$lib/stores/preferences.svelte'
	import '$lib/styles/liquid-glass.css'

	interface Props {
		query: string
		onAction: (action: SuggestionAction) => void
		keyHandler?: ((event: KeyboardEvent) => boolean) | undefined
	}

	let { query, onAction, keyHandler = $bindable(undefined) }: Props = $props()

	const chrome = useSystemChrome()

	// --- search state ---
	let isSearching = $state(false)
	let isSearchError = $state(false)
	let searchResults = $state<SearchResult[]>([])
	let highlightedIndex = $state(-1)
	let isSuggestionNavigationActive = $state(false)
	let forceClosed = $state(false)
	let searchDebounceTimer: number | null = null
	let searchAbort: AbortController | null = null

	const normalizedQuery = $derived(query.trim().toLowerCase())
	const open = $derived(normalizedQuery.length > 0 && !forceClosed)

	// --- suggestion data ---
	const allAppSuggestions: HomeSuggestion[] = [
		{ id: 'chats', title: 'chats', subtitle: 'recent conversations', icon: ChatBubbles },
		{
			id: 'reminders',
			title: 'reminders',
			subtitle: 'upcoming reminders',
			icon: ClockRotateRight,
		},
		{ id: 'notes', title: 'notes', subtitle: 'your notes', icon: Note },
		{ id: 'friends', title: 'friends', subtitle: 'contacts and people', icon: Users },
		{ id: 'library', title: 'library', subtitle: 'saved content', icon: BookOpen },
		{ id: 'calendar', title: 'calendar', subtitle: 'events and schedule', icon: Calendar },
	]

	const appSuggestions = $derived.by(() => {
		const hp = preferences.data.homepage
		return allAppSuggestions.filter((s) => {
			const key = s.id as keyof typeof hp
			return hp[key] !== false
		})
	})

	const allSuggestions: HomeSuggestion[] = $derived.by(() => [
		...appSuggestions,
		{ id: 'settings', title: 'settings', subtitle: 'open preferences', icon: Cog6 },
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
	])

	const searchResultIcons: Record<string, typeof ChatBubbles> = {
		thread: ChatBubbles,
		reminder: CheckBox,
		note: Document,
	}

	const suggestions = $derived.by((): HomeSuggestion[] => {
		if (!normalizedQuery) return []

		// local app/action suggestions (always instant)
		const localScored = allSuggestions
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
			.slice(0, 3)

		// API search results mapped to HomeSuggestion format
		const apiResults: HomeSuggestion[] = searchResults.map((r) => ({
			id: `search:${r.type}:${r.id}`,
			title: r.title,
			subtitle: r.subtitle ?? r.type,
			icon: searchResultIcons[r.type] ?? ChatBubbles,
		}))

		return [...localScored, ...apiResults].slice(0, 10)
	})

	// --- search logic ---
	async function runSearch(q: string, signal: AbortSignal): Promise<void> {
		const results: SearchResult[] = []
		isSearchError = false
		try {
			for await (const result of searchStream({ query: q, limit: 10, signal })) {
				if (signal.aborted) break
				results.push(result)
				searchResults = [...results]
			}
		} catch {
			if (signal.aborted) return
			isSearchError = true
		} finally {
			if (!signal.aborted) {
				isSearching = false
			}
		}
	}

	// debounced search effect - only tracks query prop
	$effect(() => {
		const q = query.trim()
		const hasQuery = q.length > 0

		function cancelPending() {
			if (searchDebounceTimer !== null) {
				window.clearTimeout(searchDebounceTimer)
				searchDebounceTimer = null
			}
			searchAbort?.abort()
			searchAbort = null
		}

		// reset force-closed state on any query change
		forceClosed = false

		if (!hasQuery) {
			cancelPending()
			isSearching = false
			isSearchError = false
			highlightedIndex = -1
			isSuggestionNavigationActive = false
			searchResults = []
			return
		}

		cancelPending()
		isSearching = true
		isSuggestionNavigationActive = false
		highlightedIndex = -1

		searchDebounceTimer = window.setTimeout(() => {
			searchDebounceTimer = null
			const controller = new AbortController()
			searchAbort = controller
			void runSearch(q, controller.signal)
		}, 300) as unknown as number
	})

	// --- actions ---
	function selectSuggestion(suggestion: HomeSuggestion) {
		forceClosed = true
		highlightedIndex = -1
		isSuggestionNavigationActive = false

		if (suggestion.id.startsWith('search:')) {
			const parts = suggestion.id.split(':')
			const type = parts[1]
			const entityId = parts.slice(2).join(':')
			if (type === 'thread') {
				onAction({ type: 'navigate', path: `/c/${entityId}` })
			} else if (type === 'note') {
				onAction({ type: 'navigate', path: `/notes/${entityId}` })
			} else if (type === 'reminder') {
				onAction({
					type: 'navigate',
					path: resolve(appNavigation.getEntryRoute('reminders')),
				})
			}
			return
		}

		if (suggestion.id === 'settings') {
			onAction({
				type: 'navigate',
				path: resolve(appNavigation.getEntryRoute('settings')),
			})
			return
		}
		if (suggestion.id === 'archived-chats') {
			onAction({ type: 'modal', id: 'archived-chats' })
			return
		}
		if (suggestion.id === 'dock') {
			onAction({ type: 'toggle-dock' })
			return
		}
		onAction({ type: 'pulse', message: `${suggestion.title}: coming soon` })
	}

	// keyboard handler exposed to parent via $bindable
	function handleKeyDown(event: KeyboardEvent): boolean {
		if (!open || suggestions.length === 0) return false
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
			forceClosed = true
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

	keyHandler = handleKeyDown
</script>

{#if open}
	<LiquidGlass
		tag="div"
		class="rounded-container mt-3 overflow-hidden shadow-[0_32px_64px_rgba(12,10,30,0.45)]"
	>
		<div class="relative z-10">
			<div class="p-2" role="listbox" aria-label="suggestions">
				{#if isSearching}
					<!-- shimmer searching state -->
					<div class="flex items-center gap-3 px-3 py-2.5">
						<div
							class="rounded-pill flex h-9 w-9 shrink-0 items-center justify-center bg-white/8 text-white/85"
						>
							<Search class="h-5 w-5" strokeWidth="2" />
						</div>
						<ShimmerText className="text-sm font-semibold text-white/60">
							searching
						</ShimmerText>
					</div>
				{:else if isSearchError}
					<!-- error state -->
					<div class="flex items-center gap-3 px-3 py-2.5">
						<div
							class="rounded-pill flex h-9 w-9 shrink-0 items-center justify-center bg-red-500/10 text-red-400"
						>
							<XMark class="h-5 w-5" />
						</div>
						<div class="text-sm text-white/40">search failed - try again</div>
					</div>
				{:else if suggestions.length === 0}
					<!-- no results -->
					<div class="flex items-center gap-3 px-3 py-2.5">
						<div
							class="rounded-pill flex h-9 w-9 shrink-0 items-center justify-center bg-white/8 text-white/40"
						>
							<Search class="h-5 w-5" strokeWidth="2" />
						</div>
						<div class="text-sm text-white/40">no results found</div>
					</div>
				{:else}
					{#each suggestions as suggestion, index (suggestion.id)}
						{@const Icon = suggestion.icon}
						<button
							type="button"
							role="option"
							aria-selected={highlightedIndex >= 0 && index === highlightedIndex}
							class="rounded-pill flex w-full items-center gap-3 border-none px-3 py-2 text-left transition-colors {index ===
								highlightedIndex && highlightedIndex >= 0
								? 'bg-white/10'
								: 'bg-transparent hover:bg-white/7'}"
							onmouseenter={() => {
								highlightedIndex = index
								isSuggestionNavigationActive = true
							}}
							onclick={() => selectSuggestion(suggestion)}
						>
							<div
								class="rounded-pill flex h-9 w-9 shrink-0 items-center justify-center bg-white/8 text-white/85"
							>
								<Icon class="h-5 w-5" strokeWidth="2" />
							</div>
							<div class="min-w-0">
								<div class="truncate text-sm font-semibold text-white/90">
									{suggestion.title}
								</div>
								{#if suggestion.subtitle}
									<div class="truncate text-sm text-white/55">
										{suggestion.subtitle}
									</div>
								{/if}
							</div>
						</button>
					{/each}
				{/if}
			</div>
		</div>
	</LiquidGlass>
{/if}
