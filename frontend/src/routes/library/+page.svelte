<script lang="ts">
	import { api } from '$lib/api/client'
	import ArrowUpTray from '$lib/components/icons/ArrowUpTray.svelte'
	import Clip from '$lib/components/icons/Clip.svelte'
	import Document from '$lib/components/icons/Document.svelte'
	import DocumentArrowDown from '$lib/components/icons/DocumentArrowDown.svelte'
	import Film from '$lib/components/icons/Film.svelte'
	import Funnel from '$lib/components/icons/Funnel.svelte'
	import Headphone from '$lib/components/icons/Headphone.svelte'
	import Photo from '$lib/components/icons/Photo.svelte'
	import SortIcon from '$lib/components/icons/SortIcon.svelte'
	import Sparkles from '$lib/components/icons/Sparkles.svelte'
	import XMark from '$lib/components/icons/XMark.svelte'
	import PageTitle from '$lib/components/PageTitle.svelte'
	import { MenuItem, PopupMenu } from '$lib/components/primitives'
	import ResourcesView from '$lib/components/ResourcesView.svelte'
	import type {
		ResourceItem,
		ResourceLayoutMode,
		ResourceSortMode,
	} from '$lib/components/widgets'
	import { useSystemChrome } from '$lib/contexts/systemChromeContext.svelte'
	import { accentStore } from '$lib/stores/accent.svelte'
	import { files, type FileCategoryFilter, type FileSourceFilter } from '$lib/stores/files.svelte'
	import { modals } from '$lib/stores/modals.svelte'
	import { pageTitleStore } from '$lib/stores/pageTitle.svelte'
	import { projects } from '$lib/stores/projects.svelte'
	import { canEditAccessLevel, resourceAccess } from '$lib/stores/resourceAccess.svelte'
	import { session } from '$lib/stores/session.svelte'

	const chrome = useSystemChrome()

	let sort = $state<ResourceSortMode>('updated_at:desc')
	let layout = $state<ResourceLayoutMode>('grid')
	let categoryFilter = $state<'all' | FileCategoryFilter>('all')
	let sourceFilter = $state<'all' | FileSourceFilter>('all')

	let isFilterMenuOpen = $state(false)
	let isSortMenuOpen = $state(false)
	let filterButtonEl: HTMLButtonElement | null = $state(null)
	let sortButtonEl: HTMLButtonElement | null = $state(null)
	let fileInputEl: HTMLInputElement | null = $state(null)
	let isUploading = $state(false)
	const currentUserId = $derived(session.currentUserId)
	const activeCategory = $derived(categoryFilter === 'all' ? null : categoryFilter)
	const activeSource = $derived(sourceFilter === 'all' ? null : sourceFilter)
	const activeFilterCount = $derived(
		(categoryFilter === 'all' ? 0 : 1) + (sourceFilter === 'all' ? 0 : 1)
	)
	const fileCounts = $derived(files.counts)
	const activeFileCounts = $derived(
		files.getCounts({ category: activeCategory, source: activeSource })
	)
	const totalFileCount = $derived(fileCounts.total ?? 0)
	const ownedFileCount = $derived(activeFileCounts.owned_total ?? 0)
	const sharedFileCount = $derived(activeFileCounts.shared_total ?? 0)
	const categoryOptions = $derived([
		{ value: 'all' as const, label: 'all', count: totalFileCount, icon: Funnel },
		{
			value: 'image' as const,
			label: 'images',
			count: fileCounts.by_category?.image ?? 0,
			icon: Photo,
		},
		{
			value: 'audio' as const,
			label: 'audio',
			count: fileCounts.by_category?.audio ?? 0,
			icon: Headphone,
		},
		{
			value: 'video' as const,
			label: 'video',
			count: fileCounts.by_category?.video ?? 0,
			icon: Film,
		},
		{
			value: 'file' as const,
			label: 'files',
			count: fileCounts.by_category?.file ?? 0,
			icon: Document,
		},
	])
	const sourceOptions = $derived([
		{ value: 'all' as const, label: 'all sources', count: totalFileCount, icon: Clip },
		{
			value: 'upload' as const,
			label: 'uploads',
			count: fileCounts.by_source?.upload ?? 0,
			icon: ArrowUpTray,
		},
		{
			value: 'generated' as const,
			label: 'generated',
			count: fileCounts.by_source?.generated ?? 0,
			icon: Sparkles,
		},
		{
			value: 'import' as const,
			label: 'imports',
			count: fileCounts.by_source?.import ?? 0,
			icon: DocumentArrowDown,
		},
	])
	const manageableProjectOptions = $derived.by(() =>
		projects.list
			.filter((candidate) =>
				canEditAccessLevel(
					resourceAccess.level('project', candidate.id, candidate.owner_id)
				)
			)
			.map((candidate) => ({
				id: candidate.id,
				name: candidate.name,
				owner_id: candidate.owner_id,
			}))
	)

	function closeSortMenu() {
		isSortMenuOpen = false
	}

	function closeFilterMenu() {
		isFilterMenuOpen = false
	}

	function toggleSortMenu(event: MouseEvent) {
		sortButtonEl = event.currentTarget as HTMLButtonElement
		isSortMenuOpen = !isSortMenuOpen
		if (isSortMenuOpen) isFilterMenuOpen = false
	}

	function toggleFilterMenu(event: MouseEvent) {
		filterButtonEl = event.currentTarget as HTMLButtonElement
		isFilterMenuOpen = !isFilterMenuOpen
		if (isFilterMenuOpen) isSortMenuOpen = false
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
			void files.loadCounts()
		} finally {
			isUploading = false
			input.value = ''
		}
	}

	function fileProjectIds(resource: ResourceItem): string[] {
		const value = resource.meta?.project_ids
		return Array.isArray(value)
			? value.filter((id): id is string => typeof id === 'string')
			: []
	}

	async function handleFileProjectToggle(
		resource: ResourceItem,
		projectId: string,
		selected: boolean
	): Promise<void> {
		const currentIds = fileProjectIds(resource)
		const nextIds = selected
			? [...new Set([...currentIds, projectId])]
			: currentIds.filter((id) => id !== projectId)
		const { error } = await api.PATCH('/v1/files/{file_id}', {
			params: { path: { file_id: resource.id } },
			body: { project_ids: nextIds },
		})
		if (error) return
		projects.invalidateResourceCounts([...new Set([...currentIds, ...nextIds])])
		await files.load({ force: true, category: activeCategory, source: activeSource })
		void files.loadCounts()
	}

	function shareFile(resource: ResourceItem): void {
		modals.open('resource-access', {
			resourceType: 'file',
			resourceId: resource.id,
			title: resource.title || 'file',
		})
	}

	async function deleteFile(resource: ResourceItem): Promise<boolean> {
		return await files.remove(resource.id)
	}

	const resourceItems = $derived.by((): ResourceItem[] => {
		const [field, dir] = sort.split(':') as [string, 'asc' | 'desc']
		const sorted = [...files.resources]
		sorted.sort((a, b) => {
			let cmp: number
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
		void files.load({ force: true, category: activeCategory, source: activeSource })
	})

	$effect(() => {
		void files.loadCounts()
	})

	$effect(() => {
		void files.loadCounts({ category: activeCategory, source: activeSource })
	})

	$effect(() => {
		void projects.load()
	})

	$effect(() => {
		for (const candidate of projects.list) {
			void resourceAccess.ensure('project', candidate.id, candidate.owner_id)
		}
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
		bind:this={filterButtonEl}
		class="group rounded-pill relative flex cursor-pointer items-center justify-center border-none bg-transparent opacity-80 transition-all duration-150 hover:scale-[1.05] hover:opacity-100 active:scale-[0.97]"
		onclick={toggleFilterMenu}
		aria-label="filter files"
		aria-haspopup="menu"
		aria-expanded={isFilterMenuOpen}
	>
		<Funnel variant="solid" />
		{#if activeFilterCount > 0}
			<span
				class="bg-foreground text-background absolute -top-0.5 -right-0.5 flex size-3.5 items-center justify-center rounded-full text-[9px] leading-none font-semibold"
				aria-hidden="true"
			>
				{activeFilterCount}
			</span>
		{/if}
	</button>
	<PopupMenu
		open={isFilterMenuOpen}
		anchorEl={filterButtonEl}
		onClose={closeFilterMenu}
		class="min-w-64"
	>
		<div
			class="text-foreground/50 flex items-center gap-2 px-3 pt-1 pb-2 text-xs font-semibold tracking-[0.08em] uppercase"
		>
			<Funnel class="h-3.5 w-3.5" variant="solid" />
			filter files
		</div>
		<div class="text-foreground/45 px-3 pt-1 pb-1 text-[11px] font-semibold uppercase">
			type
		</div>
		{#each categoryOptions as option (option.value)}
			<MenuItem
				selected={categoryFilter === option.value}
				onclick={() => (categoryFilter = option.value)}
			>
				{#snippet icon()}
					{@const OptionIcon = option.icon}
					<OptionIcon class="size-full" />
				{/snippet}
				{option.label}
				{#snippet trailing()}
					<span class="text-foreground/45 text-xs tabular-nums">{option.count}</span>
				{/snippet}
			</MenuItem>
		{/each}
		<div class="text-foreground/45 px-3 pt-3 pb-1 text-[11px] font-semibold uppercase">
			source
		</div>
		{#each sourceOptions as option (option.value)}
			<MenuItem
				selected={sourceFilter === option.value}
				onclick={() => (sourceFilter = option.value)}
			>
				{#snippet icon()}
					{@const OptionIcon = option.icon}
					<OptionIcon class="size-full" />
				{/snippet}
				{option.label}
				{#snippet trailing()}
					<span class="text-foreground/45 text-xs tabular-nums">{option.count}</span>
				{/snippet}
			</MenuItem>
		{/each}
		{#if activeFilterCount > 0}
			<div class="bg-foreground/8 my-2 h-px"></div>
			<MenuItem
				onclick={() => {
					categoryFilter = 'all'
					sourceFilter = 'all'
				}}
			>
				{#snippet icon()}<XMark class="size-full" />{/snippet}
				clear filters
			</MenuItem>
		{/if}
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
		<SortIcon />
	</button>
	<PopupMenu
		open={isSortMenuOpen}
		anchorEl={sortButtonEl}
		onClose={closeSortMenu}
		class="min-w-52"
	>
		<div
			class="text-foreground/50 flex items-center gap-2 px-3 pt-1 pb-2 text-xs font-semibold tracking-[0.08em] uppercase"
		>
			<SortIcon class="h-3.5 w-3.5" />
			sort files
		</div>
		{#each sortOptions as option (option.value)}
			<MenuItem
				selected={sort === option.value}
				onclick={() => {
					sort = option.value
					closeSortMenu()
				}}
			>
				{#snippet icon()}<SortIcon value={option.value} class="h-4 w-4" />{/snippet}
				{option.label}
			</MenuItem>
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
		{currentUserId}
		ownedSectionLabel="your files"
		ownedSectionCount={ownedFileCount}
		sharedSectionCount={sharedFileCount}
		ownedEmptyMessage="no files yet. upload files to see them here"
		sharedEmptyMessage="no shared files"
		filter="files"
		{sort}
		emptyMessage="no files yet. upload files to see them here"
		pageSize={50}
		onLoadMore={() => files.loadMore({ category: activeCategory, source: activeSource })}
		hasMore={files.hasMore}
		loadingMore={files.loadingMore}
		onItemClick={(item) => modals.open('file-details', { fileId: item.id })}
		onItemEdit={(item) => modals.open('file-details', { fileId: item.id })}
		onItemShare={shareFile}
		onItemDelete={deleteFile}
		onItemProjectToggle={handleFileProjectToggle}
		projectOptions={manageableProjectOptions}
		getItemProjectIds={fileProjectIds}
	/>
</div>
