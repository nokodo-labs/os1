<script lang="ts">
	import { browser } from '$app/environment'
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import DeleteButton from '$lib/components/DeleteButton.svelte'
	import EmptyState from '$lib/components/EmptyState.svelte'
	import FloatingScrollTopButton from '$lib/components/FloatingScrollTopButton.svelte'
	import ChevronDown from '$lib/components/icons/ChevronDown.svelte'
	import ListBullet from '$lib/components/icons/ListBullet.svelte'
	import Plus from '$lib/components/icons/Plus.svelte'
	import SortIcon from '$lib/components/icons/SortIcon.svelte'
	import NokodoLoader from '$lib/components/NokodoLoader.svelte'
	import PageTitle from '$lib/components/PageTitle.svelte'
	import { MenuItem, PopupMenu } from '$lib/components/primitives'
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
		canShareAccessLevel,
		resourceAccess,
	} from '$lib/stores/resourceAccess.svelte'
	import { session } from '$lib/stores/session.svelte'
	import { byAuthor } from '$lib/utils/resourceAuthors'
	import SvelteVirtualList from '@humanspeak/svelte-virtual-list'
	import { tick } from 'svelte'
	import InfoCircle from '../icons/InfoCircle.svelte'
	import Share from '../icons/Share.svelte'
	import ReminderListPropertiesModal from './ReminderListPropertiesModal.svelte'

	interface Props {
		selectedListId: string | null | undefined
		isLoading?: boolean
		isMobile?: boolean
	}

	let { selectedListId, isLoading = false, isMobile = false }: Props = $props()
	const sidebarListEdgeStyle = $derived(
		isMobile
			? 'width: 100%;'
			: 'margin-left: calc(0px - var(--spacing-page-x)); margin-right: calc(0px - var(--spacing-page-x)); width: calc(100% + var(--spacing-page-x) + var(--spacing-page-x));'
	)

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
		| { kind: 'section'; id: 'my' | 'shared'; label: string; count: number; open: boolean }
		| { kind: 'list'; id: string; list: ReminderListWithCounts }

	const listRows = $derived.by((): ReminderListSidebarRow[] => {
		if (sharedLists.length === 0) {
			return myLists.map((list) => ({ kind: 'list', id: list.id, list }))
		}

		const rows: ReminderListSidebarRow[] = []
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

	let isAddingList = $state(false)
	let newListName = $state('')
	let isSubmittingList = $state(false)
	let addListInputEl: HTMLInputElement | null = $state(null)
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

	async function startInlineAddList() {
		isAddingList = true
		newListName = ''
		await tick()
		addListInputEl?.focus()
	}

	async function submitInlineAddList() {
		if (isSubmittingList) return // guard against double submit
		const name = newListName.trim()
		if (name === '') {
			isAddingList = false
			newListName = ''
			return
		}

		isSubmittingList = true
		newListName = '' // clear immediately to prevent onblur re-trigger
		isAddingList = false

		const created = await reminders.createList({ name })
		isSubmittingList = false
		if (created) selectList(created.id)
	}

	function handleCreateList() {
		void startInlineAddList()
	}

	function toggleListMenu(listId: string, buttonEl?: HTMLButtonElement | null) {
		const opening = openListMenuId !== listId
		openListMenuId = opening ? listId : null
		if (buttonEl) listMenuButtonEl = buttonEl
	}

	function closeListMenu() {
		openListMenuId = null
		listMenuButtonEl = null
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

	function canShareList(list: (typeof lists)[0]): boolean {
		return canShareAccessLevel(listAccessLevel(list))
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
		for (const project of projects.list) {
			void resourceAccess.ensure('project', project.id, project.owner_id)
		}
	})

	$effect(() => {
		if (!browser) return
		const handler = () => {
			void startInlineAddList()
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
	<div class="relative px-3">
		<ReminderListRow
			title={list.name}
			subtitle={authorSubtitle(list)}
			count={list.pending_count}
			selected={selectedListId === list.id}
			leading={{ type: 'emoji', emoji: list.icon ?? '📋', color: list.color }}
			onPrefetch={() => prefetchList(list.id)}
			onSelect={() => selectList(list.id)}
			onMenu={canEditList(list) || canShareList(list) || canDeleteList(list)
				? (event) => {
						const el = event.currentTarget
						if (el instanceof HTMLButtonElement) toggleListMenu(list.id, el)
						else toggleListMenu(list.id, null)
					}
				: undefined}
		/>

		<PopupMenu
			open={openListMenuId === list.id}
			anchorEl={listMenuButtonEl}
			onClose={closeListMenu}
			data-reminders-list-menu
		>
			{#if canShareList(list)}
				<MenuItem
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
					{#snippet icon()}<Share class="size-full" strokeWidth="2.1" />{/snippet}
					share
				</MenuItem>
			{/if}
			{#if canEditList(list)}
				<MenuItem
					onclick={(event) => {
						event.stopPropagation()
						closeListMenu()
						editListId = list.id
					}}
				>
					{#snippet icon()}<InfoCircle variant="solid" class="size-full" />{/snippet}
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
				<div class="bg-foreground/10 my-1 h-px w-full"></div>
				<div class="mt-1">
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
								const fallbackList =
									reminders.defaultList ?? reminders.lists[0] ?? null
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
				</div>
			{/if}
		</PopupMenu>
	</div>
{/snippet}

{#snippet sectionHeader(label: string, count: number, open: boolean, onToggle: () => void)}
	<button
		type="button"
		class="text-foreground/70 hover:text-foreground/90 flex w-full cursor-pointer items-center gap-1.5 bg-transparent px-1 py-2 text-xs font-semibold tracking-wide uppercase transition-colors duration-150"
		onclick={onToggle}
		aria-expanded={open}
	>
		<ChevronDown class="h-3 w-3 transition-transform duration-200 {open ? '' : '-rotate-90'}" />
		{label}
		<span class="text-foreground/50 font-normal">({count})</span>
	</button>
{/snippet}

<div class="flex h-full min-h-0 flex-col">
	<header
		class="{isMobile
			? 'mt-0'
			: 'mt-7'} relative z-10 flex max-h-22 items-center justify-between gap-3 px-2 pt-5 pb-2"
	>
		<PageTitle icon={ListBullet} label="lists" iconColor="text-foreground/70" tag="h2" />
		{#if !isMobile}
			<div class="flex items-center gap-1">
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
					<div
						class="text-foreground/50 flex items-center gap-2 px-3 pt-1 pb-2 text-xs font-semibold tracking-[0.08em] uppercase"
					>
						<SortIcon class="h-3.5 w-3.5" />
						sort lists
					</div>
					{#each sortOptions as option (option.value)}
						<MenuItem
							selected={reminders.listsSortMode === option.value}
							onclick={() => {
								reminders.setListsSortMode(option.value)
								closeSortMenu()
							}}
						>
							{#snippet icon()}<SortIcon
									value={option.value}
									class="h-4 w-4"
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
			</div>
		{/if}
	</header>

	{#if isLoading}
		<div class="flex flex-1 items-center justify-center">
			<NokodoLoader className="opacity-70" expanded={false} />
		</div>
	{:else}
		<nav class="flex min-h-0 flex-1 flex-col">
			<div class="flex min-h-0 flex-1 flex-col gap-1">
				{#if lists.length === 0}
					<div class="px-2">
						<EmptyState label="no lists yet" compact />
					</div>
				{:else}
					<div
						bind:this={listShellEl}
						class="relative min-h-0 flex-1 overflow-hidden"
						style={sidebarListEdgeStyle}
					>
						<SvelteVirtualList
							items={listRows}
							defaultEstimatedItemHeight={58}
							bufferSize={16}
							containerClass="relative h-full min-h-0 w-full overflow-hidden"
							viewportClass="reminder-lists-sidebar-viewport absolute inset-0 w-full overflow-y-auto"
							contentClass="relative min-h-full w-full"
							itemsClass="absolute top-0 left-0 flex w-full flex-col gap-1 pt-2"
						>
							{#snippet renderItem(row, rowIndex)}
								<div class="px-3 {rowIndex === listRows.length - 1 ? 'pb-5' : ''}">
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
							{/snippet}
						</SvelteVirtualList>
						<ScrollTopShadow target={listViewportEl} />
						<FloatingScrollTopButton target={listViewportEl} />
					</div>
				{/if}

				{#if isAddingList}
					<div
						class="rounded-pill border-foreground/14 bg-foreground/6 mx-3 border px-3 py-2.5"
					>
						<input
							bind:this={addListInputEl}
							type="text"
							class="text-foreground/90 placeholder:text-foreground/40 w-full bg-transparent text-[0.95rem] font-medium outline-none"
							placeholder="new list"
							autocomplete="off"
							bind:value={newListName}
							onkeydown={(event) => {
								if (event.key === 'Enter') {
									event.preventDefault()
									void submitInlineAddList()
									return
								}
								if (event.key === 'Escape') {
									event.preventDefault()
									isAddingList = false
									newListName = ''
								}
							}}
							onblur={() => {
								if (newListName.trim() !== '') {
									void submitInlineAddList()
								} else {
									isAddingList = false
									newListName = ''
								}
							}}
						/>
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
