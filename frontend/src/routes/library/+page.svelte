<script lang="ts">
	import ArrowsUpDown from '$lib/components/icons/ArrowsUpDown.svelte'
	import ArrowUpTray from '$lib/components/icons/ArrowUpTray.svelte'
	import Clip from '$lib/components/icons/Clip.svelte'
	import PageTitle from '$lib/components/PageTitle.svelte'
	import { PopupMenu } from '$lib/components/primitives'
	import ResourcesView from '$lib/components/ResourcesView.svelte'
	import type {
		ResourceItem,
		ResourceLayoutMode,
		ResourceSortMode,
	} from '$lib/components/widgets'
	import { useSystemChrome } from '$lib/contexts/systemChromeContext.svelte'
	import { accentStore } from '$lib/stores/accent.svelte'
	import { files } from '$lib/stores/files.svelte'
	import { modals } from '$lib/stores/modals.svelte'
	import { pageTitleStore } from '$lib/stores/pageTitle.svelte'

	const chrome = useSystemChrome()

	let sort = $state<ResourceSortMode>('updated_at:desc')
	let layout = $state<ResourceLayoutMode>('grid')

	let isSortMenuOpen = $state(false)
	let sortButtonEl: HTMLButtonElement | null = $state(null)
	let fileInputEl: HTMLInputElement | null = $state(null)
	let isUploading = $state(false)

	function closeSortMenu() {
		isSortMenuOpen = false
	}

	function toggleSortMenu() {
		isSortMenuOpen = !isSortMenuOpen
	}

	function triggerUpload() {
		fileInputEl?.click()
	}

	async function handleFileSelected(e: Event) {
		const input = e.target as HTMLInputElement
		const file = input.files?.[0]
		if (!file) return
		isUploading = true
		try {
			await files.upload(file)
		} finally {
			isUploading = false
			input.value = ''
		}
	}

	const resourceItems = $derived.by((): ResourceItem[] => {
		const [field, dir] = sort.split(':') as [string, 'asc' | 'desc']
		const sorted = [...files.resources]
		sorted.sort((a, b) => {
			let cmp = 0
			if (field === 'title') {
				cmp = a.title.localeCompare(b.title)
			} else if (field === 'created_at') {
				cmp = a.createdAt - b.createdAt
			} else {
				cmp = a.updatedAt - b.updatedAt
			}
			return dir === 'desc' ? -cmp : cmp
		})
		return sorted
	})

	$effect(() => {
		void files.load()
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
		class="group rounded-pill flex cursor-pointer items-center justify-center border-none bg-transparent opacity-80 transition-all duration-150 hover:scale-[1.05] hover:opacity-100 active:scale-[0.97] disabled:cursor-wait disabled:opacity-50"
		onclick={triggerUpload}
		disabled={isUploading}
		aria-label="upload file"
	>
		<ArrowUpTray />
	</button>
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
				class="rounded-pill text-foreground/80 hover:bg-foreground/10 flex w-full cursor-pointer items-center border-none bg-transparent px-3 py-2 text-left text-sm transition-colors duration-150"
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
		<p class="text-foreground/60 mt-2 text-sm">
			all your uploaded, created and shared files in one place
		</p>
	</div>

	<input
		bind:this={fileInputEl}
		type="file"
		class="hidden"
		onchange={handleFileSelected}
		aria-hidden="true"
	/>

	<ResourcesView
		resources={resourceItems}
		loading={files.loading}
		bind:layout
		filter="files"
		{sort}
		emptyMessage="no files yet - upload files to see them here"
		pageSize={50}
		onLoadMore={() => files.loadMore()}
		hasMore={files.hasMore}
		loadingMore={files.loadingMore}
		onItemClick={(item) => modals.open('file-details', { fileId: item.id })}
	/>
</div>
