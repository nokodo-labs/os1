<script lang="ts">
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import ShimmerText from '$lib/components/effects/ShimmerText.svelte'
	import ArrowsUpDown from '$lib/components/icons/ArrowsUpDown.svelte'
	import ChevronDown from '$lib/components/icons/ChevronDown.svelte'
	import Document from '$lib/components/icons/Document.svelte'
	import EllipsisHorizontal from '$lib/components/icons/EllipsisHorizontal.svelte'
	import InfoCircle from '$lib/components/icons/InfoCircle.svelte'
	import Plus from '$lib/components/icons/Plus.svelte'
	import Share from '$lib/components/icons/Share.svelte'
	import Trash from '$lib/components/icons/Trash.svelte'
	import BaseModal from '$lib/components/modals/BaseModal.svelte'
	import { MenuItem, PopupMenu } from '$lib/components/primitives'
	import SidebarListItem from '$lib/components/SidebarListItem.svelte'
	import { device } from '$lib/stores/device.svelte'
	import { notes, type NotesSortMode } from '$lib/stores/notes.svelte'
	import { session } from '$lib/stores/session.svelte'

	interface Props {
		selectedNoteId: string | null
		isMobile?: boolean
	}

	let { selectedNoteId, isMobile = false }: Props = $props()

	let openMenuId: string | null = $state(null)
	let menuAnchorEl = $state<HTMLElement | null>(null)

	// delete confirmation modal state (managed here so it survives menu unmount)
	let deleteTargetId: string | null = $state(null)
	let isDeleting = $state(false)
	let deleteError: string | null = $state(null)

	// sort menu state
	let isSortMenuOpen = $state(false)
	let sortButtonEl: HTMLButtonElement | null = $state(null)

	const sortOptions: { value: NotesSortMode; label: string }[] = [
		{ value: 'updated_at:desc', label: 'last updated' },
		{ value: 'updated_at:asc', label: 'first updated' },
		{ value: 'title:asc', label: 'title a-z' },
		{ value: 'title:desc', label: 'title z-a' },
	]

	function closeSortMenu() {
		isSortMenuOpen = false
	}

	function toggleSortMenu() {
		isSortMenuOpen = !isSortMenuOpen
	}

	$effect(() => {
		void notes.load()
	})

	const noteList = $derived(notes.all)

	const currentUserId = $derived(session.currentUser?.id ?? null)
	const myNotes = $derived(
		currentUserId ? noteList.filter((n) => n.userId === currentUserId) : noteList
	)
	const sharedNotes = $derived(
		currentUserId ? noteList.filter((n) => n.userId !== currentUserId) : []
	)

	let myNotesOpen = $state(true)
	let sharedNotesOpen = $state(true)

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

	function handleProperties(noteId: string): void {
		openMenuId = null
		// TODO: implement properties modal for notes
		console.log('show properties for note:', noteId)
	}

	function requestDelete(noteId: string): void {
		openMenuId = null
		deleteError = null
		deleteTargetId = noteId
	}

	async function confirmDelete(): Promise<void> {
		if (!deleteTargetId) return
		const noteId = deleteTargetId
		isDeleting = true
		deleteError = null
		try {
			const wasSelected = selectedNoteId === noteId
			const remaining = noteList.filter((n) => n.id !== noteId)
			const ok = await notes.remove(noteId)
			if (!ok) {
				deleteError = 'could not delete'
				return
			}
			deleteTargetId = null
			if (wasSelected) {
				if (remaining.length > 0) {
					void goto(resolve(`/notes/${remaining[0].id}`), {
						keepFocus: true,
						noScroll: true,
					})
				} else {
					void goto(resolve('/notes'), { keepFocus: true, noScroll: true })
				}
			}
		} catch {
			deleteError = 'could not delete'
		} finally {
			isDeleting = false
		}
	}
</script>

