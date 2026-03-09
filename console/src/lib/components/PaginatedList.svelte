<script lang="ts" module>
	export type SortOption<K extends string = string> = {
		value: K
		label: string
	}

	export type PaginationState = {
		pageIndex: number
		limit: number
		hasNext: boolean
	}
</script>

<script lang="ts" generics="T, SortKey extends string = string">
	import { browser } from '$app/environment'
	import { page } from '$app/state'
	import NokodoLoader from '$lib/components/NokodoLoader.svelte'
	import { Button } from '$lib/components/ui/button'
	import {
		Card,
		CardContent,
		CardDescription,
		CardHeader,
		CardTitle,
	} from '$lib/components/ui/card'
	import { Select, SelectContent, SelectItem, SelectTrigger } from '$lib/components/ui/select'
	import type { Snippet } from 'svelte'
	import { SvelteURLSearchParams } from 'svelte/reactivity'

	type Props = {
		title: string
		description: string
		sortOptions?: SortOption<SortKey>[]
		defaultSort?: SortKey
		sortParam?: string
		filterKey?: string
		filterParam?: string
		filterLabel?: string
		items: T[]
		isLoading: boolean
		hasNext: boolean
		error?: string | null
		pageIndex: number
		onPageChange: (newPage: number) => void
		onSortChange?: (sort: SortKey) => void
		onFilterClear?: () => void
		onRefresh: () => void
		headerActions?: Snippet
		itemTemplate: Snippet<[T]>
		emptyMessage?: string
	}

	let {
		title,
		description,
		sortOptions = [],
		defaultSort,
		sortParam = 'sort',
		filterKey,
		filterParam,
		filterLabel = 'filter',
		items,
		isLoading,
		hasNext,
		error = null,
		pageIndex,
		onPageChange,
		onSortChange,
		onFilterClear,
		onRefresh,
		headerActions,
		itemTemplate,
		emptyMessage = 'no items found',
	}: Props = $props()

	let sortKey = $state<SortKey | undefined>(undefined)
	let filterValue = $state<string | null>(null)

	function replaceUrl(target: string) {
		if (!browser) return
		history.replaceState(history.state, '', target)
	}

	function updateQueryParams(updates: Record<string, string | null>) {
		if (!browser) return
		const url = page.url
		const params = new SvelteURLSearchParams(url.searchParams)
		for (const [key, value] of Object.entries(updates)) {
			if (!value) params.delete(key)
			else params.set(key, value)
		}
		const qs = params.toString()
		replaceUrl(qs ? `${url.pathname}?${qs}` : url.pathname)
	}

	function setSort(next: SortKey) {
		sortKey = next
		onPageChange(0)
		updateQueryParams({ [sortParam]: next })
		onSortChange?.(next)
	}

	function clearFilter() {
		filterValue = null
		onPageChange(0)
		if (filterParam) updateQueryParams({ [filterParam]: null })
		onFilterClear?.()
	}

	$effect(() => {
		if (!browser) return

		const sp = page.url.searchParams
		const sort = sp.get(sortParam)
		const nextSort =
			sort && sortOptions.some((o) => o.value === sort) ? (sort as SortKey) : defaultSort

		if (filterParam) {
			const filter = sp.get(filterParam)
			filterValue = filter?.trim() ? filter : null
		}

		if (sortKey !== nextSort) {
			sortKey = nextSort
		}
	})
</script>

<div class="flex min-h-0 flex-1 flex-col gap-6">
	<div class="flex shrink-0 flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
		<div>
			<h2 class="text-2xl font-bold tracking-tight">{title}</h2>
			<p class="text-zinc-400">{description}</p>
		</div>
		<div class="flex flex-wrap items-center gap-2">
			{#if headerActions}
				{@render headerActions()}
			{/if}
			{#if sortOptions.length > 0 && sortKey}
				<Select value={sortKey} onValueChange={(v: string) => setSort(v as SortKey)}>
					<SelectTrigger class="w-56 rounded-xl">
						<span class="truncate text-left">
							{sortOptions.find((o) => o.value === sortKey)?.label ?? sortKey}
						</span>
					</SelectTrigger>
					<SelectContent>
						{#each sortOptions as opt (opt.value)}
							<SelectItem value={opt.value}>{opt.label}</SelectItem>
						{/each}
					</SelectContent>
				</Select>
			{/if}
			{#if filterKey && filterValue}
				<Button
					variant="outline"
					class="rounded-xl"
					onclick={() => clearFilter()}
					disabled={isLoading}
				>
					{filterLabel}: {filterValue} · clear
				</Button>
			{/if}
			<Button
				variant="outline"
				class="rounded-xl"
				onclick={() => onRefresh()}
				disabled={isLoading}
			>
				{isLoading ? 'loading...' : 'refresh'}
			</Button>
		</div>
	</div>

	{#if error}
		<div
			class="shrink-0 rounded-2xl border border-red-900/50 bg-red-900/10 p-4 text-sm text-red-200"
		>
			{error}
		</div>
	{/if}

	<Card
		class="flex min-h-0 flex-1 flex-col rounded-2xl border-zinc-800 bg-zinc-900 text-zinc-100"
	>
		<CardHeader
			class="flex shrink-0 flex-col gap-3 sm:flex-row sm:items-center sm:justify-between"
		>
			<div>
				<CardTitle>list</CardTitle>
				<CardDescription>
					page {pageIndex + 1} · showing {items.length}{hasNext ? '+' : ''}
				</CardDescription>
			</div>
			<div class="flex items-center gap-2">
				<Button
					variant="outline"
					class="rounded-xl"
					onclick={() => onPageChange(Math.max(0, pageIndex - 1))}
					disabled={pageIndex === 0 || isLoading}
				>
					prev
				</Button>
				<Button
					variant="outline"
					class="rounded-xl"
					onclick={() => onPageChange(pageIndex + 1)}
					disabled={!hasNext || isLoading}
				>
					next
				</Button>
			</div>
		</CardHeader>
		<CardContent class="min-h-0 flex-1 space-y-2 overflow-y-auto">
			{#if isLoading && items.length === 0}
				<div
					class="flex items-center justify-center rounded-xl border border-zinc-800 bg-zinc-950 p-10"
				>
					<NokodoLoader />
				</div>
			{/if}

			{#if items.length === 0 && !isLoading}
				<div
					class="rounded-xl border border-dashed border-zinc-800 p-10 text-center text-sm text-zinc-500"
				>
					{emptyMessage}
				</div>
			{/if}

			{#each items as item (item)}
				{@render itemTemplate(item)}
			{/each}
		</CardContent>
	</Card>
</div>
