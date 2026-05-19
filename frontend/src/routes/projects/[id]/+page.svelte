<script lang="ts">
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import { page } from '$app/state'
	import { api } from '$lib/api/client'
	import { deleteThread, updateThread } from '$lib/chat/threadActions'
	import CalendarManageModal from '$lib/components/calendar/CalendarManageModal.svelte'
	import DeleteButton from '$lib/components/DeleteButton.svelte'
	import ChevronLeft from '$lib/components/icons/ChevronLeft.svelte'
	import EllipsisHorizontal from '$lib/components/icons/EllipsisHorizontal.svelte'
	import FinderFolder from '$lib/components/icons/FinderFolder.svelte'
	import Funnel from '$lib/components/icons/Funnel.svelte'
	import InfoCircle from '$lib/components/icons/InfoCircle.svelte'
	import Plus from '$lib/components/icons/Plus.svelte'
	import Share from '$lib/components/icons/Share.svelte'
	import SortIcon from '$lib/components/icons/SortIcon.svelte'
	import Trash from '$lib/components/icons/Trash.svelte'
	import ChatPropertiesModal from '$lib/components/modals/ChatPropertiesModal.svelte'
	import ProjectPropertiesModal from '$lib/components/modals/ProjectPropertiesModal.svelte'
	import ResourcePickerModal from '$lib/components/modals/ResourcePickerModal.svelte'
	import PageTitle from '$lib/components/PageTitle.svelte'
	import { MenuItem, PopupMenu } from '$lib/components/primitives'
	import ReminderListPropertiesModal from '$lib/components/reminders/ReminderListPropertiesModal.svelte'
	import ResourcesView from '$lib/components/ResourcesView.svelte'
	import type {
		ResourceFilterMode,
		ResourceItem,
		ResourceLayoutMode,
		ResourceSortMode,
	} from '$lib/components/widgets'
	import { useSystemChrome } from '$lib/contexts/systemChromeContext.svelte'
	import {
		resourceAccentStyle,
		resourceVisual,
		type ResourceVisualType,
	} from '$lib/resources/resourceVisuals'
	import { calendars, type Calendar as CalendarRecord } from '$lib/stores/calendars.svelte'
	import type { Thread } from '$lib/stores/chat.svelte'
	import { chat } from '$lib/stores/chat.svelte'
	import { apiFileToResource, files } from '$lib/stores/files.svelte'
	import { modals } from '$lib/stores/modals.svelte'
	import { notes, type Note } from '$lib/stores/notes.svelte'
	import { projects } from '$lib/stores/projects.svelte'
	import { reminders, type ReminderListWithCounts } from '$lib/stores/reminders.svelte'
	import {
		canDeleteAccessLevel,
		canEditAccessLevel,
		resourceAccess,
	} from '$lib/stores/resourceAccess.svelte'
	import { session } from '$lib/stores/session.svelte'
	import { untrack } from 'svelte'
	import { SvelteSet } from 'svelte/reactivity'

	const chrome = useSystemChrome()

	let filter = $state<ResourceFilterMode>('all')
	let sort = $state<ResourceSortMode>('updated_at:desc')
	let layout = $state<ResourceLayoutMode>('grid')
	let loading = $state(true)
	let projectThreads = $state<Thread[]>([])
	let loadSequence = 0

	let isFilterMenuOpen = $state(false)
	let isSortMenuOpen = $state(false)
	let filterButtonEl: HTMLButtonElement | null = $state(null)
	let sortButtonEl: HTMLButtonElement | null = $state(null)

	let isEditModalOpen = $state(false)
	let isPickerOpen = $state(false)
	let editThread = $state<Thread | null>(null)
	let editThreadTitle = $state('')
	let editThreadTags = $state<string[]>([])
	let editThreadError = $state<string | null>(null)
	let isSavingThreadEdit = $state(false)
	let editReminderList = $state<ReminderListWithCounts | null>(null)
	let editCalendar = $state<CalendarRecord | null>(null)
	let isCalendarModalOpen = $state(false)

	let moreMenuOpen = $state(false)
	let moreButtonEl: HTMLButtonElement | null = $state(null)
	let showDeleteConfirm = $state(false)

	const projectId = $derived(page.params.id)
	const project = $derived(projectId ? projects.getById(projectId) : null)
	const projectThreadIds = $derived(project?.thread_ids ?? [])
	const projectAccessLevel = $derived(
		project ? resourceAccess.level('project', project.id, project.owner_id) : null
	)
	const canEditProject = $derived(canEditAccessLevel(projectAccessLevel))
	const canDeleteProject = $derived(canDeleteAccessLevel(projectAccessLevel))
	const currentUserId = $derived(session.currentUserId)
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
				owner_id: thread.owner_id,
				project_ids: thread.project_ids,
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
			meta: { labels: note.labels, owner_id: note.userId, project_ids: note.projectIds },
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
				owner_id: list.owner_id,
				project_ids: list.project_ids ?? [],
			},
		}
	}

	function calendarToResource(calendar: CalendarRecord): ResourceItem {
		return {
			id: calendar.id,
			type: 'calendar',
			title: calendar.name || 'untitled calendar',
			subtitle: calendar.description ?? undefined,
			href: resolve('/calendar'),
			updatedAt: new Date(calendar.updated_at).getTime(),
			createdAt: new Date(calendar.created_at).getTime(),
			meta: {
				owner_id: calendar.owner_id,
				project_ids: calendar.project_ids ?? [],
				color: calendar.color,
				timezone: calendar.timezone,
			},
		}
	}

	const existingResourceIds = $derived.by(() => {
		return new SvelteSet(resourceItems.map((r) => r.id))
	})

	const resourceItems = $derived.by((): ResourceItem[] => {
		if (!projectId) return []
		const items: ResourceItem[] = []
		const threadIds = new SvelteSet(projectThreadIds)
		const seenThreadIds = new SvelteSet<string>()

		for (const thread of projectThreads) {
			if (threadIds.has(thread.id) || thread.project_ids?.includes(projectId)) {
				items.push(threadToResource(thread))
				seenThreadIds.add(thread.id)
			}
		}

		for (const thread of chat.recentThreads) {
			if (!seenThreadIds.has(thread.id) && thread.project_ids?.includes(projectId)) {
				items.push(threadToResource(thread))
				seenThreadIds.add(thread.id)
			}
		}

		for (const note of notes.all) {
			if (note.projectIds.includes(projectId)) {
				items.push(noteToResource(note))
			}
		}

		for (const list of reminders.lists) {
			if ((list.project_ids ?? []).includes(projectId)) {
				items.push(reminderListToResource(list))
			}
		}

		for (const file of files.all) {
			if (file.project_ids.includes(projectId)) {
				items.push(apiFileToResource(file))
			}
		}

		for (const calendar of calendars.all) {
			if ((calendar.project_ids ?? []).includes(projectId)) {
				items.push(calendarToResource(calendar))
			}
		}

		return items
	})

	async function loadProjectThreads(targetProjectId: string): Promise<Thread[]> {
		const currentProject = projects.getById(targetProjectId)
		const threadIds = currentProject?.thread_ids ?? []
		if (threadIds.length === 0) return []

		const loaded = await Promise.all(
			threadIds.map((threadId) => chat.threadCache.getThread(threadId))
		)
		return loaded.filter((thread): thread is Thread => thread !== null)
	}

	async function loadProjectData(targetProjectId: string) {
		const sequence = ++loadSequence
		loading = true
		try {
			await Promise.all([
				projects.load(),
				chat.recentThreads.length === 0 ? chat.refreshThreads() : chat.fetchUnreadCounts(),
				notes.load(),
				reminders.loadListsAndCounts(),
				files.load(),
				calendars.load(),
			])
			const loadedProjectThreads = await loadProjectThreads(targetProjectId)
			if (sequence === loadSequence && targetProjectId === projectId) {
				projectThreads = loadedProjectThreads
			}
		} finally {
			if (sequence === loadSequence) loading = false
		}
	}

	async function deleteProject(): Promise<boolean> {
		if (!projectId || !canDeleteProject) return false
		const success = await projects.remove(projectId)
		if (success) {
			await goto(resolve('/projects'))
		}
		return success
	}

	async function handleResourcePicked(resource: ResourceItem) {
		if (!projectId || !canEditProject) return

		if (resource.type === 'thread') {
			const thread =
				chat.recentThreads.find((t) => t.id === resource.id) ??
				(await chat.threadCache.getThread(resource.id))
			const currentIds = thread?.project_ids ?? []
			if (!currentIds.includes(projectId)) {
				const { data } = await api.PATCH('/v1/threads/{thread_id}', {
					params: { path: { thread_id: resource.id } },
					body: { project_ids: [...currentIds, projectId] },
				})
				if (data) {
					chat.threadCache.set(data)
					chat.updateRecentThread(data.id, () => data)
					projectThreads = [data, ...projectThreads.filter((t) => t.id !== data.id)]
					await projects.load({ force: true })
				}
			}
		} else if (resource.type === 'note') {
			const note = notes.get(resource.id)
			const currentIds = note?.projectIds ?? []
			if (!currentIds.includes(projectId)) {
				await api.PUT('/v1/notes/{note_id}', {
					params: { path: { note_id: resource.id } },
					body: { project_ids: [...currentIds, projectId] },
				})
				await notes.load({ force: true })
			}
		} else if (resource.type === 'reminder_list') {
			const list = reminders.lists.find((l) => l.id === resource.id)
			const currentIds = list?.project_ids ?? []
			if (!currentIds.includes(projectId)) {
				await api.PATCH('/v1/reminder-lists/{list_id}', {
					params: { path: { list_id: resource.id } },
					body: { project_ids: [...currentIds, projectId] },
				})
				await reminders.loadListsAndCounts()
			}
		} else if (resource.type === 'file') {
			const file = files.all.find((f) => f.id === resource.id)
			const currentIds = file?.project_ids ?? []
			if (!currentIds.includes(projectId)) {
				await api.PATCH('/v1/files/{file_id}', {
					params: { path: { file_id: resource.id } },
					body: { project_ids: [...currentIds, projectId] },
				})
				await files.load({ force: true })
			}
		} else if (resource.type === 'calendar') {
			const calendar = calendars.all.find((item) => item.id === resource.id)
			const currentIds = calendar?.project_ids ?? []
			if (!currentIds.includes(projectId)) {
				await calendars.update(resource.id, { project_ids: [...currentIds, projectId] })
			}
		}

		isPickerOpen = false
	}

	function resourceProjectIds(resource: ResourceItem): string[] {
		const value = resource.meta?.project_ids
		return Array.isArray(value)
			? value.filter((id): id is string => typeof id === 'string')
			: projectId
				? [projectId]
				: []
	}

	function uniqueIds(ids: string[]): string[] {
		return [...new Set(ids.filter(Boolean))]
	}

	async function getThreadResource(resourceId: string): Promise<Thread | null> {
		return (
			projectThreads.find((thread) => thread.id === resourceId) ??
			chat.recentThreads.find((thread) => thread.id === resourceId) ??
			(await chat.threadCache.getThread(resourceId))
		)
	}

	async function updateResourceProjects(
		resource: ResourceItem,
		nextProjectIds: string[]
	): Promise<boolean> {
		const activeProjectId = projectId
		const nextIds = uniqueIds(nextProjectIds)
		const previousIds = resourceProjectIds(resource)
		const changedProjectIds = uniqueIds([...previousIds, ...nextIds])

		if (resource.type === 'thread') {
			const { data, error } = await api.PATCH('/v1/threads/{thread_id}', {
				params: { path: { thread_id: resource.id } },
				body: { project_ids: nextIds },
			})
			if (error || !data) return false
			chat.threadCache.set(data)
			chat.updateRecentThread(data.id, () => data)
			projectThreads =
				activeProjectId && nextIds.includes(activeProjectId)
					? [data, ...projectThreads.filter((thread) => thread.id !== data.id)]
					: projectThreads.filter((thread) => thread.id !== data.id)
		} else if (resource.type === 'note') {
			const note = notes.get(resource.id)
			const ok = await notes.update(resource.id, {
				title: note?.title,
				content: note?.content,
				labels: note?.labels,
				projectIds: nextIds,
			})
			if (!ok) return false
		} else if (resource.type === 'reminder_list') {
			const { error } = await api.PATCH('/v1/reminder-lists/{list_id}', {
				params: { path: { list_id: resource.id } },
				body: { project_ids: nextIds },
			})
			if (error) return false
			await reminders.loadListsAndCounts()
		} else if (resource.type === 'file') {
			const { error } = await api.PATCH('/v1/files/{file_id}', {
				params: { path: { file_id: resource.id } },
				body: { project_ids: nextIds },
			})
			if (error) return false
			await files.load({ force: true })
			void files.loadCounts()
		} else if (resource.type === 'calendar') {
			const saved = await calendars.update(resource.id, { project_ids: nextIds })
			if (!saved) return false
		}

		projects.invalidateResourceCounts(changedProjectIds)
		return true
	}

	function handleResourceShare(resource: ResourceItem): void {
		modals.open('resource-access', {
			resourceType: resource.type,
			resourceId: resource.id,
			title: resource.title || resource.id,
		})
	}

	async function handleResourceProperties(resource: ResourceItem): Promise<void> {
		if (resource.type === 'file') {
			modals.open('file-details', { fileId: resource.id })
			return
		}
		if (resource.type === 'note') {
			modals.open('note-properties', { noteId: resource.id })
			return
		}
		if (resource.type === 'thread') {
			const thread = await getThreadResource(resource.id)
			if (!thread) return
			editThreadError = null
			editThread = thread
			return
		}
		if (resource.type === 'reminder_list') {
			editReminderList = reminders.lists.find((list) => list.id === resource.id) ?? null
			return
		}
		if (resource.type === 'calendar') {
			editCalendar = calendars.all.find((calendar) => calendar.id === resource.id) ?? null
			isCalendarModalOpen = editCalendar !== null
		}
	}

	async function handleResourceDelete(resource: ResourceItem): Promise<boolean> {
		let success = false
		if (resource.type === 'thread') {
			const status = await deleteThread(resource.id)
			success = status === 204
			if (success) {
				chat.removeRecentThread(resource.id)
				projectThreads = projectThreads.filter((thread) => thread.id !== resource.id)
			}
		} else if (resource.type === 'note') {
			success = await notes.remove(resource.id)
		} else if (resource.type === 'reminder_list') {
			success = await reminders.deleteList(resource.id)
		} else if (resource.type === 'file') {
			success = await files.remove(resource.id)
		} else if (resource.type === 'calendar') {
			success = await calendars.remove(resource.id)
		}

		if (success && projectId) projects.invalidateResourceCounts([projectId])
		return success
	}

	async function handleRemoveResourceFromProject(resource: ResourceItem): Promise<void> {
		if (!projectId) return
		const nextProjectIds = resourceProjectIds(resource).filter((id) => id !== projectId)
		await updateResourceProjects(resource, nextProjectIds)
	}

	async function handleResourceProjectToggle(
		resource: ResourceItem,
		targetProjectId: string,
		selected: boolean
	): Promise<void> {
		const currentIds = resourceProjectIds(resource)
		const nextProjectIds = selected
			? uniqueIds([...currentIds, targetProjectId])
			: currentIds.filter((id) => id !== targetProjectId)
		await updateResourceProjects(resource, nextProjectIds)
	}

	$effect(() => {
		if (!editThread) return
		editThreadTitle = editThread.title ?? ''
		editThreadTags = Array.isArray(editThread.tags) ? [...editThread.tags] : []
	})

	function closeThreadProperties(): void {
		if (isSavingThreadEdit) return
		editThread = null
		editThreadError = null
	}

	function saveThreadProperties(): void {
		if (isSavingThreadEdit || !editThread) return
		void (async () => {
			const threadId = editThread?.id
			if (!threadId) return
			isSavingThreadEdit = true
			editThreadError = null
			const ok = await updateThread(threadId, editThreadTitle.trim(), editThreadTags)
			if (ok) editThread = null
			else editThreadError = 'could not save changes'
			isSavingThreadEdit = false
		})()
	}

	function shareThreadProperties(): void {
		if (!editThread) return
		const thread = editThread
		editThread = null
		editThreadError = null
		modals.open('resource-access', {
			resourceType: 'thread',
			resourceId: thread.id,
			title: thread.title ?? thread.id,
		})
	}

	function handleItemClick(item: ResourceItem): void {
		switch (item.type) {
			case 'thread':
				void goto(resolve(`/c/${item.id}`))
				return
			case 'note':
				void goto(resolve(`/notes/${item.id}`))
				return
			case 'reminder_list':
				void goto(resolve(`/reminders/lists/${item.id}`))
				return
			case 'calendar':
				void goto(resolve('/calendar'))
				return
			case 'file':
				modals.open('file-details', { fileId: item.id })
				return
			case 'project':
				void goto(resolve(`/projects/${item.id}`))
				return
		}
	}

	function shareProject(): void {
		if (!project) return
		moreMenuOpen = false
		modals.open('resource-access', {
			resourceType: 'project',
			resourceId: project.id,
			title: project.name,
		})
	}

	$effect(() => {
		const id = projectId
		if (!id) return
		untrack(() => void loadProjectData(id))
	})

	$effect(() => {
		const accessKey = project ? `${project.id}:${resourceAccess.version}` : ''
		if (project && accessKey)
			void resourceAccess.ensure('project', project.id, project.owner_id)
	})

	$effect(() => {
		const projectsAccessKey = `${resourceAccess.version}:${projects.list.map((candidate) => candidate.id).join('|')}`
		if (!projectsAccessKey) return
		for (const candidate of projects.list) {
			void resourceAccess.ensure('project', candidate.id, candidate.owner_id)
		}
	})

	$effect(() => {
		const targetProjectId = projectId
		const threadIdsKey = projectThreadIds.join('|')
		if (!targetProjectId) return
		void (async () => {
			const loadedProjectThreads = await loadProjectThreads(targetProjectId)
			if (targetProjectId === projectId && threadIdsKey === projectThreadIds.join('|')) {
				projectThreads = loadedProjectThreads
			}
		})()
	})

	$effect(() => {
		chrome.setContextActions(islandContextActions)
		return () => chrome.setContextActions(null)
	})

	const filterOptions: {
		value: ResourceFilterMode
		label: string
		resourceType?: ResourceVisualType
	}[] = [
		{ value: 'all', label: 'all' },
		{ value: 'threads', label: resourceVisual('thread').pluralLabel, resourceType: 'thread' },
		{ value: 'notes', label: resourceVisual('note').pluralLabel, resourceType: 'note' },
		{
			value: 'reminders',
			label: resourceVisual('reminder_list').pluralLabel,
			resourceType: 'reminder_list',
		},
		{ value: 'files', label: resourceVisual('file').pluralLabel, resourceType: 'file' },
		{
			value: 'calendars',
			label: resourceVisual('calendar').pluralLabel,
			resourceType: 'calendar',
		},
		{
			value: 'projects',
			label: resourceVisual('project').pluralLabel,
			resourceType: 'project',
		},
	]

	const sortOptions: { value: ResourceSortMode; label: string }[] = [
		{ value: 'updated_at:desc', label: 'last updated' },
		{ value: 'updated_at:asc', label: 'first updated' },
		{ value: 'created_at:desc', label: 'newest' },
		{ value: 'created_at:asc', label: 'oldest' },
		{ value: 'title:asc', label: 'title a-z' },
		{ value: 'title:desc', label: 'title z-a' },
	]
	const projectResourcePickerTypes: ResourceItem['type'][] = [
		'thread',
		'note',
		'reminder_list',
		'file',
		'calendar',
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
		<Funnel variant="solid" />
	</button>
	<PopupMenu
		open={isFilterMenuOpen}
		anchorEl={filterButtonEl}
		onClose={closeMenus}
		class="min-w-52"
	>
		<div
			class="text-foreground/50 flex items-center gap-2 px-3 pt-1 pb-2 text-xs font-semibold tracking-[0.08em] uppercase"
		>
			<Funnel class="h-3.5 w-3.5" variant="solid" />
			filter resources
		</div>
		{#each filterOptions as option (option.value)}
			{@const visual = option.resourceType ? resourceVisual(option.resourceType) : null}
			<MenuItem
				selected={filter === option.value}
				onclick={() => {
					filter = option.value
					closeMenus()
				}}
			>
				{#snippet icon()}
					{#if visual}
						{@const Icon = visual.icon}
						<span
							class="flex size-full items-center justify-center text-(--accent-primary)"
							style={resourceAccentStyle(visual.type)}
						>
							<Icon variant="solid" />
						</span>
					{:else}
						<Funnel class="h-4 w-4" variant="solid" />
					{/if}
				{/snippet}
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
		<SortIcon />
	</button>
	<PopupMenu open={isSortMenuOpen} anchorEl={sortButtonEl} onClose={closeMenus} class="min-w-52">
		<div
			class="text-foreground/50 flex items-center gap-2 px-3 pt-1 pb-2 text-xs font-semibold tracking-[0.08em] uppercase"
		>
			<SortIcon class="h-3.5 w-3.5" />
			sort resources
		</div>
		{#each sortOptions as option (option.value)}
			<MenuItem
				selected={sort === option.value}
				onclick={() => {
					sort = option.value
					closeMenus()
				}}
			>
				{#snippet icon()}<SortIcon value={option.value} class="h-4 w-4" />{/snippet}
				{option.label}
			</MenuItem>
		{/each}
	</PopupMenu>

	{#if canEditProject}
		<button
			type="button"
			class="group rounded-pill flex cursor-pointer items-center justify-center border-none bg-transparent opacity-80 transition-all duration-150 hover:scale-[1.05] hover:opacity-100 active:scale-[0.97]"
			onclick={() => (isPickerOpen = true)}
			aria-label="add resource"
		>
			<Plus />
		</button>
	{/if}
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
			{#if project}
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
						{#if project}
							<MenuItem onclick={shareProject}>
								{#snippet icon()}<Share class="size-4" />{/snippet}
								share
							</MenuItem>
						{/if}
						{#if canEditProject}
							<MenuItem
								onclick={() => {
									moreMenuOpen = false
									isEditModalOpen = true
								}}
							>
								{#snippet icon()}<InfoCircle
										variant="solid"
										class="size-4"
									/>{/snippet}
								project properties
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
						{/if}
						{#if canDeleteProject}
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
						{/if}
					</PopupMenu>
				</div>
			{/if}
		</div>

		<ResourcesView
			resources={resourceItems}
			{loading}
			bind:layout
			{filter}
			{sort}
			{currentUserId}
			showOwnershipSections={false}
			emptyMessage="no resources in this project yet"
			pageSize={24}
			class="flex-1"
			onItemClick={handleItemClick}
			onItemEdit={handleResourceProperties}
			onItemShare={handleResourceShare}
			onItemDelete={handleResourceDelete}
			onItemRemoveFromProject={handleRemoveResourceFromProject}
			onItemProjectToggle={handleResourceProjectToggle}
			projectOptions={manageableProjectOptions}
			getItemProjectIds={resourceProjectIds}
		/>
	{/if}
</div>

{#if project}
	<ProjectPropertiesModal
		open={isEditModalOpen && canEditProject}
		{project}
		onClose={() => (isEditModalOpen = false)}
	/>
{/if}

<ResourcePickerModal
	open={isPickerOpen && canEditProject}
	onClose={() => (isPickerOpen = false)}
	onSelect={handleResourcePicked}
	excludeIds={existingResourceIds}
	allowedTypes={projectResourcePickerTypes}
/>

<ChatPropertiesModal
	open={editThread !== null}
	thread={editThread}
	bind:title={editThreadTitle}
	bind:tags={editThreadTags}
	error={editThreadError}
	isSaving={isSavingThreadEdit}
	onClose={closeThreadProperties}
	onShare={shareThreadProperties}
	onSave={saveThreadProperties}
/>

<ReminderListPropertiesModal
	open={editReminderList !== null}
	list={editReminderList}
	onClose={() => (editReminderList = null)}
/>

<CalendarManageModal
	open={isCalendarModalOpen}
	calendar={editCalendar}
	onClose={() => {
		isCalendarModalOpen = false
		editCalendar = null
	}}
/>

{#if canDeleteProject}
	<DeleteButton
		showTrigger={false}
		bind:open={showDeleteConfirm}
		onDelete={deleteProject}
		modalText={{
			title: 'delete project?',
			description: 'this will remove the project but not its resources.',
		}}
	/>
{/if}
