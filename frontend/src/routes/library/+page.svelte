<script lang="ts">
	import PageTitle from '$lib/components/PageTitle.svelte'
	import ArrowsUpDown from '$lib/components/icons/ArrowsUpDown.svelte'
	import Clip from '$lib/components/icons/Clip.svelte'
	import { PopupMenu } from '$lib/components/primitives'
	import ResourcesView from '$lib/components/ResourcesView.svelte'
	import type {
		ResourceItem,
		ResourceLayoutMode,
		ResourceSortMode,
	} from '$lib/components/widgets'
	import { useSystemChrome } from '$lib/contexts/systemChromeContext.svelte'
	import { accentStore } from '$lib/stores/accent.svelte'
	import { pageTitleStore } from '$lib/stores/pageTitle.svelte'

	const chrome = useSystemChrome()

	let sort = $state<ResourceSortMode>('updated_at:desc')
	let layout = $state<ResourceLayoutMode>('grid')
	let loading = $state(true)

	let isSortMenuOpen = $state(false)
	let sortButtonEl: HTMLButtonElement | null = $state(null)

	function closeSortMenu() {
		isSortMenuOpen = false
	}

	function toggleSortMenu() {
		isSortMenuOpen = !isSortMenuOpen
	}

	// TODO: load files from a files store once available
	const resourceItems = $derived.by((): ResourceItem[] => {
		return []
	})

	async function loadFiles() {
		loading = true
		// TODO: await files.load() once the files store is implemented
		loading = false
	}

	$effect(() => {
		void loadFiles()
	})

	$effect(() => {
		pageTitleStore.pageTitle = 'files'
	})

	$effect(() => {
		accentStore.set('blue')
	})

	$effect(() => {
		chrome.setContextActions(islandContextActions)
		return () => chrome.setContextActions(null)
	})

	const sortOptions: { value: ResourceSortMode; label: string }[] = [
		{ value: 'updated_at:desc', label: 'last updated' },
		{ value: 'updated_at:asc', label: 'first updated' },
		{ value: 'created_at:desc', label: 'newest' },
		{ value: 'created_at:asc', label: 'oldest' },
		{ value: 'title:asc', label: 'name a-z' },
		{ value: 'title:desc', label: 'name z-a' },
	]
</script>

{#snippet islandContextActions()}
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
	<PopupMenu open={isSortMenuOpen} anchorEl={sortButtonEl} onClose={closeSortMenu}>
		{#each sortOptions as option (option.value)}
			<button
				type="button"
				role="menuitem"
				class="rounded-pill flex w-full cursor-pointer items-center border-none bg-transparent px-3 py-2 text-left text-sm text-white/80 transition-colors duration-150 hover:bg-white/10"
				onclick={() => {
					sort = option.value
					closeSortMenu()
				}}
			>
				{option.label}{sort === option.value ? ' \u2713' : ''}
			</button>
		{/each}
	</PopupMenu>
{/snippet}

<div
	class="flex flex-col gap-6 pb-10"
	style="padding-left: var(--spacing-page-x); padding-right: var(--spacing-page-x);"
>
	<div>
		<PageTitle icon={Clip} label="files" />
		<p class="mt-2 text-sm text-white/60">
			all your uploaded, created and shared files in one place
		</p>
	</div>

	<ResourcesView
		resources={resourceItems}
		{loading}
		bind:layout
		filter="files"
		{sort}
		emptyMessage="no files yet - upload files to see them here"
		pageSize={24}
	/>
</div>
