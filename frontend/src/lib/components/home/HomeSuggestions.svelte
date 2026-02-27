<script module lang="ts">
	import type SearchIcon from '$lib/components/icons/Search.svelte'
	import type {
		NotesRouteId,
		RemindersRouteId,
		SettingsRouteId,
	} from '$lib/stores/appNavigation.svelte'

	type IconComponent = typeof SearchIcon

	export type HomeSuggestion = {
		id: string
		title: string
		subtitle?: string
		icon: IconComponent
	}

	type SuggestionRoute = '/' | `/c/${string}` | '/library' | NotesRouteId | RemindersRouteId | SettingsRouteId

	export type SuggestionAction =
		| { type: 'navigate'; path: SuggestionRoute }
		| { type: 'modal'; id: 'archived-chats' }
		| { type: 'toggle-dock' }
		| { type: 'pulse'; message: string }
</script>

<script lang="ts">
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

	// search state
	let isSearching = $state(false)
	let isSearchError = $state(false)
	let searchResults = $state<SearchResult[]>([])
	let highlightedIndex = $state(-1)
	let isSuggestionNavigationActive = $state(false)
	let forceClosed = $state(false)
	let searchDebounceTimer: number | null = null
	let searchAbort: AbortController | null = null

	// full (hybrid) search state
	let isFullSearching = $state(false)
	let isFullSearchError = $state(false)
	let hasDoneFullSearch = $state(false)
	let fullSearchAbort: AbortController | null = null

	const normalizedQuery = $derived(query.trim().toLowerCase())
	const open = $derived(normalizedQuery.length > 0 && !forceClosed)

	// suggestion data
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

	// search logic
	async function runAutocomplete(q: string, signal: AbortSignal): Promise<void> {
		const results: SearchResult[] = []
		isSearchError = false
		try {
			for await (const result of searchStream({
				query: q,
				limit: 10,
				mode: 'autocomplete',
				signal,
			})) {
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

	function triggerFullSearch() {
		fullSearchAbort?.abort()
		fullSearchAbort = null
		const q = query.trim()
		if (!q) return
		isFullSearching = true
		isFullSearchError = false
		const controller = new AbortController()
		fullSearchAbort = controller
		void (async () => {
			const results: SearchResult[] = []
			try {
				for await (const result of searchStream({
					query: q,
					limit: 20,
					mode: 'full',
					signal: controller.signal,
				})) {
					if (controller.signal.aborted) break
					results.push(result)
				}
				if (!controller.signal.aborted) {
					searchResults = results
					hasDoneFullSearch = true
				}
			} catch {
				if (!controller.signal.aborted) isFullSearchError = true
			} finally {
				if (!controller.signal.aborted) isFullSearching = false
			}
			fullSearchAbort = null
		})()
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
			isFullSearching = false
			isFullSearchError = false
			hasDoneFullSearch = false
			fullSearchAbort?.abort()
			fullSearchAbort = null
			highlightedIndex = -1
			isSuggestionNavigationActive = false
			searchResults = []
			return
		}

		cancelPending()
		isSearching = true
		isFullSearching = false
		hasDoneFullSearch = false
		fullSearchAbort?.abort()
		fullSearchAbort = null
		isSuggestionNavigationActive = false
		highlightedIndex = -1

		searchDebounceTimer = window.setTimeout(() => {
			searchDebounceTimer = null
			const controller = new AbortController()
			searchAbort = controller
			void runAutocomplete(q, controller.signal)
		}, 150) as unknown as number
	})

	// actions
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
					path: appNavigation.getEntryRoute('reminders'),
				})
			}
			return
		}

		if (suggestion.id === 'settings') {
			onAction({
				type: 'navigate',
				path: appNavigation.getEntryRoute('settings'),
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
		if (suggestion.id === 'chats') {
			onAction({ type: 'navigate', path: '/' })
			return
		}
		if (suggestion.id === 'notes') {
			onAction({ type: 'navigate', path: appNavigation.getEntryRoute('notes') })
			return
		}
		if (suggestion.id === 'reminders') {
			onAction({ type: 'navigate', path: appNavigation.getEntryRoute('reminders') })
			return
		}
		if (suggestion.id === 'library') {
			onAction({ type: 'navigate', path: '/library' })
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
		class="rounded-container flex min-h-0 flex-col overflow-hidden shadow-[0_32px_64px_rgba(12,10,30,0.45)]"
	>
		<div class="relative z-10 flex min-h-0 flex-col">
			<div
				class="no-scrollbar min-h-0 overflow-y-auto p-2"
				role="listbox"
				aria-label="suggestions"
			>
				{#if isSearching}
					<!-- shimmer autocomplete state -->
					<div class="flex items-center gap-3 px-3 py-2.5">
						<div
							class="rounded-pill flex h-9 w-9 shrink-0 items-center justify-center bg-foreground/8 text-foreground/85"
						>
							<Search class="h-5 w-5" strokeWidth="2" />
						</div>
						<ShimmerText className="text-sm font-semibold text-foreground/60">
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
						<div class="text-sm text-foreground/40">search failed - try again</div>
					</div>
				{:else if suggestions.length === 0 && !isFullSearching}
					<!-- no results -->
					<div class="flex items-center gap-3 px-3 py-2.5">
						<div
							class="rounded-pill flex h-9 w-9 shrink-0 items-center justify-center bg-foreground/8 text-foreground/40"
						>
							<Search class="h-5 w-5" strokeWidth="2" />
						</div>
						<div class="text-sm text-foreground/40">no results found</div>
					</div>
				{:else}
					{#if isFullSearching}
						<!-- shimmer row while full search runs -->
						<div class="flex items-center gap-3 px-3 py-2">
							<div
								class="rounded-pill flex h-8 w-8 shrink-0 items-center justify-center bg-foreground/6 text-foreground/50"
							>
								<Search class="h-4 w-4" strokeWidth="2" />
							</div>
							<ShimmerText className="text-xs font-medium text-foreground/50">
								searching deeper
							</ShimmerText>
						</div>
					{/if}
					{#each suggestions as suggestion, index (suggestion.id)}
						{@const Icon = suggestion.icon}
						<button
							type="button"
							role="option"
							aria-selected={highlightedIndex >= 0 && index === highlightedIndex}
							class="rounded-pill flex w-full items-center gap-3 border-none px-3 py-2 text-left transition-colors {index ===
								highlightedIndex && highlightedIndex >= 0
								? 'bg-foreground/10'
								: 'bg-transparent hover:bg-foreground/7'}"
							onmouseenter={() => {
								highlightedIndex = index
								isSuggestionNavigationActive = true
							}}
							onclick={() => selectSuggestion(suggestion)}
						>
							<div
								class="rounded-pill flex h-9 w-9 shrink-0 items-center justify-center bg-foreground/8 text-foreground/85"
							>
								<Icon class="h-5 w-5" strokeWidth="2" />
							</div>
							<div class="min-w-0">
								<div class="truncate text-sm font-semibold text-foreground/90">
									{suggestion.title}
								</div>
								{#if suggestion.subtitle}
									<div class="truncate text-sm text-foreground/55">
										{suggestion.subtitle}
									</div>
								{/if}
							</div>
						</button>
					{/each}
					{#if !hasDoneFullSearch && !isFullSearching && suggestions.length > 0}
						<!-- full search trigger -->
						<div class="mt-1 border-t border-foreground/8 pt-1">
							<button
								type="button"
								class="rounded-pill flex w-full items-center gap-3 border-none px-3 py-2 text-left transition-colors hover:bg-foreground/7"
								onclick={triggerFullSearch}
							>
								<div
									class="rounded-pill flex h-8 w-8 shrink-0 items-center justify-center bg-foreground/6 text-foreground/50"
								>
									<Search class="h-4 w-4" strokeWidth="2" />
								</div>
								<div class="text-xs text-foreground/50">search more in-depth</div>
							</button>
						</div>
					{/if}
					{#if isFullSearchError}
						<div class="px-3 py-1.5 text-xs text-red-400/70">full search failed</div>
					{/if}
				{/if}
			</div>
		</div>
	</LiquidGlass>
{/if}
