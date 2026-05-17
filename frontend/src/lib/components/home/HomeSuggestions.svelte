<script module lang="ts">
	import type { AccentColorKey } from '$lib/contexts/themeContext.svelte'
	import type {
		CalendarRouteId,
		MessagesRouteId,
		NotesRouteId,
		ProjectsRouteId,
		RemindersRouteId,
		SettingsRouteId,
		SocialRouteId,
	} from '$lib/stores/appNavigation.svelte'
	import type { Component } from 'svelte'

	type IconComponent = Component<{
		class?: string
		color?: string
		strokeWidth?: string | number
		variant?: 'outline' | 'solid'
	}>

	export type HomeSuggestion = {
		id: string
		title: string
		subtitle?: string
		icon: IconComponent
		accent?: AccentColorKey
		iconVariant?: 'outline' | 'solid'
	}

	type SuggestionRoute =
		| '/'
		| `/c/${string}`
		| CalendarRouteId
		| MessagesRouteId
		| '/library'
		| NotesRouteId
		| ProjectsRouteId
		| RemindersRouteId
		| SettingsRouteId
		| SocialRouteId

	export type SuggestionAction =
		| { type: 'navigate'; path: SuggestionRoute }
		| { type: 'modal'; id: 'archived-chats' }
		| { type: 'search'; query: string }
		| { type: 'toggle-dock' }
		| { type: 'pulse'; message: string }
</script>

