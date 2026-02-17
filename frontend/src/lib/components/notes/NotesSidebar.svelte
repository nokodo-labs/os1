<script lang="ts">
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import DeleteButton from '$lib/components/DeleteButton.svelte'
	import ArrowsUpDown from '$lib/components/icons/ArrowsUpDown.svelte'
	import Document from '$lib/components/icons/Document.svelte'
	import EllipsisHorizontal from '$lib/components/icons/EllipsisHorizontal.svelte'
	import Plus from '$lib/components/icons/Plus.svelte'
	import Share from '$lib/components/icons/Share.svelte'
	import { MenuItem } from '$lib/components/primitives'
	import SidebarListItem from '$lib/components/SidebarListItem.svelte'
	import { device } from '$lib/stores/device.svelte'
	import { notes, type NotesSortMode } from '$lib/stores/notes.svelte'
	import { scale } from 'svelte/transition'

	interface Props {
		selectedNoteId: string | null
		isMobile?: boolean
	}

	let { selectedNoteId, isMobile = false }: Props = $props()

	let openMenuId: string | null = $state(null)
	let menuFixedTop = $state(0)
	let menuFixedRight = $state(0)

	// sort menu state
	let isSortMenuOpen = $state(false)
	let sortMenuEl: HTMLDivElement | null = $state(null)
	let sortButtonEl: HTMLButtonElement | null = $state(null)

	const sortOptions: { value: NotesSortMode; label: string }[] = [
		{ value: 'updated_at:desc', label: 'last updated' },
		{ value: 'updated_at:asc', label: 'first updated' },
		{ value: 'title:asc', label: 'title a-z' },
		{ value: 'title:desc', label: 'title z-a' },
	]

	function closeSortMenu() {
		isSortMenuOpen = false
		sortMenuEl = null
	}

	function toggleSortMenu() {
		isSortMenuOpen = !isSortMenuOpen
	}

	$effect(() => {
		void notes.load()
	})

	// close menu on outside click/escape
	$effect(() => {
		if (!openMenuId && !isSortMenuOpen) return

		const onPointerDown = (event: PointerEvent) => {
			const target = event.target as HTMLElement
			if (openMenuId && target.closest('[data-note-menu]')) return
			if (isSortMenuOpen && sortMenuEl && event.composedPath().includes(sortMenuEl)) return
			if (isSortMenuOpen && sortButtonEl && event.composedPath().includes(sortButtonEl))
				return
			openMenuId = null
			closeSortMenu()
		}

		const onKeyDown = (event: KeyboardEvent) => {
			if (event.key === 'Escape') {
				event.preventDefault()
				openMenuId = null
				closeSortMenu()
			}
		}

		window.addEventListener('pointerdown', onPointerDown)
		window.addEventListener('keydown', onKeyDown)
		return () => {
			window.removeEventListener('pointerdown', onPointerDown)
			window.removeEventListener('keydown', onKeyDown)
		}
	})

	const noteList = $derived(notes.all)

	function labelForNote(title: string): string {
		const trimmed = title.trim()
		return trimmed.length > 0 ? trimmed : 'untitled'
	}

	async function createNote() {
		const created = await notes.create()
		if (created) {
			await goto(resolve(`/notes/${created.id}`), { keepFocus: true, noScroll: true })
		}
	}

	function openNote(noteId: string) {
		void goto(resolve(`/notes/${noteId}`), { keepFocus: true, noScroll: true })
	}

	function handleShare(noteId: string): void {
		openMenuId = null
		// TODO: implement share modal for notes
		console.log('share note:', noteId)
	}

	async function handleDelete(noteId: string): Promise<void> {
		const wasSelected = selectedNoteId === noteId
		const remaining = noteList.filter((n) => n.id !== noteId)
		await notes.remove(noteId)
		// navigate away if the deleted note is currently selected
		if (wasSelected) {
			if (remaining.length > 0) {
				void goto(resolve(`/notes/${remaining[0].id}`), { keepFocus: true, noScroll: true })
			} else {
				void goto(resolve('/notes'), { keepFocus: true, noScroll: true })
			}
		}
	}
</script>

<div
	class="flex min-h-0 flex-col {isMobile
		? 'min-h-[calc(100vh-var(--chrome-island-offset,0px)-var(--spacing-island-content)-2.5rem)]'
		: 'h-full'}"
	style="gap: var(--spacing-header-content);"
