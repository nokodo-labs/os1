<script lang="ts">
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import { page } from '$app/state'
	import { api } from '$lib/api/client'
	import DeleteButton from '$lib/components/DeleteButton.svelte'
	import AdjustmentsHorizontal from '$lib/components/icons/AdjustmentsHorizontal.svelte'
	import ArrowsUpDown from '$lib/components/icons/ArrowsUpDown.svelte'
	import ChevronLeft from '$lib/components/icons/ChevronLeft.svelte'
	import EllipsisHorizontal from '$lib/components/icons/EllipsisHorizontal.svelte'
	import FinderFolder from '$lib/components/icons/FinderFolder.svelte'
	import PencilSquare from '$lib/components/icons/PencilSquare.svelte'
	import Plus from '$lib/components/icons/Plus.svelte'
	import Trash from '$lib/components/icons/Trash.svelte'
	import EditProjectModal from '$lib/components/modals/EditProjectModal.svelte'
	import ResourcePickerModal from '$lib/components/modals/ResourcePickerModal.svelte'
	import PageTitle from '$lib/components/PageTitle.svelte'
	import { PopupMenu } from '$lib/components/primitives'
	import MenuItem from '$lib/components/primitives/MenuItem.svelte'
	import ResourcesView from '$lib/components/ResourcesView.svelte'
	import type {
		ResourceFilterMode,
		ResourceItem,
		ResourceLayoutMode,
		ResourceSortMode,
	} from '$lib/components/widgets'
	import { useSystemChrome } from '$lib/contexts/systemChromeContext.svelte'
	import type { Thread } from '$lib/stores/chat.svelte'
	import { chat } from '$lib/stores/chat.svelte'
	import { apiFileToResource, files } from '$lib/stores/files.svelte'
	import { notes, type Note } from '$lib/stores/notes.svelte'
	import { projects } from '$lib/stores/projects.svelte'
	import { reminders, type ReminderListWithCounts } from '$lib/stores/reminders.svelte'

	const chrome = useSystemChrome()

	let filter = $state<ResourceFilterMode>('all')
	let sort = $state<ResourceSortMode>('updated_at:desc')
	let layout = $state<ResourceLayoutMode>('grid')
	let loading = $state(true)

	let isFilterMenuOpen = $state(false)
	let isSortMenuOpen = $state(false)
	let filterButtonEl: HTMLButtonElement | null = $state(null)
	let sortButtonEl: HTMLButtonElement | null = $state(null)

	let isEditModalOpen = $state(false)
	let isPickerOpen = $state(false)

	let moreMenuOpen = $state(false)
	let moreButtonEl: HTMLButtonElement | null = $state(null)
	let showDeleteConfirm = $state(false)

	const projectId = $derived(page.params.id)
	const project = $derived(projectId ? projects.getById(projectId) : null)

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

	function threadToResource(thread: Thread): ResourceItem {
		return {
			id: thread.id,
			type: 'thread',
			title: thread.title ?? 'untitled chat',
			preview: undefined,
			href: resolve(`/c/${thread.id}`),
			updatedAt: new Date(thread.last_activity_at).getTime(),
			createdAt: new Date(thread.created_at).getTime(),
			meta: {
				tags: thread.tags,
				is_archived: thread.is_archived,
			},
		}
	}

	function noteToResource(note: Note): ResourceItem {
		return {
			id: note.id,
			type: 'note',
			title: note.title || 'untitled note',
			preview: note.content.slice(0, 200),
			href: resolve(`/notes/${note.id}`),
			updatedAt: note.updatedAt,
			createdAt: note.createdAt,
			meta: { labels: note.labels },
		}
	}

	function reminderListToResource(list: ReminderListWithCounts): ResourceItem {
		return {
			id: list.id,
			type: 'reminder_list',
			title: list.name,
			subtitle: list.description ?? undefined,
			href: resolve(`/reminders/lists/${list.id}`),
			updatedAt: new Date(list.updated_at).getTime(),
			createdAt: new Date(list.created_at).getTime(),
			meta: {
				total_count: list.total_count,
				pending_count: list.pending_count,
				completed_count: list.completed_count,
				color: list.color,
				icon: list.icon,
			},
		}
	}

	const existingResourceIds = $derived.by(() => {
		return new Set(resourceItems.map((r) => r.id))
	})

	const resourceItems = $derived.by((): ResourceItem[] => {
		if (!projectId) return []
		const items: ResourceItem[] = []

		for (const thread of chat.recentThreads) {
			if (thread.project_ids?.includes(projectId)) {
				items.push(threadToResource(thread))
			}
		}

		for (const note of notes.all) {
			if (note.projectId === projectId) {
				items.push(noteToResource(note))
			}
		}

		for (const list of reminders.lists) {
			if (list.project_id === projectId) {
				items.push(reminderListToResource(list))
			}
		}

		for (const file of files.all) {
			if (file.project_id === projectId) {
				items.push(apiFileToResource(file))
			}
		}

		return items
	})

	async function loadProjectData() {
		loading = true
		await Promise.all([
			projects.load(),
			chat.refreshThreads(),
			notes.load(),
			reminders.loadListsAndCounts(),
			files.load(),
		])
		loading = false
	}

	async function deleteProject(): Promise<boolean> {
		if (!projectId) return false
		const success = await projects.remove(projectId)
		if (success) {
			await goto(resolve('/projects'))
		}
		return success
	}

	async function handleResourcePicked(resource: ResourceItem) {
		if (!projectId) return

		if (resource.type === 'thread') {
			const thread = chat.recentThreads.find((t) => t.id === resource.id)
			const currentIds = thread?.project_ids ?? []
			if (!currentIds.includes(projectId)) {
				const { data } = await api.PATCH('/v1/threads/{thread_id}', {
					params: { path: { thread_id: resource.id } },
					body: { project_ids: [...currentIds, projectId] },
				})
				if (data) {
					chat.updateRecentThread(data.id, () => data)
				}
			}
		} else if (resource.type === 'note') {
			await api.PUT('/v1/notes/{note_id}', {
				params: { path: { note_id: resource.id } },
				body: { project_id: projectId },
			})
			await notes.load({ force: true })
		} else if (resource.type === 'reminder_list') {
			await api.PATCH('/v1/reminders/lists/{list_id}', {
				params: { path: { list_id: resource.id } },
				body: { project_id: projectId },
			})
			await reminders.loadListsAndCounts()
		} else if (resource.type === 'file') {
			await api.PATCH('/v1/files/{file_id}', {
				params: { path: { file_id: resource.id } },
				body: { project_id: projectId },
			})
			await files.load({ force: true })
		}

		isPickerOpen = false
	}

	$effect(() => {
		void loadProjectData()
	})

	$effect(() => {
		chrome.setContextActions(islandContextActions)
		return () => chrome.setContextActions(null)
	})

	const filterOptions: { value: ResourceFilterMode; label: string }[] = [
		{ value: 'all', label: 'all' },
		{ value: 'threads', label: 'chats' },
		{ value: 'notes', label: 'notes' },
		{ value: 'reminders', label: 'reminders' },
		{ value: 'files', label: 'files' },
	]

	const sortOptions: { value: ResourceSortMode; label: string }[] = [
		{ value: 'updated_at:desc', label: 'last updated' },
		{ value: 'updated_at:asc', label: 'first updated' },
		{ value: 'created_at:desc', label: 'newest' },
		{ value: 'created_at:asc', label: 'oldest' },
		{ value: 'title:asc', label: 'title a-z' },
		{ value: 'title:desc', label: 'title z-a' },
	]