<script lang="ts">
	import { searchStream, type SearchResult } from '$lib/api/streaming'
	import AppNotification from '$lib/components/icons/AppNotification.svelte'
	import ArchiveBox from '$lib/components/icons/ArchiveBox.svelte'
	import Cog6 from '$lib/components/icons/Cog6.svelte'
	import Search from '$lib/components/icons/Search.svelte'
	import ResourceWidget from '$lib/components/widgets/ResourceWidget.svelte'
	import type { ResourceItem } from '$lib/components/widgets/types'
	import { useSystemChrome } from '$lib/contexts/systemChromeContext.svelte'
	import { accentColors } from '$lib/contexts/themeContext.svelte'
	import { appVisuals, type AppVisualId } from '$lib/resources/resourceVisuals'
	import { searchResultToResource } from '$lib/resources/searchResults'
	import { appNavigation } from '$lib/stores/appNavigation.svelte'
	import { preferences } from '$lib/stores/preferences.svelte'

	interface Props {
		query: string
		onAction: (action: SuggestionAction) => void
		onKeyHandler?: (handler: (event: KeyboardEvent) => boolean) => void
	}

	let { query, onAction, onKeyHandler }: Props = $props()

	type SuggestionEntry =
		| { kind: 'action'; id: string; suggestion: HomeSuggestion }
		| { kind: 'resource'; id: string; resource: ResourceItem }
	type HomepageSuggestionKey = keyof typeof preferences.data.homepage
	type AppSuggestion = HomeSuggestion & { preferenceKey: HomepageSuggestionKey }

	const chrome = useSystemChrome()

	// search state
	let searchResults = $state<SearchResult[]>([])
	let highlightedIndex = $state(-1)
	let isSuggestionNavigationActive = $state(false)
	let forceClosed = $state(false)
	let searchDebounceTimer: number | null = null
	let searchAbort: AbortController | null = null

	const normalizedQuery = $derived(query.trim().toLowerCase())

	// suggestion data
	function appVisual(id: AppVisualId) {
		return appVisuals.find((app) => app.id === id)
	}

	function appSuggestion(id: AppVisualId, preferenceKey: HomepageSuggestionKey): AppSuggestion {
		const visual = appVisual(id)
		return {
			id,
			title: visual?.title ?? id,
			subtitle: visual?.description,
			icon: visual?.icon ?? Search,
			accent: visual?.accent ?? 'gray',
			iconVariant: id === 'library' ? 'outline' : 'solid',
			preferenceKey,
		}
	}

	const allAppSuggestions: AppSuggestion[] = [
		appSuggestion('messages', 'chats'),
		appSuggestion('reminders', 'reminders'),
		appSuggestion('notes', 'notes'),
		appSuggestion('projects', 'projects'),
		appSuggestion('calendar', 'calendar'),
		appSuggestion('library', 'library'),
		appSuggestion('social', 'friends'),
	]

	const appSuggestions = $derived.by(() => {
		const hp = preferences.data.homepage
		return allAppSuggestions.filter((s) => {
			return hp[s.preferenceKey] !== false
		})
	})

	const allSuggestions: HomeSuggestion[] = $derived.by(() => [
		...appSuggestions,
		{
			id: 'settings',
			title: 'settings',
			subtitle: 'open preferences',
			icon: Cog6,
			accent: 'gray',
			iconVariant: 'solid',
		},
		{
			id: 'archived-chats',
			title: 'archived chats',
			subtitle: 'browse archived threads',
			icon: ArchiveBox,
			accent: 'green',
			iconVariant: 'solid',
		},
		{
			id: 'dock',
			title: chrome.isDockOpen ? 'hide dock' : 'show dock',
			subtitle: 'notifications + control center',
			icon: AppNotification,
			accent: 'blue',
			iconVariant: 'solid',
		},
	])

	function suggestionAccentStyle(accent: HomeSuggestion['accent']): string {
		const colors = accentColors[accent ?? 'gray']
		return `--suggestion-accent: ${colors.primary}; --suggestion-accent-rgb: ${colors.rgb};`
	}

	const suggestionEntries = $derived.by((): SuggestionEntry[] => {
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

		const actionEntries: SuggestionEntry[] = localScored.map((suggestion) => ({
			kind: 'action',
			id: `action:${suggestion.id}`,
			suggestion,
		}))
		const resourceEntries: SuggestionEntry[] = searchResults.map((result) => {
			const resource = searchResultToResource(result)
			return {
				kind: 'resource',
				id: `resource:${resource.type}:${resource.id}`,
				resource,
			}
		})

		return [...actionEntries, ...resourceEntries].slice(0, 10)
	})
	const open = $derived(
		normalizedQuery.length > 0 && suggestionEntries.length > 0 && !forceClosed
	)

	// search logic
	async function runAutocomplete(q: string, signal: AbortSignal): Promise<void> {
		const results: SearchResult[] = []
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
		} finally {
			if (!signal.aborted) searchResults = [...results]
		}
	}

	function triggerSearchMode() {
		const q = query.trim()
		if (!q) return
		forceClosed = true
		onAction({ type: 'search', query: q })
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
			highlightedIndex = -1
			isSuggestionNavigationActive = false
			searchResults = []
			return
		}

		cancelPending()
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
	function selectResource(resource: ResourceItem) {
		switch (resource.type) {
			case 'thread':
				onAction({ type: 'navigate', path: `/c/${resource.id}` })
				return
			case 'note':
				onAction({ type: 'navigate', path: `/notes/${resource.id}` })
				return
			case 'reminder_list':
				onAction({ type: 'navigate', path: `/reminders/lists/${resource.id}` })
				return
			case 'calendar':
				onAction({ type: 'navigate', path: appNavigation.getEntryRoute('calendar') })
				return
			case 'project':
				onAction({ type: 'navigate', path: `/projects/${resource.id}` })
				return
			case 'file':
				onAction({ type: 'pulse', message: "can't open this result yet" })
				return
		}
	}

	function selectEntry(entry: SuggestionEntry) {
		forceClosed = true
		highlightedIndex = -1
		isSuggestionNavigationActive = false

		if (entry.kind === 'resource') {
			selectResource(entry.resource)
			return
		}

		const { suggestion } = entry

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
		if (suggestion.id === 'messages') {
			onAction({ type: 'navigate', path: appNavigation.getEntryRoute('messages') })
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
		if (suggestion.id === 'calendar') {
			onAction({ type: 'navigate', path: appNavigation.getEntryRoute('calendar') })
			return
		}
		if (suggestion.id === 'projects') {
			onAction({ type: 'navigate', path: appNavigation.getEntryRoute('projects') })
			return
		}
		if (suggestion.id === 'social') {
			onAction({ type: 'navigate', path: appNavigation.getEntryRoute('social') })
			return
		}
		onAction({ type: 'pulse', message: `${suggestion.title}: coming soon` })
	}

	// keyboard handler exposed to parent via $bindable
	function handleKeyDown(event: KeyboardEvent): boolean {
		if (!open || suggestionEntries.length === 0) return false
		if (event.key === 'ArrowDown') {
			event.preventDefault()
			isSuggestionNavigationActive = true
			highlightedIndex =
				highlightedIndex < 0 ? 0 : (highlightedIndex + 1) % suggestionEntries.length
			return true
		}
		if (event.key === 'ArrowUp') {
			event.preventDefault()
			isSuggestionNavigationActive = true
			highlightedIndex =
				highlightedIndex < 0
					? suggestionEntries.length - 1
					: (highlightedIndex - 1 + suggestionEntries.length) % suggestionEntries.length
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
			const entry = suggestionEntries[highlightedIndex]
			if (!entry) return true
			selectEntry(entry)
			return true
		}
		return false
	}

	$effect(() => {
		onKeyHandler?.(handleKeyDown)
	})
</script>

{#if open}
	<div
		class="liquid-glass liquid-glass--clip rounded-container isolate flex min-h-0 flex-col overflow-hidden [--lg-bg:color-mix(in_oklch,var(--background)_18%,transparent)] [--lg-blur:8px] dark:[--lg-bg:color-mix(in_oklch,var(--background)_42%,transparent)]"
	>
		<div class="relative z-10 flex min-h-0 flex-col">
			<div
				class="no-scrollbar min-h-0 overflow-y-auto p-2"
				role="listbox"
				aria-label="suggestions"
			>
				<div
					class="flex flex-col gap-0 overflow-hidden rounded-[calc(var(--radius-container)-0.5rem)]"
				>
					{#each suggestionEntries as entry, index (entry.id)}
						{#if entry.kind === 'action'}
							{@const suggestion = entry.suggestion}
							{@const Icon = suggestion.icon}
							<button
								type="button"
								role="option"
								aria-selected={highlightedIndex >= 0 && index === highlightedIndex}
								class="focus-visible:bg-foreground/10 flex w-full items-center gap-3 border-none px-3 py-2 text-left transition-colors duration-150 ease-out {index ===
									highlightedIndex && highlightedIndex >= 0
									? 'bg-foreground/10'
									: 'hover:bg-foreground/8 bg-transparent'}"
								onmouseenter={() => {
									highlightedIndex = index
									isSuggestionNavigationActive = true
								}}
								onclick={() => selectEntry(entry)}
							>
								<div
									class="rounded-pill flex h-9 w-9 shrink-0 items-center justify-center bg-[rgb(var(--suggestion-accent-rgb)/0.14)] text-(--suggestion-accent) shadow-[inset_0_0_0_1px_rgb(var(--suggestion-accent-rgb)/0.18)]"
									style={suggestionAccentStyle(suggestion.accent)}
								>
									{#if suggestion.iconVariant === 'solid'}
										<Icon variant="solid" class="h-5 w-5" strokeWidth="2" />
									{:else}
										<Icon class="h-5 w-5" strokeWidth="2" />
									{/if}
								</div>
								<div class="min-w-0">
									<div class="text-foreground/90 truncate text-sm font-semibold">
										{suggestion.title}
									</div>
									{#if suggestion.subtitle}
										<div class="text-foreground/55 truncate text-sm">
											{suggestion.subtitle}
										</div>
									{/if}
								</div>
							</button>
						{:else}
							<div
								role="option"
								tabindex="-1"
								aria-selected={highlightedIndex >= 0 && index === highlightedIndex}
								class="overflow-hidden transition-colors duration-150 ease-out {index ===
									highlightedIndex && highlightedIndex >= 0
									? 'bg-foreground/10'
									: 'hover:bg-foreground/8 bg-transparent'}"
								onmouseenter={() => {
									highlightedIndex = index
									isSuggestionNavigationActive = true
								}}
							>
								<ResourceWidget
									resource={entry.resource}
									layout="bare"
									onclick={() => selectEntry(entry)}
									class="transition-none"
								/>
							</div>
						{/if}
					{/each}
				</div>
				<!-- full search trigger -->
				<div class="border-foreground/8 mt-2 border-t pt-2">
					<button
						type="button"
						class="rounded-pill hover:bg-foreground/8 flex w-full items-center gap-3 border-none px-3 py-2 text-left transition-colors duration-150 ease-out"
						onclick={triggerSearchMode}
					>
						<div
							class="rounded-pill bg-foreground/6 text-foreground/50 flex h-8 w-8 shrink-0 items-center justify-center"
						>
							<Search class="h-4 w-4" strokeWidth="2" />
						</div>
						<div class="text-foreground/50 text-xs">search more in-depth</div>
					</button>
				</div>
			</div>
		</div>
	</div>
{/if}
