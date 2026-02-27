<script lang="ts">
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import PageTitle from '$lib/components/PageTitle.svelte'
	import ArrowsUpDown from '$lib/components/icons/ArrowsUpDown.svelte'
	import FinderFolder from '$lib/components/icons/FinderFolder.svelte'
	import Plus from '$lib/components/icons/Plus.svelte'
	import CreateProjectModal from '$lib/components/modals/CreateProjectModal.svelte'
	import EditProjectModal from '$lib/components/modals/EditProjectModal.svelte'
	import { PopupMenu } from '$lib/components/primitives'
	import ResourcesView from '$lib/components/ResourcesView.svelte'
	import type { ResourceItem, ResourceLayoutMode } from '$lib/components/widgets'
	import { useSystemChrome } from '$lib/contexts/systemChromeContext.svelte'
	import { accentStore } from '$lib/stores/accent.svelte'
	import { pageTitleStore } from '$lib/stores/pageTitle.svelte'
	import { projects, type Project } from '$lib/stores/projects.svelte'

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

	function closeSortMenu() {
		isSortMenuOpen = false
	}

	function toggleSortMenu() {
		isSortMenuOpen = !isSortMenuOpen
	}

	function projectToResource(project: Project): ResourceItem {
		return {
			id: project.id,
			type: 'project',
			title: project.name,
			subtitle: project.description ?? undefined,
			href: resolve(`/projects/${project.id}`),
			updatedAt: new Date(project.updated_at).getTime(),
			createdAt: new Date(project.created_at).getTime(),
			meta: {
				thread_count: project.thread_ids?.length ?? 0,
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

	$effect(() => {
		void projects.load().then(() => {
			loading = false
		})
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
		<ArrowsUpDown variant="solid" />
	</button>
	<PopupMenu open={isSortMenuOpen} anchorEl={sortButtonEl} onClose={closeSortMenu}>
		{#each [{ value: 'newest', label: 'newest first' }, { value: 'oldest', label: 'oldest first' }, { value: 'name', label: 'by name' }] as option (option.value)}
			<button
				type="button"
				role="menuitem"
				class="rounded-pill flex w-full cursor-pointer items-center border-none bg-transparent px-3 py-2 text-left text-sm text-foreground/80 transition-colors duration-150 hover:bg-foreground/10"
				onclick={() => {
					sort = option.value as SortMode
					closeSortMenu()
				}}
			>
				{option.label}{sort === option.value ? ' \u2713' : ''}
			</button>
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
		<p class="mt-2 text-sm text-foreground/60">
			organize your chats, notes, and files into projects.
		</p>
	</div>

	<ResourcesView
		resources={resourceItems}
		{loading}
		bind:layout
		sort="updated_at:desc"
		emptyMessage="no projects yet - create one to get started"
		pageSize={24}
		onItemEdit={handleItemEdit}
		onItemDelete={handleItemDelete}
	/>
</div>

{#if editingProject}
	<EditProjectModal
		open={isEditModalOpen}
		project={editingProject}
		onClose={() => {
			isEditModalOpen = false
			editingProject = null
		}}
	/>
{/if}

<CreateProjectModal
	open={isCreateModalOpen}
	onClose={() => (isCreateModalOpen = false)}
	onCreated={async (created) => {
		await goto(resolve(`/projects/${created.id}`))
	}}
/>