</script>

{#snippet islandContextActions()}
	<button
		type="button"
		class="group rounded-pill flex cursor-pointer items-center justify-center border-none bg-transparent opacity-80 transition-all duration-150 hover:scale-[1.05] hover:opacity-100 active:scale-[0.97]"
		onclick={() => goto(resolve('/projects'))}
		aria-label="back to projects"
	>
		<ChevronLeft strokeWidth="2" />
	</button>

	<button
		type="button"
		bind:this={filterButtonEl}
		class="group rounded-pill flex cursor-pointer items-center justify-center border-none bg-transparent opacity-80 transition-all duration-150 hover:scale-[1.05] hover:opacity-100 active:scale-[0.97]"
		onclick={toggleFilterMenu}
		aria-label="filter resources"
		aria-haspopup="menu"
		aria-expanded={isFilterMenuOpen}
	>
		<AdjustmentsHorizontal />
	</button>
	<PopupMenu open={isFilterMenuOpen} anchorEl={filterButtonEl} onClose={closeMenus}>
		{#each filterOptions as option (option.value)}
			<MenuItem
				selected={filter === option.value}
				onclick={() => {
					filter = option.value
					closeMenus()
				}}
			>
				{option.label}
			</MenuItem>
		{/each}
	</PopupMenu>

	<button
		type="button"
		bind:this={sortButtonEl}
		class="group rounded-pill flex cursor-pointer items-center justify-center border-none bg-transparent opacity-80 transition-all duration-150 hover:scale-[1.05] hover:opacity-100 active:scale-[0.97]"
		onclick={toggleSortMenu}
		aria-label="sort resources"
		aria-haspopup="menu"
		aria-expanded={isSortMenuOpen}
	>
		<ArrowsUpDown variant="solid" />
	</button>
	<PopupMenu open={isSortMenuOpen} anchorEl={sortButtonEl} onClose={closeMenus}>
		{#each sortOptions as option (option.value)}
			<MenuItem
				selected={sort === option.value}
				onclick={() => {
					sort = option.value
					closeMenus()
				}}
			>
				{option.label}
			</MenuItem>
		{/each}
	</PopupMenu>

	<button
		type="button"
		class="group rounded-pill flex cursor-pointer items-center justify-center border-none bg-transparent opacity-80 transition-all duration-150 hover:scale-[1.05] hover:opacity-100 active:scale-[0.97]"
		onclick={() => (isPickerOpen = true)}
		aria-label="add resource"
	>
		<Plus />
	</button>
{/snippet}

<div
	class="flex min-h-full flex-1 flex-col gap-6 pb-10"
	style="padding-left: var(--spacing-page-x); padding-right: var(--spacing-page-x);"
>
	{#if !project && !loading}
		<div class="flex flex-1 flex-col items-center justify-center py-20 text-center">
			<p class="text-foreground/50 text-sm">project not found</p>
			<button
				type="button"
				class="rounded-pill border-foreground/10 bg-foreground/5 text-foreground/70 hover:bg-foreground/10 mt-4 cursor-pointer border px-4 py-2 text-sm transition-colors"
				onclick={() => goto(resolve('/projects'))}
			>
				back to projects
			</button>
		</div>
	{:else if loading && !project}
		<div class="flex items-center gap-3">
			<FinderFolder class="text-foreground h-7 w-7 shrink-0" variant="solid" />
			<div class="bg-foreground/10 h-8 w-48 animate-pulse rounded-full"></div>
		</div>
	{:else}
		<div class="flex items-start gap-3">
			<div class="flex-1">
				<PageTitle icon={FinderFolder} label={project?.name ?? ''} />
				{#if project?.description}
					<p class="text-foreground/60 mt-2 text-sm">{project.description}</p>
				{/if}
			</div>
			<div class="relative flex shrink-0 gap-1 pt-1">
				<button
					type="button"
					bind:this={moreButtonEl}
					class="text-foreground/60 hover:text-foreground/90 flex size-8 cursor-pointer items-center justify-center rounded-lg border-none bg-transparent transition-colors"
					onclick={() => (moreMenuOpen = !moreMenuOpen)}
					aria-label="project options"
					aria-haspopup="menu"
					aria-expanded={moreMenuOpen}
				>
					<EllipsisHorizontal class="size-5" />
				</button>
				<PopupMenu
					open={moreMenuOpen}
					anchorEl={moreButtonEl}
					onClose={() => (moreMenuOpen = false)}
				>
					<MenuItem
						onclick={() => {
							moreMenuOpen = false
							isEditModalOpen = true
						}}
					>
						{#snippet icon()}<PencilSquare class="size-4" />{/snippet}
						edit project
					</MenuItem>
					<MenuItem
						onclick={() => {
							moreMenuOpen = false
							isPickerOpen = true
						}}
					>
						{#snippet icon()}<Plus class="size-4" />{/snippet}
						add resource
					</MenuItem>
					<button
						type="button"
						class="group/del rounded-pill text-foreground/80 flex w-full cursor-pointer items-center border-none bg-transparent px-3 py-2 text-left text-sm transition-colors duration-150 hover:bg-red-500/10 hover:text-red-300"
						onclick={() => {
							moreMenuOpen = false
							showDeleteConfirm = true
						}}
					>
						<Trash
							class="h-4 w-4 text-red-400 transition-colors duration-150 group-hover/del:text-red-300"
						/>
						<span class="ml-2">delete</span>
					</button>
				</PopupMenu>
			</div>
		</div>

		<ResourcesView
			resources={resourceItems}
			{loading}
			bind:layout
			{filter}
			{sort}
			emptyMessage="no resources in this project yet"
			pageSize={24}
			class="flex-1"
		/>
	{/if}
</div>

{#if project}
	<EditProjectModal open={isEditModalOpen} {project} onClose={() => (isEditModalOpen = false)} />
{/if}

<ResourcePickerModal
	open={isPickerOpen}
	onClose={() => (isPickerOpen = false)}
	onSelect={handleResourcePicked}
	excludeIds={existingResourceIds}
/>

<DeleteButton
	showTrigger={false}
	bind:open={showDeleteConfirm}
	onDelete={deleteProject}
	modalText={{
		title: 'delete project?',
		description: 'this will remove the project but not its resources.',
	}}
/>
