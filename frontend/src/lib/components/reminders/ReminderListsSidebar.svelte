<script lang="ts">
	import { browser } from '$app/environment'
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import DeleteButton from '$lib/components/DeleteButton.svelte'
	import ListBullet from '$lib/components/icons/ListBullet.svelte'
	import Plus from '$lib/components/icons/Plus.svelte'
	import SortIcon from '$lib/components/icons/SortIcon.svelte'
	import NokodoLoader from '$lib/components/NokodoLoader.svelte'
	import PageTitle from '$lib/components/PageTitle.svelte'
	import { MenuItem, PopupMenu } from '$lib/components/primitives'
	import ReminderListRow from '$lib/components/reminders/ReminderListRow.svelte'
	import { modals } from '$lib/stores/modals.svelte'
	import { reminders, type ReminderListsSortMode } from '$lib/stores/reminders.svelte'
	import { tick } from 'svelte'
	import InfoCircle from '../icons/InfoCircle.svelte'
	import Share from '../icons/Share.svelte'
	import EditReminderListModal from './EditReminderListModal.svelte'

	interface Props {
		selectedListId: string | null | undefined
		isLoading?: boolean
		isMobile?: boolean
	}

	let { selectedListId, isLoading = false, isMobile = false }: Props = $props()

	const lists = $derived(reminders.lists)

	let isAddingList = $state(false)
	let newListName = $state('')
	let isSubmittingList = $state(false)
	let addListInputEl: HTMLInputElement | null = $state(null)

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

	$effect(() => {
		if (!browser) return
		const handler = () => {
			void startInlineAddList()
		}
		window.addEventListener('reminders:list-add', handler)
		return () => window.removeEventListener('reminders:list-add', handler)
	})
</script>

<div class="flex h-full min-h-0 flex-col" style="gap: var(--spacing-header-content);">
	<header
		class="{isMobile
			? 'mt-0'
			: 'mt-7'} flex max-h-22 items-center justify-between gap-3 px-2 py-5 pb-6"
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
					<SortIcon value={reminders.listsSortMode} class="h-5 w-5" />
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
						<SortIcon value={reminders.listsSortMode} class="h-3.5 w-3.5" />
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
		<nav class="min-h-0 flex-1 overflow-y-auto px-2 pb-2">
			<div class="space-y-1">
				{#each lists as list (list.id)}
					<div class="relative">
						<ReminderListRow
							title={list.name}
							count={list.pending_count}
							selected={selectedListId === list.id}
							leading={{ type: 'emoji', emoji: list.icon ?? '📋', color: list.color }}
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
							onClose={closeListMenu}
							data-reminders-list-menu
						>
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
								{#snippet icon()}<Share class="h-4 w-4" />{/snippet}
								share
							</MenuItem>
							<MenuItem
								onclick={(event) => {
									event.stopPropagation()
									closeListMenu()
									editListId = list.id
								}}
							>
								{#snippet icon()}<InfoCircle class="h-4 w-4" />{/snippet}
								properties
							</MenuItem>
							{#if !list.is_default}
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
											const ok = await reminders.deleteList(list.id)
											if (!ok) return false
											if (selectedListId === list.id) {
												const fallbackList =
													reminders.defaultList ??
													reminders.lists[0] ??
													null
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
				{/each}

				{#if isAddingList}
					<div
						class="rounded-pill border-foreground/14 bg-foreground/6 border px-3 py-2.5"
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

<EditReminderListModal
	open={editListId !== null}
	list={editList}
	onClose={() => {
		editListId = null
	}}
/>
