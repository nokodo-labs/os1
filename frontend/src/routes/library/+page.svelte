<script lang="ts">
	import { browser } from '$app/environment'
	import AdjustmentsHorizontal from '$lib/components/icons/AdjustmentsHorizontal.svelte'
	import ArrowsUpDown from '$lib/components/icons/ArrowsUpDown.svelte'
	import { useSystemChrome } from '$lib/contexts/systemChromeContext.svelte'
	import { accentStore } from '$lib/stores/accent.svelte'
	import { pageTitleStore } from '$lib/stores/pageTitle.svelte'
	import { scale } from 'svelte/transition'

	type FilterMode = 'all' | 'sent' | 'received' | 'created'
	type SortMode = 'newest' | 'oldest'

	const chrome = useSystemChrome()

	let filter = $state<FilterMode>('all')
	let sort = $state<SortMode>('newest')

	let isFilterMenuOpen = $state(false)
	let isSortMenuOpen = $state(false)

	let filterMenuEl: HTMLDivElement | null = $state(null)
	let filterButtonEl: HTMLButtonElement | null = $state(null)
	let sortMenuEl: HTMLDivElement | null = $state(null)
	let sortButtonEl: HTMLButtonElement | null = $state(null)

	function closeMenus() {
		isFilterMenuOpen = false
		isSortMenuOpen = false
		filterMenuEl = null
		sortMenuEl = null
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

	$effect(() => {
		if (!browser) return
		if (!isFilterMenuOpen && !isSortMenuOpen) return

		const onKeyDown = (event: KeyboardEvent) => {
			if (event.key !== 'Escape') return
			event.preventDefault()
			closeMenus()
		}

		const onPointerDown = (event: PointerEvent) => {
			const path = event.composedPath()
			if (filterMenuEl && path.includes(filterMenuEl)) return
			if (filterButtonEl && path.includes(filterButtonEl)) return
			if (sortMenuEl && path.includes(sortMenuEl)) return
			if (sortButtonEl && path.includes(sortButtonEl)) return
			closeMenus()
		}

		window.addEventListener('keydown', onKeyDown)
		window.addEventListener('pointerdown', onPointerDown)
		return () => {
			window.removeEventListener('keydown', onKeyDown)
			window.removeEventListener('pointerdown', onPointerDown)
		}
	})
</script>

{#snippet islandContextActions()}
	<div class="relative flex items-center gap-1">
		<div class="relative">
			<button
				type="button"
				bind:this={filterButtonEl}
				class="group rounded-pill flex h-12 w-12 cursor-pointer items-center justify-center border-none bg-transparent opacity-80 transition-all duration-150 hover:scale-[1.05] hover:opacity-100 active:scale-[0.97]"
				onclick={toggleFilterMenu}
				aria-label="filter"
				aria-haspopup="menu"
				aria-expanded={isFilterMenuOpen}
			>
				<AdjustmentsHorizontal class="h-5 w-5" />
			</button>

			{#if isFilterMenuOpen}
				<div
					transition:scale={{ duration: 160, start: 0.96, opacity: 0 }}
					bind:this={filterMenuEl}
					role="menu"
					class="animate-popup-right rounded-box absolute top-full left-0 z-50 mt-2 w-44 border border-white/10 bg-black/70 p-2 shadow-[0_24px_48px_rgba(12,10,30,0.55)] backdrop-blur"
				>
					{#each ['all', 'sent', 'received', 'created'] as FilterMode[] as option}
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
				</div>
			{/if}
		</div>

		<div class="relative">
			<button
				type="button"
				bind:this={sortButtonEl}
				class="group rounded-pill flex h-12 w-12 cursor-pointer items-center justify-center border-none bg-transparent opacity-80 transition-all duration-150 hover:scale-[1.05] hover:opacity-100 active:scale-[0.97]"
				onclick={toggleSortMenu}
				aria-label="sort"
				aria-haspopup="menu"
				aria-expanded={isSortMenuOpen}
			>
				<ArrowsUpDown variant="solid" class="h-5 w-5" />
			</button>

			{#if isSortMenuOpen}
				<div
					transition:scale={{ duration: 160, start: 0.96, opacity: 0 }}
					bind:this={sortMenuEl}
					role="menu"
					class="animate-popup-right rounded-box absolute top-full left-0 z-50 mt-2 w-44 border border-white/10 bg-black/70 p-2 shadow-[0_24px_48px_rgba(12,10,30,0.55)] backdrop-blur"
				>
					{#each ['newest', 'oldest'] as SortMode[] as option}
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
				</div>
			{/if}
		</div>
	</div>
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
