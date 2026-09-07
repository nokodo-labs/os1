<script lang="ts" module>
	/** one run of rows under an optional lowercase header. */
	export interface SearchResultsSection<Item> {
		id: string
		label?: string
		items: readonly Item[]
	}

	/** what a row gets from the box: whether it is the current one, and how to take over. */
	export interface SearchResultsRow {
		highlighted: boolean
		select: () => void
		hover: () => void
	}

	/** true when the box consumed the key, so the input it hangs over leaves it alone. */
	export type SearchResultsKeyHandler = (event: KeyboardEvent) => boolean
</script>

<script lang="ts" generics="Item extends { id: string }">
	/**
	 * the results surface autocomplete-type search shares: the box, its sections,
	 * and the one navigation contract (arrow keys walk the flattened run, enter
	 * takes the highlighted row, escape closes). rows stay the caller's markup -
	 * a suggestion, a resource widget and a conversation row look nothing alike -
	 * so the box owns the chrome and the state machine, nothing else.
	 */

	import type { Snippet } from 'svelte'

	interface Props {
		/** the query these rows answer; a new one re-opens the box and drops the highlight. */
		query: string
		sections: readonly SearchResultsSection<Item>[]
		/** the caller's own gate (mode is active, results exist); the box adds its dismissal. */
		open?: boolean
		listLabel?: string
		/** rows are options of a listbox by default; a run of list items opts out. */
		listRole?: 'listbox' | 'list'
		onSelect: (item: Item) => void
		/** escape, after the box closed itself - where the caller drops the query. */
		onDismiss?: () => void
		onKeyHandler?: (handler: SearchResultsKeyHandler) => void
		row: Snippet<[Item, SearchResultsRow]>
		/** trailing row outside the sections (home's "search more in-depth"). */
		footer?: Snippet<[() => void]>
		class?: string
	}

	let {
		query,
		sections,
		open = true,
		listLabel = 'results',
		listRole = 'listbox',
		onSelect,
		onDismiss,
		onKeyHandler,
		row,
		footer,
		class: className = '',
	}: Props = $props()

	let highlightedIndex = $state(-1)
	let navigationActive = $state(false)
	let dismissed = $state(false)

	const entries = $derived(sections.flatMap((section) => [...section.items]))
	const order = $derived(new Map(entries.map((entry, index) => [entry.id, index])))
	const isOpen = $derived(open && !dismissed && entries.length > 0)

	// a new query is a new list: nothing is highlighted, and an escape is forgotten.
	$effect(() => {
		void query
		highlightedIndex = -1
		navigationActive = false
		dismissed = false
	})

	function close(): void {
		dismissed = true
		highlightedIndex = -1
		navigationActive = false
	}

	function select(item: Item): void {
		close()
		onSelect(item)
	}

	function rowState(item: Item): SearchResultsRow {
		const index = order.get(item.id) ?? -1
		return {
			highlighted: index >= 0 && index === highlightedIndex,
			select: () => select(item),
			hover: () => {
				highlightedIndex = index
				navigationActive = true
			},
		}
	}

	function handleKeyDown(event: KeyboardEvent): boolean {
		if (!isOpen) return false
		if (event.key === 'ArrowDown') {
			event.preventDefault()
			navigationActive = true
			highlightedIndex = highlightedIndex < 0 ? 0 : (highlightedIndex + 1) % entries.length
			return true
		}
		if (event.key === 'ArrowUp') {
			event.preventDefault()
			navigationActive = true
			highlightedIndex =
				highlightedIndex < 0
					? entries.length - 1
					: (highlightedIndex - 1 + entries.length) % entries.length
			return true
		}
		if (event.key === 'Escape') {
			event.preventDefault()
			close()
			onDismiss?.()
			return true
		}
		if (event.key === 'Enter' && !event.shiftKey) {
			// enter only belongs to the box once the user has walked into it;
			// otherwise it is still the input's own submit.
			if (!navigationActive || highlightedIndex < 0) return false
			event.preventDefault()
			const item = entries[highlightedIndex]
			if (!item) return true
			select(item)
			return true
		}
		return false
	}

	$effect(() => {
		onKeyHandler?.(handleKeyDown)
	})
</script>

{#if isOpen}
	<div
		class="liquid-glass liquid-glass--clip rounded-container isolate flex min-h-0 flex-col overflow-hidden [--lg-bg:color-mix(in_oklch,var(--background)_18%,transparent)] [--lg-blur:8px] dark:[--lg-bg:color-mix(in_oklch,var(--background)_42%,transparent)] {className}"
		data-search-results
	>
		<div class="relative z-10 flex min-h-0 flex-col">
			<div
				class="no-scrollbar min-h-0 overflow-y-auto p-2"
				role={listRole}
				aria-label={listLabel}
			>
				{#each sections as section (section.id)}
					{#if section.label}
						<h3
							class="text-foreground/45 mt-2 px-3 pb-1 text-xs font-medium first:mt-0"
							data-section-label
						>
							{section.label}
						</h3>
					{/if}
					<div
						class="flex flex-col gap-0 overflow-hidden rounded-[calc(var(--radius-container)-0.5rem)]"
					>
						{#each section.items as item (item.id)}
							{@render row(item, rowState(item))}
						{/each}
					</div>
				{/each}
				{#if footer}
					<div class="border-foreground/8 mt-2 border-t pt-2">
						{@render footer(close)}
					</div>
				{/if}
			</div>
		</div>
	</div>
{/if}