>
	<header
		class="{isMobile
			? 'mt-0'
			: 'mt-7'} flex max-h-22 items-center justify-between gap-3 px-2 py-5 pb-6"
	>
		<div class="flex min-w-0 items-center gap-3" style="color: var(--accent-primary);">
			<Document variant="solid" class="h-6 w-6" />
			<h2 class="min-w-0 truncate text-xl font-semibold tracking-wide text-white/90">
				notes
			</h2>
		</div>
		{#if !isMobile}
			<div class="flex items-center gap-1">
				<div class="relative">
					<button
						type="button"
						bind:this={sortButtonEl}
						class="flex h-12 w-12 cursor-pointer items-center justify-center bg-transparent text-white/80 transition-transform duration-150 hover:scale-[1.05] hover:text-white active:scale-[0.97]"
						onclick={toggleSortMenu}
						aria-label="sort notes"
						aria-haspopup="menu"
						aria-expanded={isSortMenuOpen}
					>
						<ArrowsUpDown variant="solid" class="h-5 w-5" />
					</button>

					{#if isSortMenuOpen}
						<div
							transition:scale={{ duration: 160, start: 0.96, opacity: 0 }}
							bind:this={sortMenuEl}
							role="menu"
							class="animate-popup-right rounded-container absolute top-full right-0 z-50 mt-2 w-44 border border-white/10 bg-black/70 p-2 shadow-[0_24px_48px_rgba(12,10,30,0.55)] backdrop-blur"
						>
							{#each sortOptions as option (option.value)}
								<button
									type="button"
									role="menuitem"
									class="rounded-pill flex w-full cursor-pointer items-center border-none bg-transparent px-3 py-2 text-left text-sm text-white/80 transition-colors duration-150 hover:bg-white/10"
									onclick={() => {
										notes.sortMode = option.value
										closeSortMenu()
									}}
								>
									{option.label}{notes.sortMode === option.value ? ' ✓' : ''}
								</button>
							{/each}
						</div>
					{/if}
				</div>
				<button
					type="button"
					onclick={createNote}
					class="flex h-12 w-12 cursor-pointer items-center justify-center bg-transparent text-white/80 transition-transform duration-150 hover:scale-[1.05] hover:text-white active:scale-[0.97]"
					aria-label="create note"
				>
					<Plus class="h-6 w-6" />
				</button>
			</div>
		{/if}
	</header>

	<nav class="flex min-h-0 flex-1 flex-col overflow-y-auto px-2 pb-2">
		{#if noteList.length === 0}
			<div class="flex flex-1 items-center justify-center">
				<div
					class="rounded-container w-full overflow-hidden border border-white/14 bg-white/5 p-3 text-center text-sm whitespace-nowrap text-white/55"
				>
					no notes yet
				</div>
			</div>
		{:else}
			<div class="space-y-1">
				{#each noteList as note (note.id)}
					<div class="group/note relative">
						<SidebarListItem
							selected={selectedNoteId === note.id}
							onSelect={() => openNote(note.id)}
							actionsVisibility={device.isTouch ? 'always' : 'hover'}
							showChevron={true}
						>
							<span class="flex min-w-0 flex-col">
								<span
									class="min-w-0 truncate text-[0.95rem] font-medium text-white/90"
								>
									{labelForNote(note.title)}
								</span>
								<span class="min-w-0 truncate text-xs text-white/55">
									{note.content.trim().length > 0
										? note.content.trim().slice(0, 60)
										: 'empty note'}
								</span>
							</span>

							{#snippet actions()}
								<button
									type="button"
									data-note-menu
									class="flex h-9 w-9 cursor-pointer items-center justify-center rounded-full border border-transparent bg-transparent text-white/70 transition-all duration-150 hover:bg-white/10 hover:text-white"
									onclick={(e) => {
										e.stopPropagation()
										if (openMenuId !== note.id) {
											const rect = (
												e.currentTarget as HTMLElement
											).getBoundingClientRect()
											menuFixedTop = rect.bottom + 4
											menuFixedRight = window.innerWidth - rect.right
										}
										openMenuId = openMenuId === note.id ? null : note.id
									}}
									aria-label="note options"
								>
									<EllipsisHorizontal class="h-5 w-5" />
								</button>
							{/snippet}
						</SidebarListItem>

						{#if openMenuId === note.id}
							<div
								data-note-menu
								transition:scale={{ duration: 160, start: 0.96, opacity: 0 }}
								class="liquid-metal rounded-container animate-popup-right fixed z-50 min-w-44 p-2 shadow-[0_24px_48px_rgba(12,10,30,0.55)]"
								style="top: {menuFixedTop}px; right: {menuFixedRight}px;"
							>
								<MenuItem onclick={() => handleShare(note.id)}>
									{#snippet icon()}<Share class="h-4 w-4" />{/snippet}
									share
								</MenuItem>
								<DeleteButton
									onDelete={() => handleDelete(note.id)}
									modalText={{
										title: 'delete note?',
										description: 'this action cannot be undone.',
									}}
									onTrigger={() => {
										openMenuId = null
									}}
								/>
							</div>
						{/if}
					</div>
				{/each}
			</div>
		{/if}
	</nav>
</div>
