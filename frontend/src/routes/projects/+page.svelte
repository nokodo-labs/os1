<script lang="ts">
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import FinderFolder from '$lib/components/icons/FinderFolder.svelte'
	import Plus from '$lib/components/icons/Plus.svelte'
	import SortIcon from '$lib/components/icons/SortIcon.svelte'
	import CreateProjectModal from '$lib/components/modals/CreateProjectModal.svelte'
	import ProjectPropertiesModal from '$lib/components/modals/ProjectPropertiesModal.svelte'
	import PageTitle from '$lib/components/PageTitle.svelte'
	import { MenuItem, PopupMenu } from '$lib/components/primitives'
	import ResourcesView from '$lib/components/ResourcesView.svelte'
	import type { ResourceItem, ResourceLayoutMode } from '$lib/components/widgets'
	import { useSystemChrome } from '$lib/contexts/systemChromeContext.svelte'
	import { accentStore } from '$lib/stores/accent.svelte'
	import { modals } from '$lib/stores/modals.svelte'
	import { pageTitleStore } from '$lib/stores/pageTitle.svelte'
	import { projects, type Project } from '$lib/stores/projects.svelte'
	import { session } from '$lib/stores/session.svelte'

	type SortMode = 'newest' | 'oldest' | 'name'

	const chrome = useSystemChrome()

	let sort = $state<SortMode>('newest')
	let layout = $state<ResourceLayoutMode>('grid')
	let loading = $state(true)

	let isSortMenuOpen = $state(false)
	let sortButtonEl: HTMLButtonElement | null = $state(null)

	let isEditModalOpen = $state(false)
	let editingProject = $state<Project | null>(null)
	let isCreateModalOpen = $state(false)
	const currentUserId = $derived(session.currentUserId)

	function closeSortMenu() {
		isSortMenuOpen = false
	}

	function toggleSortMenu() {
		isSortMenuOpen = !isSortMenuOpen
	}

	const sortOptions: { value: SortMode; label: string }[] = [
		{ value: 'newest', label: 'newest first' },
		{ value: 'oldest', label: 'oldest first' },
		{ value: 'name', label: 'by name' },
	]

	function projectToResource(project: Project): ResourceItem {
		const counts = projects.resourceCounts(project.id)
		return {
			id: project.id,
			type: 'project',
			title: project.name,
			subtitle: project.description ?? undefined,
			href: resolve(`/projects/${project.id}`),
			updatedAt: new Date(project.updated_at).getTime(),
			createdAt: new Date(project.created_at).getTime(),
			meta: {
				thread_count: counts?.thread_count,
				note_count: counts?.note_count,
				file_count: counts?.file_count,
				reminder_list_count: counts?.reminder_list_count,
				calendar_count: counts?.calendar_count,
				resource_count: counts?.resource_count,
				counts_loaded: counts !== null,
				owner_id: project.owner_id,
			},
		}
	}

	const resourceItems = $derived.by(() => {
		const items = projects.list.map(projectToResource)
		if (sort === 'oldest') {
			items.sort((a, b) => a.createdAt - b.createdAt)
		} else if (sort === 'name') {
			items.sort((a, b) => a.title.localeCompare(b.title))
		} else {
			items.sort((a, b) => b.updatedAt - a.updatedAt)
		}
		return items
	})

	function handleItemEdit(item: ResourceItem) {
		const p = projects.getById(item.id)
		if (p) {
			editingProject = p
			isEditModalOpen = true
		}
	}

	async function handleItemDelete(item: ResourceItem): Promise<boolean> {
		return await projects.remove(item.id)
	}

	function handleItemShare(item: ResourceItem): void {
		const project = projects.getById(item.id)
		modals.open('resource-access', {
			resourceType: 'project',
			resourceId: item.id,
			title: project?.name ?? item.title,
		})
	}

	$effect(() => {
		void projects.load().then(() => {
			loading = false
		})
	})

	$effect(() => {
		for (const project of projects.list) {
			if (!project.id.startsWith('temp-')) void projects.loadResourceCounts(project.id)
		}
	})

	$effect(() => {
		pageTitleStore.pageTitle = 'projects'
	})

	$effect(() => {
		accentStore.set('yellow')
	})

	$effect(() => {
		chrome.setContextActions(islandContextActions)
		return () => chrome.setContextActions(null)
	})
</script>

{#snippet islandContextActions()}
	<button
		type="button"
		bind:this={sortButtonEl}
		class="group rounded-pill flex cursor-pointer items-center justify-center border-none bg-transparent opacity-80 transition-all duration-150 hover:scale-[1.05] hover:opacity-100 active:scale-[0.97]"
		onclick={toggleSortMenu}
		aria-label="sort projects"
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
			sort projects
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

	<button
		type="button"
		class="group rounded-pill flex cursor-pointer items-center justify-center border-none bg-transparent opacity-80 transition-all duration-150 hover:scale-[1.05] hover:opacity-100 active:scale-[0.97]"
		onclick={() => (isCreateModalOpen = true)}
		aria-label="create project"
	>
		<Plus />
	</button>
{/snippet}

<div
	class="flex flex-col gap-6 pb-10"
	style="padding-left: var(--spacing-page-x); padding-right: var(--spacing-page-x);"
>
	<div>
		<PageTitle icon={FinderFolder} label="projects" />
		<p class="text-foreground/60 mt-2 text-sm">
			organize your chats, notes, and files into projects.
		</p>
	</div>

	<ResourcesView
		resources={resourceItems}
		{loading}
		bind:layout
		{currentUserId}
		ownedSectionLabel="your projects"
		ownedEmptyMessage="no projects yet. create one to get started"
		sharedEmptyMessage="no shared projects"
		sort="updated_at:desc"
		emptyMessage="no projects yet. create one to get started"
		pageSize={24}
		onItemEdit={handleItemEdit}
		onItemShare={handleItemShare}
		onItemDelete={handleItemDelete}
	/>
</div>

<ProjectPropertiesModal
	open={isEditModalOpen && editingProject !== null}
	project={editingProject}
	onClose={() => {
		isEditModalOpen = false
		editingProject = null
	}}
/>

<CreateProjectModal
	open={isCreateModalOpen}
	onClose={() => (isCreateModalOpen = false)}
	onCreated={async (created) => {
		await goto(resolve(`/projects/${created.id}`))
	}}
/>