<div
	class="flex min-h-0 flex-col {isMobile ? '' : 'h-full'}"
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
				<PopupMenu open={isSortMenuOpen} anchorEl={sortButtonEl} onClose={closeSortMenu}>
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
				</PopupMenu>
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
			<div class="py-4">
				<div
					class="rounded-container w-full overflow-hidden border border-white/14 bg-white/5 p-3 text-center text-sm whitespace-nowrap text-white/55"
				>
					no notes yet
				</div>
			</div>
		{:else}
			{#snippet noteItem(note: (typeof noteList)[0])}
				<div class="group/note relative">
					<SidebarListItem
						selected={selectedNoteId === note.id}
						onSelect={() => openNote(note.id)}
						actionsVisibility={device.isTouch ? 'always' : 'hover'}
						showChevron={true}
					>
						<span class="flex min-w-0 flex-col">
							<span class="min-w-0 truncate text-[0.95rem] font-medium text-white/90">
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
									if (openMenuId !== note.id)
										menuAnchorEl = e.currentTarget as HTMLElement
									openMenuId = openMenuId === note.id ? null : note.id
								}}
								aria-label="note options"
							>
								<EllipsisHorizontal class="h-5 w-5" />
							</button>
						{/snippet}
					</SidebarListItem>

					<PopupMenu
						open={openMenuId === note.id}
						anchorEl={menuAnchorEl}
						onClose={() => {
							openMenuId = null
						}}
						data-note-menu
					>
						<MenuItem onclick={() => handleShare(note.id)}>
							{#snippet icon()}<Share class="h-4 w-4" />{/snippet}
							share
						</MenuItem>
						<MenuItem onclick={() => handleProperties(note.id)}>
							{#snippet icon()}<InfoCircle class="h-4 w-4" />{/snippet}
							properties
						</MenuItem>
						<div class="my-1 h-px w-full bg-white/10"></div>
						<button
							type="button"
							class="group rounded-pill flex w-full cursor-pointer items-center border-none bg-transparent px-3 py-2 text-left text-sm text-white/80 transition-colors duration-150 hover:bg-red-500/10 hover:text-red-300"
							onclick={() => requestDelete(note.id)}
						>
							<Trash
								class="h-4 w-4 text-red-400 transition-colors duration-150 group-hover:text-red-300"
							/>
							<span class="ml-2">delete</span>
						</button>
					</PopupMenu>
				</div>
			{/snippet}

			{#if sharedNotes.length > 0}
				<!-- sectioned: user owns some, others are shared -->
				{#if myNotes.length > 0}
					<div>
						<button
							type="button"
							class="flex w-full cursor-pointer items-center gap-1.5 bg-transparent px-1 py-2 text-xs font-semibold tracking-wide text-white/70 uppercase transition-colors duration-150 hover:text-white/90"
							onclick={() => (myNotesOpen = !myNotesOpen)}
							aria-expanded={myNotesOpen}
						>
							<ChevronDown
								class="h-3 w-3 transition-transform duration-200 {myNotesOpen
									? ''
									: '-rotate-90'}"
							/>
							your notes
							<span class="font-normal text-white/50">({myNotes.length})</span>
						</button>
						{#if myNotesOpen}
							<div class="space-y-1">
								{#each myNotes as note (note.id)}
									{@render noteItem(note)}
								{/each}
							</div>
						{/if}
					</div>
				{/if}

				<div class="mt-3">
					<button
						type="button"
						class="flex w-full cursor-pointer items-center gap-1.5 bg-transparent px-1 py-2 text-xs font-semibold tracking-wide text-white/70 uppercase transition-colors duration-150 hover:text-white/90"
						onclick={() => (sharedNotesOpen = !sharedNotesOpen)}
						aria-expanded={sharedNotesOpen}
					>
						<ChevronDown
							class="h-3 w-3 transition-transform duration-200 {sharedNotesOpen
								? ''
								: '-rotate-90'}"
						/>
						shared with you
						<span class="font-normal text-white/50">({sharedNotes.length})</span>
					</button>
					{#if sharedNotesOpen}
						<div class="space-y-1">
							{#each sharedNotes as note (note.id)}
								{@render noteItem(note)}
							{/each}
						</div>
					{/if}
				</div>
			{:else}
				<!-- no shared notes: flat list without section headers -->
				<div class="space-y-1">
					{#each myNotes as note (note.id)}
						{@render noteItem(note)}
					{/each}
				</div>
			{/if}
		{/if}
	</nav>
</div>

<BaseModal
	open={deleteTargetId !== null}
	title="delete note?"
	description="this action cannot be undone."
	onClose={() => {
		if (isDeleting) return
		deleteTargetId = null
		deleteError = null
	}}
	widthClassName="max-w-sm"
>
	<div class="space-y-4">
		{#if deleteError}
			<div
				class="rounded-container border border-white/10 bg-white/5 px-3 py-2 text-sm text-white/70"
			>
				{deleteError}
			</div>
		{/if}

		<div class="flex items-center justify-end gap-2">
			<button
				type="button"
				class="rounded-pill border border-white/10 bg-transparent px-4 py-2 text-sm text-white/80 transition-colors duration-150 hover:bg-white/5"
				disabled={isDeleting}
				onclick={() => {
					deleteTargetId = null
					deleteError = null
				}}
			>
				cancel
			</button>
			<button
				type="button"
				class="rounded-pill inline-flex items-center border border-red-500/25 bg-red-500/20 px-4 py-2 text-sm text-red-100 transition-colors duration-150 hover:bg-red-500/30 disabled:opacity-60"
				disabled={isDeleting}
				onclick={() => void confirmDelete()}
			>
				<Trash class="h-4 w-4" />
				<span class="ml-2">
					{#if isDeleting}
						<ShimmerText className="inline-block">deleting</ShimmerText>
					{:else}
						delete
					{/if}
				</span>
			</button>
		</div>
	</div>
</BaseModal>
