<script lang="ts">
	import EmptyState from '$lib/components/EmptyState.svelte'
	import Search from '$lib/components/icons/Search.svelte'
	import SortIcon from '$lib/components/icons/SortIcon.svelte'
	import LoadingMoreIndicator from '$lib/components/LoadingMoreIndicator.svelte'
	import NokodoLoader from '$lib/components/NokodoLoader.svelte'
	import { DropdownSelect } from '$lib/components/primitives'
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
		loadMoreThreshold?: number
		items: Snippet
		footerLeft?: Snippet
		footerRight?: Snippet
	}

	let {
		search,
		searchPlaceholder = 'search',
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
		loadMoreThreshold = 400,
		items,
		footerLeft,
		footerRight,
	}: ModalListLayoutProps = $props()

	let scrollerEl: HTMLDivElement | null = $state(null)
	const sortSelectOptions = $derived(
		sortOptions.map((option, index) => ({ value: String(index), label: option.label }))
	)

	function maybeLoadMore(el: HTMLDivElement | null): void {
		if (!el || loading || loadingMore || !hasMore || isEmpty) return
		if (el.scrollHeight - el.scrollTop - el.clientHeight <= loadMoreThreshold) {
			onLoadMore()
		}
	}

	function onScroll(e: Event): void {
		maybeLoadMore(e.currentTarget as HTMLDivElement)
	}

	$effect(() => {
		if (!scrollerEl || loading || loadingMore || !hasMore || isEmpty) return
		const frame = requestAnimationFrame(() => maybeLoadMore(scrollerEl))
		return () => cancelAnimationFrame(frame)
	})
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
				class="text-foreground/45 pointer-events-none absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2"
			/>
			<DropdownSelect
				options={sortSelectOptions}
				value={String(sortIndex)}
				onchange={(value) => onSortChange(Number(value))}
				ariaLabel="sort list"
				class="min-w-40"
				buttonClass="py-2 pl-9 text-foreground/70"
			/>
		</div>
	</div>

	<!-- scrollable list container -->
	<div bind:this={scrollerEl} class="max-h-[68dvh] min-h-40 overflow-y-auto" onscroll={onScroll}>
		{#if loading}
			<div class="flex min-h-40 items-center justify-center py-12">
				<NokodoLoader className="opacity-70" expanded={false} />
			</div>
		{:else if isEmpty}
			<EmptyState label={search ? (emptySearchMessage ?? emptyMessage) : emptyMessage} />
		{:else}
			<div class="space-y-2">
				{@render items()}

				{#if loadingMore}
					<LoadingMoreIndicator className="py-3" />
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
