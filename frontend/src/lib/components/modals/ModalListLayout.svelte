<script lang="ts">
	import ChevronDown from '$lib/components/icons/ChevronDown.svelte'
	import Search from '$lib/components/icons/Search.svelte'
	import SortIcon from '$lib/components/icons/SortIcon.svelte'
	import type { Snippet } from 'svelte'

	type SortOption = {
		label: string
		value: string
	}

	interface ModalListLayoutProps {
		search: string
		searchPlaceholder?: string
		sortOptions: readonly SortOption[]
		sortIndex: number
		loading: boolean
		loadingMore: boolean
		hasMore: boolean
		isEmpty: boolean
		emptyMessage: string
		emptySearchMessage?: string
		onSearchInput: (value: string) => void
		onSortChange: (index: number) => void
		onLoadMore: () => void
		items: Snippet
		footerLeft?: Snippet
		footerRight?: Snippet
	}

	let {
		search,
		searchPlaceholder = 'search...',
		sortOptions,
		sortIndex,
		loading,
		loadingMore,
		hasMore,
		isEmpty,
		emptyMessage,
		emptySearchMessage,
		onSearchInput,
		onSortChange,
		onLoadMore,
		items,
		footerLeft,
		footerRight,
	}: ModalListLayoutProps = $props()

	const SCROLL_THRESHOLD = 100
	const selectedSortValue = $derived(
		sortOptions.find((_option, index) => index === sortIndex)?.value
	)

	function onScroll(e: Event): void {
		const el = e.currentTarget as HTMLDivElement
		if (!el || loadingMore || !hasMore) return
		if (el.scrollHeight - el.scrollTop - el.clientHeight < SCROLL_THRESHOLD) {
			onLoadMore()
		}
	}
</script>

<div class="flex flex-col gap-3">
	<!-- toolbar: search + sort -->
	<div class="flex items-center gap-2">
		<div class="relative flex-1">
			<Search
				class="text-foreground/40 pointer-events-none absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2"
			/>
			<input
				type="text"
				class="rounded-pill border-foreground/10 bg-foreground/5 text-foreground/90 placeholder:text-foreground/40 focus:border-foreground/20 focus:bg-foreground/8 w-full border py-2 pr-3 pl-9 text-sm transition-colors outline-none"
				placeholder={searchPlaceholder}
				value={search}
				oninput={(e) => onSearchInput(e.currentTarget.value)}
			/>
		</div>
		<div class="relative shrink-0">
			<SortIcon
				value={selectedSortValue}
				class="text-foreground/45 pointer-events-none absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2"
			/>
			<select
				class="rounded-pill border-foreground/10 bg-foreground/5 text-foreground/70 focus:border-foreground/20 [&>option]:text-foreground/90 min-w-40 appearance-none border py-2 pr-8 pl-9 text-sm transition-colors outline-none [&>option]:bg-neutral-900"
				value={sortIndex}
				onchange={(e) => onSortChange(Number(e.currentTarget.value))}
			>
				{#each sortOptions as opt, i (opt.value)}
					<option value={i}>{opt.label}</option>
				{/each}
			</select>
			<ChevronDown
				class="text-foreground/45 pointer-events-none absolute top-1/2 right-3 h-4 w-4 -translate-y-1/2"
			/>
		</div>
	</div>

	<!-- scrollable list container -->
	<div class="max-h-80 min-h-40 overflow-y-auto" onscroll={onScroll}>
		{#if loading}
			<div class="flex items-center justify-center py-12">
				<div
					class="border-foreground/20 h-5 w-5 animate-spin rounded-full border-2 border-t-white/60"
				></div>
			</div>
		{:else if isEmpty}
			<div class="flex min-h-40 items-center justify-center">
				<p class="text-foreground/40 text-center text-sm">
					{search ? (emptySearchMessage ?? emptyMessage) : emptyMessage}
				</p>
			</div>
		{:else}
			<div class="space-y-2">
				{@render items()}

				{#if loadingMore}
					<div class="flex items-center justify-center py-3">
						<div
							class="border-foreground/20 h-4 w-4 animate-spin rounded-full border-2 border-t-white/60"
						></div>
					</div>
				{/if}
			</div>
		{/if}
	</div>

	<!-- footer -->
	<div class="border-foreground/10 flex items-center justify-between border-t pt-3">
		<span class="text-foreground/40 text-xs">
			{@render footerLeft?.()}
		</span>
		<div class="flex items-center gap-2">
			{@render footerRight?.()}
		</div>
	</div>
</div>
