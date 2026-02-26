<script lang="ts">
	import { browser } from '$app/environment'
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import { apiClient } from '$lib/api/client'
	import PageTitle from '$lib/components/common/PageTitle.svelte'
	import DeleteButton from '$lib/components/DeleteButton.svelte'
	import ArrowsUpDown from '$lib/components/icons/ArrowsUpDown.svelte'
	import ListBullet from '$lib/components/icons/ListBullet.svelte'
	import Plus from '$lib/components/icons/Plus.svelte'
	import NokodoLoader from '$lib/components/NokodoLoader.svelte'
	import { PopupMenu } from '$lib/components/primitives'
	import ReminderListRow from '$lib/components/reminders/ReminderListRow.svelte'
	import { reminders, type ReminderListsSortMode } from '$lib/stores/reminders.svelte'
	import { tick } from 'svelte'
	import InfoCircle from '../icons/InfoCircle.svelte'
	import EditReminderListModal from './EditReminderListModal.svelte'

	interface Props {
		selectedListId: string | null | undefined
		isLoading?: boolean
		isMobile?: boolean
	}

	let { selectedListId, isLoading = false, isMobile = false }: Props = $props()

	const lists = $derived(reminders.lists)
	const defaultCounts = $derived(reminders.defaultCounts)

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

	function selectList(listId: string | null) {
		const url = listId ? `/reminders/lists/${listId}` : '/reminders'
		// @ts-expect-error resolve typing is narrower than our constructed URL
		void goto(resolve(url as never), { keepFocus: true, noScroll: true })
	}

	function prefetchList(listId: string | null): void {
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

	async function deleteList(listId: string): Promise<number | null> {
		const { response } = await apiClient().DELETE('/v1/reminders/lists/{list_id}', {
			params: { path: { list_id: listId } },
		})
		return response.status
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
		<PageTitle icon={ListBullet} label="lists" iconColor="text-white/70" tag="h2" />
		{#if !isMobile}
			<div class="flex items-center gap-1">
				<button
					type="button"
					bind:this={sortButtonEl}
					class="flex h-12 w-12 cursor-pointer items-center justify-center bg-transparent text-white/80 transition-transform duration-150 hover:scale-[1.05] hover:text-white active:scale-[0.97]"
					onclick={toggleSortMenu}
					aria-label="sort lists"
					aria-haspopup="menu"
					aria-expanded={isSortMenuOpen}
				>
					<ArrowsUpDown variant="solid" class="h-5 w-5" />
				</button>
				<PopupMenu open={isSortMenuOpen} anchorEl={sortButtonEl} onClose={closeSortMenu}>
					{#each sortOptions as option (option.value)}
						<button
							type="button"
							role="menuitem"
							class="rounded-pill flex w-full cursor-pointer items-center border-none bg-transparent px-3 py-2 text-left text-sm text-white/80 transition-colors duration-150 hover:bg-white/10"
							onclick={() => {
								reminders.setListsSortMode(option.value)
								closeSortMenu()
							}}
						>
							{option.label}{reminders.listsSortMode === option.value ? ' ✓' : ''}
						</button>
					{/each}
				</PopupMenu>
				<button
					type="button"
					class="flex h-12 w-12 cursor-pointer items-center justify-center bg-transparent text-white/80 transition-transform duration-150 hover:scale-[1.05] hover:text-white active:scale-[0.97]"
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
				<ReminderListRow
					title="reminders"
					count={defaultCounts.pending_count}
					selected={selectedListId === null}
					leading={{ type: 'checkbox' }}
					onPrefetch={() => prefetchList(null)}
					onSelect={() => selectList(null)}
				/>

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
							<button
								type="button"
								class="rounded-pill flex w-full cursor-pointer items-center gap-2 border-none bg-transparent px-3 py-2 text-left text-sm text-white/80 transition-colors duration-150 hover:bg-white/10"
								onclick={(event) => {
									event.stopPropagation()
									closeListMenu()
									editListId = list.id
								}}
							>
								<InfoCircle class="h-4 w-4" />
								properties
							</button>
							<div class="my-1 h-px w-full bg-white/10"></div>
							<div class="mt-1">
								<DeleteButton
									confirm={true}
									stopPropagation={true}
									modalText={{
										title: 'delete list?',
										description: list.name,
									}}
									onDelete={async () => {
										const status = await deleteList(list.id)
										if (status !== 204) return false

										await reminders.loadLists({ force: true })
										if (selectedListId === list.id) {
											selectList(null)
										}
										return true
									}}
								/>
							</div>
						</PopupMenu>
					</div>
				{/each}

				{#if isAddingList}
					<div class="rounded-pill border border-white/14 bg-white/6 px-3 py-2.5">
						<input
							bind:this={addListInputEl}
							type="text"
							class="w-full bg-transparent text-[0.95rem] font-medium text-white/90 outline-none placeholder:text-white/40"
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
