<script lang="ts">
	import Search from '$lib/components/icons/Search.svelte'
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
				class="pointer-events-none absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 text-white/40"
			/>
			<input
				type="text"
				class="rounded-pill w-full border border-white/10 bg-white/5 py-2 pr-3 pl-9 text-sm text-white/90 placeholder-white/40 transition-colors outline-none focus:border-white/20 focus:bg-white/8"
				placeholder={searchPlaceholder}
				value={search}
				oninput={(e) => onSearchInput(e.currentTarget.value)}
			/>
		</div>
		<select
			class="rounded-pill border border-white/10 bg-white/5 px-3 py-2 text-sm text-white/70 transition-colors outline-none focus:border-white/20 [&>option]:bg-neutral-900 [&>option]:text-white/90"
			value={sortIndex}
			onchange={(e) => onSortChange(Number(e.currentTarget.value))}
		>
			{#each sortOptions as opt, i (opt.value)}
				<option value={i}>{opt.label}</option>
			{/each}
		</select>
	</div>

	<!-- scrollable list container -->
	<div class="max-h-80 min-h-40 overflow-y-auto" onscroll={onScroll}>
		{#if loading}
			<div class="flex items-center justify-center py-12">
				<div
					class="h-5 w-5 animate-spin rounded-full border-2 border-white/20 border-t-white/60"
				></div>
			</div>
		{:else if isEmpty}
			<div class="rounded-container border border-white/8 bg-white/3 p-6">
				<p class="text-center text-sm text-white/40">
					{search ? (emptySearchMessage ?? emptyMessage) : emptyMessage}
				</p>
			</div>
		{:else}
			<div class="space-y-2">
				{@render items()}

				{#if loadingMore}
					<div class="flex items-center justify-center py-3">
						<div
							class="h-4 w-4 animate-spin rounded-full border-2 border-white/20 border-t-white/60"
						></div>
					</div>
				{/if}
			</div>
		{/if}
	</div>

	<!-- footer -->
	<div class="flex items-center justify-between border-t border-white/10 pt-3">
		<span class="text-xs text-white/40">
			{@render footerLeft?.()}
		</span>
		<div class="flex items-center gap-2">
			{@render footerRight?.()}
		</div>
	</div>
</div>
