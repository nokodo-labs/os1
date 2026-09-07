<script lang="ts">
	import { browser } from '$app/environment'
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import { contextmenu, type ContextMenuAnchor } from '$lib/attachments/contextmenu'
	import DeleteButton from '$lib/components/DeleteButton.svelte'
	import EmptyState from '$lib/components/EmptyState.svelte'
	import FloatingScrollTopButton from '$lib/components/FloatingScrollTopButton.svelte'
	import ChevronDown from '$lib/components/icons/ChevronDown.svelte'
	import ListBullet from '$lib/components/icons/ListBullet.svelte'
	import Plus from '$lib/components/icons/Plus.svelte'
	import SortIcon from '$lib/components/icons/SortIcon.svelte'
	import MasterSidebarHeader from '$lib/components/layouts/MasterSidebarHeader.svelte'
	import {
		MenuItem,
		MenuSectionHeader,
		MenuSeparator,
		PopupMenu,
		Skeleton,
	} from '$lib/components/primitives'
	import ReminderListRow from '$lib/components/reminders/ReminderListRow.svelte'
	import ScrollTopShadow from '$lib/components/ScrollTopShadow.svelte'
	import type { ResourceProjectOption } from '$lib/components/widgets/ResourceProjectsMenu.svelte'
	import ResourceProjectsMenu from '$lib/components/widgets/ResourceProjectsMenu.svelte'
	import { modals } from '$lib/stores/modals.svelte'
	import { projects } from '$lib/stores/projects.svelte'
	import {
		reminders,
		type ReminderListWithCounts,
		type ReminderListsSortMode,
	} from '$lib/stores/reminders.svelte'
	import {
		canDeleteAccessLevel,
		canEditAccessLevel,
		resourceAccess,
	} from '$lib/stores/resourceAccess.svelte'
	import { session } from '$lib/stores/session.svelte'
	import { byAuthor } from '$lib/utils/resourceAuthors'
	import SvelteVirtualList from '@humanspeak/svelte-virtual-list'
	import { tick } from 'svelte'
	import InfoCircle from '../icons/InfoCircle.svelte'
	import Share from '../icons/Share.svelte'
	import ReminderListCreateModal from './ReminderListCreateModal.svelte'
	import ReminderListPropertiesModal from './ReminderListPropertiesModal.svelte'

	interface Props {
		selectedListId: string | null | undefined
		isLoading?: boolean
		isMobile?: boolean
	}

	let { selectedListId, isLoading = false, isMobile = false }: Props = $props()

	const lists = $derived(reminders.lists)
	const currentUserId = $derived(session.currentUserId)
	const myLists = $derived(
		currentUserId ? lists.filter((list) => list.owner_id === currentUserId) : lists
	)
	const sharedLists = $derived(
		currentUserId ? lists.filter((list) => list.owner_id !== currentUserId) : []
	)
	const manageableProjectOptions = $derived.by((): ResourceProjectOption[] =>
		projects.list
			.filter((project) =>
				canEditAccessLevel(resourceAccess.level('project', project.id, project.owner_id))
			)
			.map((project) => ({
				id: project.id,
				name: project.name,
				owner_id: project.owner_id,
			}))
	)
	let myListsOpen = $state(true)
	let sharedListsOpen = $state(true)

	type ReminderListSidebarRow =
		| { kind: 'header' }
		| { kind: 'section'; id: 'my' | 'shared'; label: string; count: number; open: boolean }
		| { kind: 'list'; id: string; list: ReminderListWithCounts }

	const listRows = $derived.by((): ReminderListSidebarRow[] => {
		const header: ReminderListSidebarRow[] = isMobile ? [{ kind: 'header' }] : []

		if (sharedLists.length === 0) {
			return [
				...header,
				...myLists.map((list) => ({ kind: 'list' as const, id: list.id, list })),
			]
		}

		const rows: ReminderListSidebarRow[] = [...header]
		if (myLists.length > 0) {
			rows.push({
				kind: 'section',
				id: 'my',
				label: 'your lists',
				count: myLists.length,
				open: myListsOpen,
			})
			if (myListsOpen) {
				rows.push(...myLists.map((list) => ({ kind: 'list' as const, id: list.id, list })))
			}
		}
		rows.push({
			kind: 'section',
			id: 'shared',
			label: 'shared with you',
			count: sharedLists.length,
			open: sharedListsOpen,
		})
		if (sharedListsOpen) {
			rows.push(...sharedLists.map((list) => ({ kind: 'list' as const, id: list.id, list })))
		}
		return rows
	})

	let isCreateListOpen = $state(false)
	let listShellEl = $state<HTMLDivElement | null>(null)
	let listViewportEl = $state<HTMLElement | null>(null)

	// sort menu state
	let isSortMenuOpen = $state(false)
	let sortButtonEl: HTMLButtonElement | null = $state(null)

	const sortOptions: { value: ReminderListsSortMode; label: string }[] = [
		{ value: 'position:asc', label: 'manual order' },
		{ value: 'name:asc', label: 'name a-z' },
		{ value: 'name:desc', label: 'name z-a' },
		{ value: 'created_at:desc', label: 'newest' },
		{ value: 'created_at:asc', label: 'oldest' },
	]

	function closeSortMenu() {
		isSortMenuOpen = false
	}

	function toggleSortMenu() {
		isSortMenuOpen = !isSortMenuOpen
		if (isSortMenuOpen) closeListMenu()
	}

	let openListMenuId = $state<string | null>(null)
	let listMenuButtonEl: HTMLButtonElement | null = $state(null)
	let listMenuAnchor = $state<ContextMenuAnchor | null>(null)

	let editListId = $state<string | null>(null)
	const editList = $derived(editListId ? reminders.getListById(editListId) : null)

	function selectList(listId: string) {
		void goto(resolve('/reminders/lists/[listId]', { listId }), {
			keepFocus: true,
			noScroll: true,
		})
	}

	function prefetchList(listId: string): void {
		void reminders.loadReminders(listId, { force: false })
	}

	function openCreateListModal() {
		isCreateListOpen = true
	}

	function closeCreateListModal() {
		isCreateListOpen = false
	}

	function handleCreateList() {
		openCreateListModal()
	}

	function toggleListMenu(listId: string, buttonEl?: HTMLButtonElement | null) {
		const opening = openListMenuId !== listId
		openListMenuId = opening ? listId : null
		if (buttonEl) listMenuButtonEl = buttonEl
		listMenuAnchor = null
	}

	/** right-click / hold anywhere on the row opens the same menu, at the gesture. */
	function openListMenuAt(listId: string, anchor: ContextMenuAnchor) {
		openListMenuId = listId
		listMenuButtonEl = null
		listMenuAnchor = anchor
	}

	function closeListMenu() {
		openListMenuId = null
		listMenuButtonEl = null
		listMenuAnchor = null
	}

	function authorSubtitle(list: (typeof lists)[0]): string | null {
		if (list.owner_id === currentUserId) return null
		return byAuthor(session.authorLabel(list.owner_id))
	}

	function listAccessLevel(list: (typeof lists)[0]) {
		return resourceAccess.level('reminder_list', list.id, list.owner_id)
	}

	function canEditList(list: (typeof lists)[0]): boolean {
		return canEditAccessLevel(listAccessLevel(list))
	}

	function canDeleteList(list: (typeof lists)[0]): boolean {
		return canDeleteAccessLevel(listAccessLevel(list))
	}

	async function handleListProjectToggle(
		list: (typeof lists)[0],
		projectId: string,
		selected: boolean
	): Promise<void> {
		if (!canEditList(list)) return
		const currentIds = list.project_ids ?? []
		const nextIds = selected
			? [...new Set([...currentIds, projectId])]
			: currentIds.filter((id) => id !== projectId)
		await reminders.updateList(list, { project_ids: nextIds })
		projects.invalidateResourceCounts([...new Set([...currentIds, ...nextIds])])
	}

	$effect(() => {
		const listsAccessKey = `${resourceAccess.version}:${lists.map((list) => list.id).join('|')}`
		if (!listsAccessKey) return
		if (sharedLists.length > 0) {
			void session.ensureUsers(sharedLists.map((list) => list.owner_id))
		}
		for (const list of lists) {
			void resourceAccess.ensure('reminder_list', list.id, list.owner_id)
		}
	})

	$effect(() => {
		void projects.load()
	})

	$effect(() => {
		const projectsAccessKey = `${resourceAccess.version}:${projects.list.map((project) => project.id).join('|')}`
		if (!projectsAccessKey) return
		for (const project of projects.list) {
			void resourceAccess.ensure('project', project.id, project.owner_id)
		}
	})

	$effect(() => {
		if (!browser) return
		const handler = () => {
			openCreateListModal()
		}
		window.addEventListener('reminders:list-add', handler)
		return () => window.removeEventListener('reminders:list-add', handler)
	})

	$effect(() => {
		const shell = listShellEl
		const rowCount = listRows.length
		if (!shell || rowCount === 0) {
			listViewportEl = null
			return
		}

		let cancelled = false
		void tick().then(() => {
			if (cancelled) return
			const viewport = shell.querySelector('.reminder-lists-sidebar-viewport')
			listViewportEl = viewport instanceof HTMLElement ? viewport : null
		})
		return () => {
			cancelled = true
		}
	})
