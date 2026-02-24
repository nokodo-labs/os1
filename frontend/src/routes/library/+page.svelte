<script lang="ts">
	import AdjustmentsHorizontal from '$lib/components/icons/AdjustmentsHorizontal.svelte'
	import ArrowsUpDown from '$lib/components/icons/ArrowsUpDown.svelte'
	import { PopupMenu } from '$lib/components/primitives'
	import { useSystemChrome } from '$lib/contexts/systemChromeContext.svelte'
	import { accentStore } from '$lib/stores/accent.svelte'
	import { pageTitleStore } from '$lib/stores/pageTitle.svelte'

	type FilterMode = 'all' | 'sent' | 'received' | 'created'
	type SortMode = 'newest' | 'oldest'

	const chrome = useSystemChrome()

	let filter = $state<FilterMode>('all')
	let sort = $state<SortMode>('newest')

	let isFilterMenuOpen = $state(false)
	let isSortMenuOpen = $state(false)

	let filterButtonEl: HTMLButtonElement | null = $state(null)
	let sortButtonEl: HTMLButtonElement | null = $state(null)

	function closeMenus() {
		isFilterMenuOpen = false
		isSortMenuOpen = false
	}

	function toggleFilterMenu() {
		isFilterMenuOpen = !isFilterMenuOpen
		if (isFilterMenuOpen) isSortMenuOpen = false
	}

	function toggleSortMenu() {
		isSortMenuOpen = !isSortMenuOpen
		if (isSortMenuOpen) isFilterMenuOpen = false
	}

	$effect(() => {
		pageTitleStore.pageTitle = 'library'
	})

	$effect(() => {
		accentStore.set('yellow')
	})

	// inject library controls into the Island
	$effect(() => {
		chrome.setContextActions(islandContextActions)
		return () => chrome.setContextActions(null)
	})
</script>

{#snippet islandContextActions()}
	<button
		type="button"
		bind:this={filterButtonEl}
		class="group rounded-pill flex cursor-pointer items-center justify-center border-none bg-transparent opacity-80 transition-all duration-150 hover:scale-[1.05] hover:opacity-100 active:scale-[0.97]"
		onclick={toggleFilterMenu}
		aria-label="filter"
		aria-haspopup="menu"
		aria-expanded={isFilterMenuOpen}
	>
		<AdjustmentsHorizontal />
	</button>
	<PopupMenu open={isFilterMenuOpen} anchorEl={filterButtonEl} onClose={closeMenus}>
		{#each ['all', 'sent', 'received', 'created'] as FilterMode[] as option (option)}
			<button
				type="button"
				role="menuitem"
				class="rounded-pill flex w-full cursor-pointer items-center border-none bg-transparent px-3 py-2 text-left text-sm text-white/80 transition-colors duration-150 hover:bg-white/10"
				onclick={() => {
					filter = option
					closeMenus()
				}}
			>
				{option}{filter === option ? ' ✓' : ''}
			</button>
		{/each}
	</PopupMenu>

	<button
		type="button"
		bind:this={sortButtonEl}
		class="group rounded-pill flex cursor-pointer items-center justify-center border-none bg-transparent opacity-80 transition-all duration-150 hover:scale-[1.05] hover:opacity-100 active:scale-[0.97]"
		onclick={toggleSortMenu}
		aria-label="sort"
		aria-haspopup="menu"
		aria-expanded={isSortMenuOpen}
	>
		<ArrowsUpDown variant="solid" />
	</button>
	<PopupMenu open={isSortMenuOpen} anchorEl={sortButtonEl} onClose={closeMenus}>
		{#each ['newest', 'oldest'] as SortMode[] as option (option)}
			<button
				type="button"
				role="menuitem"
				class="rounded-pill flex w-full cursor-pointer items-center border-none bg-transparent px-3 py-2 text-left text-sm text-white/80 transition-colors duration-150 hover:bg-white/10"
				onclick={() => {
					sort = option
					closeMenus()
				}}
			>
				{option}{sort === option ? ' ✓' : ''}
			</button>
		{/each}
	</PopupMenu>
{/snippet}

<div class="mx-auto mt-10 max-w-3xl">
	<h1 class="text-2xl font-semibold text-white/90">library</h1>
	<p class="mt-2 text-sm text-white/60">
		all sent and received media, artifacts, and files will live here.
	</p>

	<div
		class="rounded-container mt-6 border border-white/10 bg-white/5 p-5 text-center text-sm text-white/70"
	>
		coming soon
	</div>
</div>
