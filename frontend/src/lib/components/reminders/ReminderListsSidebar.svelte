<script lang="ts">
	import { browser } from '$app/environment'
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import { apiClient } from '$lib/api/client'
	import DeleteButton from '$lib/components/DeleteButton.svelte'
	import ListBullet from '$lib/components/icons/ListBullet.svelte'
	import Plus from '$lib/components/icons/Plus.svelte'
	import NokodoLoader from '$lib/components/NokodoLoader.svelte'
	import ReminderListRow from '$lib/components/reminders/ReminderListRow.svelte'
	import { reminders } from '$lib/stores/reminders.svelte'
	import { tick } from 'svelte'
	import { scale } from 'svelte/transition'
	import Pencil from '../icons/Pencil.svelte'
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
	let addListInputEl: HTMLInputElement | null = $state(null)

	let openListMenuId = $state<string | null>(null)
	let listMenuEl: HTMLDivElement | null = $state(null)
	let listMenuButtonEl: HTMLButtonElement | null = $state(null)

	let editListId = $state<string | null>(null)
	const editList = $derived(lists.find((l) => l.id === editListId) ?? null)

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
		const name = newListName.trim()
		if (name === '') {
			isAddingList = false
			newListName = ''
			return
		}

		const created = await reminders.createList({ name })
		isAddingList = false
		newListName = ''
		if (created) selectList(created.id)
	}

	function handleCreateList() {
		void startInlineAddList()
	}

	function toggleListMenu(listId: string, buttonEl?: HTMLButtonElement | null) {
		openListMenuId = openListMenuId === listId ? null : listId
		if (buttonEl) listMenuButtonEl = buttonEl
	}

	function closeListMenu() {
		openListMenuId = null
		listMenuEl = null
		listMenuButtonEl = null
	}

	async function deleteList(listId: string): Promise<number | null> {
		const { response } = await apiClient().DELETE('/v1/reminders/lists/{list_id}', {
			params: { path: { list_id: listId } },
		})
		return response.status
	}

	$effect(() => {
		if (!openListMenuId) return

		const onKeyDown = (event: KeyboardEvent) => {
			if (event.key !== 'Escape') return
			event.preventDefault()
			closeListMenu()
		}

		const onPointerDown = (event: PointerEvent) => {
			const path = event.composedPath()
			if (listMenuEl && path.includes(listMenuEl)) return
			if (listMenuButtonEl && path.includes(listMenuButtonEl)) return
			closeListMenu()
		}

		window.addEventListener('keydown', onKeyDown)
		window.addEventListener('pointerdown', onPointerDown)
		return () => {
			window.removeEventListener('keydown', onKeyDown)
			window.removeEventListener('pointerdown', onPointerDown)
		}
	})

	$effect(() => {
		if (!browser) return
		const handler = () => {
			void startInlineAddList()
		}
		window.addEventListener('nokodo:reminders:list-add', handler)
		return () => window.removeEventListener('nokodo:reminders:list-add', handler)
	})
</script>

<div class="flex h-full min-h-0 flex-col gap-8">
	<header
		class="{isMobile
			? 'mt-0'
			: 'mt-7'} flex max-h-22 items-center justify-between gap-3 px-2 py-5 pb-6"
	>
		<div class="flex min-w-0 items-center gap-3">
			<ListBullet class="h-6 w-6 text-white/70" />
			<h2 class="min-w-0 truncate text-xl font-semibold tracking-wide text-white/90">
				lists
			</h2>
		</div>
		<button
			type="button"
			class="rounded-circle inline-flex h-9 w-9 cursor-pointer items-center justify-center border border-transparent bg-transparent text-white/80 transition-all duration-200 hover:border-white/10 hover:bg-white/5 hover:text-white"
			onclick={handleCreateList}
			aria-label="create list"
		>
			<Plus class="h-6 w-6" />
		</button>
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

						{#if openListMenuId === list.id}
							<div
								transition:scale={{ duration: 160, start: 0.96, opacity: 0 }}
								bind:this={listMenuEl}
								data-reminders-list-menu
								class="animate-popup-right rounded-box absolute top-full right-2 z-50 mt-2 w-52 border border-white/10 bg-black/70 p-2 shadow-[0_24px_48px_rgba(12,10,30,0.55)] backdrop-blur"
							>
								<button
									type="button"
									class="rounded-pill flex w-full cursor-pointer items-center border-none bg-transparent px-3 py-2 text-left text-sm text-white/80 transition-colors duration-150 hover:bg-white/10"
									onclick={(event) => {
										event.stopPropagation()
										closeListMenu()
										editListId = list.id
									}}
								>
									<Pencil variant="solid" class="h-4 w-4" />
									&nbsp; edit
								</button>
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
							</div>
						{/if}
					</div>
				{/each}

				{#if isAddingList}
					<div class="rounded-pill border border-white/10 bg-white/6 px-3 py-2.5">
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