</script>

{#snippet listItem(list: (typeof lists)[0])}
	<div
		class="relative px-3"
		{@attach contextmenu({ onOpen: (anchor) => openListMenuAt(list.id, anchor) })}
	>
		<ReminderListRow
			title={list.name}
			subtitle={authorSubtitle(list)}
			count={list.pending_count}
			selected={selectedListId === list.id}
			emoji={list.icon ?? '📋'}
			emojiColor={list.color}
			onPrefetch={() => prefetchList(list.id)}
			onSelect={() => selectList(list.id)}
			onMenu={(event) => {
				const el = event.currentTarget
				if (el instanceof HTMLButtonElement) toggleListMenu(list.id, el)
				else toggleListMenu(list.id, null)
			}}
		/>

		<PopupMenu
			open={openListMenuId === list.id}
			anchorEl={listMenuButtonEl}
			anchorPoint={listMenuAnchor}
			onClose={closeListMenu}
			data-reminders-list-menu
		>
			{#if list}
				<MenuItem
					icon={Share}
					onclick={(event) => {
						event.stopPropagation()
						closeListMenu()
						modals.open('resource-access', {
							resourceType: 'reminder_list',
							resourceId: list.id,
							title: list.name,
						})
					}}
				>
					share
				</MenuItem>
			{/if}
			{#if canEditList(list)}
				<MenuItem
					icon={InfoCircle}
					onclick={(event) => {
						event.stopPropagation()
						closeListMenu()
						editListId = list.id
					}}
				>
					properties
				</MenuItem>
				<ResourceProjectsMenu
					projectOptions={manageableProjectOptions}
					selectedProjectIds={list.project_ids ?? []}
					onProjectToggle={(projectId, selected) =>
						handleListProjectToggle(list, projectId, selected)}
				/>
			{/if}
			{#if !list.is_default && canDeleteList(list)}
				<MenuSeparator />
				<DeleteButton
					confirm={true}
					stopPropagation={true}
					onTrigger={closeListMenu}
					modalText={{
						title: 'delete list?',
						description: list.name,
					}}
					onDelete={async () => {
						if (!canDeleteList(list)) return false
						const ok = await reminders.deleteList(list.id)
						if (!ok) return false
						if (selectedListId === list.id) {
							const fallbackList = reminders.defaultList ?? reminders.lists[0] ?? null
							if (fallbackList) {
								selectList(fallbackList.id)
							} else {
								void goto(resolve('/reminders'), {
									replaceState: true,
								})
							}
						}
						return true
					}}
				/>
			{/if}
		</PopupMenu>
	</div>
{/snippet}

{#snippet sectionHeader(label: string, count: number, open: boolean, onToggle: () => void)}
	<button
		type="button"
		class="text-foreground/70 hover:text-foreground/90 flex w-full cursor-pointer items-center gap-1.5 bg-transparent px-2 py-2 text-xs font-semibold tracking-wide uppercase transition-colors duration-150"
		onclick={onToggle}
		aria-expanded={open}
	>
		<ChevronDown class="h-3 w-3 transition-transform duration-200 {open ? '' : '-rotate-90'}" />
		{label}
		<span class="text-foreground/50 font-normal">({count})</span>
	</button>
{/snippet}

{#snippet mobileHeading()}
	<MasterSidebarHeader icon={ListBullet} label="lists" iconColor="text-foreground/70" isMobile />
{/snippet}

<div class="flex h-full min-h-0 flex-1 flex-col">
	{#if !isMobile}
		<MasterSidebarHeader icon={ListBullet} label="lists" iconColor="text-foreground/70">
			{#snippet actions()}
				<button
					type="button"
					bind:this={sortButtonEl}
					class="text-foreground/80 hover:text-foreground flex h-12 w-12 cursor-pointer items-center justify-center bg-transparent transition-transform duration-150 hover:scale-[1.05] active:scale-[0.97]"
					onclick={toggleSortMenu}
					aria-label="sort lists"
					aria-haspopup="menu"
					aria-expanded={isSortMenuOpen}
				>
					<SortIcon class="h-5 w-5" />
				</button>
				<PopupMenu
					open={isSortMenuOpen}
					anchorEl={sortButtonEl}
					onClose={closeSortMenu}
					class="min-w-52"
				>
					<MenuSectionHeader icon={SortIcon}>sort lists</MenuSectionHeader>
					{#each sortOptions as option (option.value)}
						<MenuItem
							selected={reminders.listsSortMode === option.value}
							onclick={() => {
								reminders.setListsSortMode(option.value)
								closeSortMenu()
							}}
						>
							{#snippet iconSnippet()}<SortIcon
									value={option.value}
									class="size-full"
								/>{/snippet}
							{option.label}
						</MenuItem>
					{/each}
				</PopupMenu>
				<button
					type="button"
					class="text-foreground/80 hover:text-foreground flex h-12 w-12 cursor-pointer items-center justify-center bg-transparent transition-transform duration-150 hover:scale-[1.05] active:scale-[0.97]"
					onclick={handleCreateList}
					aria-label="create list"
				>
					<Plus class="h-6 w-6" />
				</button>
			{/snippet}
		</MasterSidebarHeader>
	{/if}

	{#if isLoading}
		{#if isMobile}{@render mobileHeading()}{/if}
		<div class="flex flex-col gap-1 px-3 {isMobile ? '' : 'pt-2'}">
			<Skeleton shape="row" count={6} lines={1} height="3.25rem" radius="pill" />
		</div>
	{:else}
		<nav class="flex min-h-0 flex-1 flex-col">
			<div class="flex min-h-0 flex-1 flex-col gap-1">
				{#if lists.length === 0}
					{#if isMobile}{@render mobileHeading()}{/if}
					<div class="flex min-h-0 flex-1 flex-col px-2">
						<EmptyState label="no lists yet" compact class="flex-1" />
					</div>
				{:else}
					<div bind:this={listShellEl} class="relative min-h-0 flex-1 overflow-hidden">
						<SvelteVirtualList
							items={listRows}
							defaultEstimatedItemHeight={58}
							bufferSize={16}
							containerClass="relative h-full min-h-0 w-full overflow-hidden"
							viewportClass="reminder-lists-sidebar-viewport absolute inset-0 w-full overflow-y-auto"
							contentClass="relative min-h-full w-full"
							itemsClass="absolute top-0 left-0 flex w-full flex-col gap-1 {isMobile
								? ''
								: 'pt-2'}"
						>
							{#snippet renderItem(row, rowIndex)}
								{#if row.kind === 'header'}
									{@render mobileHeading()}
								{:else}
									<div
										class="px-3 {rowIndex === listRows.length - 1
											? isMobile
												? 'pb-10'
												: 'pb-6'
											: ''}"
									>
										{#if row.kind === 'section'}
											{@render sectionHeader(
												row.label,
												row.count,
												row.open,
												() => {
													if (row.id === 'my') myListsOpen = !myListsOpen
													else sharedListsOpen = !sharedListsOpen
												}
											)}
										{:else}
											<div class="-mx-3">
												{@render listItem(row.list)}
											</div>
										{/if}
									</div>
								{/if}
							{/snippet}
						</SvelteVirtualList>
						{#if !isMobile}
							<ScrollTopShadow target={listViewportEl} />
						{/if}
						<FloatingScrollTopButton target={listViewportEl} />
					</div>
				{/if}
			</div>
		</nav>
	{/if}
</div>

<ReminderListPropertiesModal
	open={editListId !== null}
	list={editList}
	onClose={() => {
		editListId = null
	}}
/>

<ReminderListCreateModal
	open={isCreateListOpen}
	onClose={closeCreateListModal}
	onCreated={(list) => selectList(list.id)}
/>
