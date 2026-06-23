<script lang="ts">
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import ShimmerText from '$lib/components/effects/ShimmerText.svelte'
	import EmptyState from '$lib/components/EmptyState.svelte'
	import FloatingScrollTopButton from '$lib/components/FloatingScrollTopButton.svelte'
	import ChevronDown from '$lib/components/icons/ChevronDown.svelte'
	import Document from '$lib/components/icons/Document.svelte'
	import EllipsisHorizontal from '$lib/components/icons/EllipsisHorizontal.svelte'
	import InfoCircle from '$lib/components/icons/InfoCircle.svelte'
	import Plus from '$lib/components/icons/Plus.svelte'
	import Share from '$lib/components/icons/Share.svelte'
	import SortIcon from '$lib/components/icons/SortIcon.svelte'
	import Trash from '$lib/components/icons/Trash.svelte'
	import BaseModal from '$lib/components/modals/BaseModal.svelte'
	import NokodoLoader from '$lib/components/NokodoLoader.svelte'
	import PageTitle from '$lib/components/PageTitle.svelte'
	import { MenuItem, PopupMenu } from '$lib/components/primitives'
	import ScrollTopShadow from '$lib/components/ScrollTopShadow.svelte'
	import SidebarListItem from '$lib/components/SidebarListItem.svelte'
	import Timestamp from '$lib/components/Timestamp.svelte'
	import type { ResourceProjectOption } from '$lib/components/widgets/ResourceProjectsMenu.svelte'
	import ResourceProjectsMenu from '$lib/components/widgets/ResourceProjectsMenu.svelte'
	import { device } from '$lib/stores/device.svelte'
	import { modals } from '$lib/stores/modals.svelte'
	import { notes, type Note, type NotesSortMode } from '$lib/stores/notes.svelte'
	import { projects } from '$lib/stores/projects.svelte'
	import {
		canDeleteAccessLevel,
		canEditAccessLevel,
		resourceAccess,
	} from '$lib/stores/resourceAccess.svelte'
	import { session } from '$lib/stores/session.svelte'
	import { byAuthor } from '$lib/utils/resourceAuthors'
	import SvelteVirtualList from '@humanspeak/svelte-virtual-list'
	import { tick } from 'svelte'

	interface Props {
		selectedNoteId: string | null
		isMobile?: boolean
	}

	let { selectedNoteId, isMobile = false }: Props = $props()
	const sidebarListEdgeStyle = $derived(
		isMobile
			? 'width: 100%;'
			: 'margin-left: calc(0px - var(--spacing-page-x)); margin-right: calc(0px - var(--spacing-page-x)); width: calc(100% + var(--spacing-page-x) + var(--spacing-page-x));'
	)

	let openMenuId: string | null = $state(null)
	let menuAnchorEl = $state<HTMLElement | null>(null)
	let listShellEl = $state<HTMLDivElement | null>(null)
	let listViewportEl = $state<HTMLElement | null>(null)

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

	const currentUserId = $derived(session.currentUserId)
	const myNotes = $derived(
		currentUserId ? noteList.filter((n) => n.userId === currentUserId) : noteList
	)
	const sharedNotes = $derived(
		currentUserId ? noteList.filter((n) => n.userId !== currentUserId) : []
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

	let myNotesOpen = $state(true)
	let sharedNotesOpen = $state(true)

	type NoteSidebarRow =
		| { kind: 'section'; id: 'my' | 'shared'; label: string; count: number; open: boolean }
		| { kind: 'note'; id: string; note: Note }

	const noteRows = $derived.by((): NoteSidebarRow[] => {
		if (sharedNotes.length === 0) {
			return myNotes.map((note) => ({ kind: 'note', id: note.id, note }))
		}

		const rows: NoteSidebarRow[] = []
		if (myNotes.length > 0) {
			rows.push({
				kind: 'section',
				id: 'my',
				label: 'your notes',
				count: myNotes.length,
				open: myNotesOpen,
			})
			if (myNotesOpen) {
				rows.push(...myNotes.map((note) => ({ kind: 'note' as const, id: note.id, note })))
			}
		}
		rows.push({
			kind: 'section',
			id: 'shared',
			label: 'shared with you',
			count: sharedNotes.length,
			open: sharedNotesOpen,
		})
		if (sharedNotesOpen) {
			rows.push(...sharedNotes.map((note) => ({ kind: 'note' as const, id: note.id, note })))
		}
		return rows
	})

	function labelForNote(title: string): string {
		const trimmed = title.trim()
		return trimmed.length > 0 ? trimmed : 'untitled'
	}

	function formatCharCount(value: string): string {
		const count = value.length
		return `${count} char${count === 1 ? '' : 's'}`
	}

	function noteAuthorLabel(note: (typeof noteList)[0]): string | null {
		if (note.userId === currentUserId) return null
		return session.authorLabel(note.userId)
	}

	function noteAccessLevel(note: (typeof noteList)[0]) {
		return resourceAccess.level('note', note.id, note.userId)
	}

	function canEditNote(note: (typeof noteList)[0]): boolean {
		return canEditAccessLevel(noteAccessLevel(note))
	}

	function canDeleteNote(note: (typeof noteList)[0]): boolean {
		return canDeleteAccessLevel(noteAccessLevel(note))
	}

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
		const notesAccessKey = `${resourceAccess.version}:${noteList.map((note) => note.id).join('|')}`
		if (!notesAccessKey) return
		if (sharedNotes.length > 0) void session.ensureUsers(sharedNotes.map((note) => note.userId))
		for (const note of noteList) {
			void resourceAccess.ensure('note', note.id, note.userId)
		}
	})

	$effect(() => {
		const shell = listShellEl
		const rowCount = noteRows.length
		if (!shell || rowCount === 0) {
			listViewportEl = null
			return
		}

		let cancelled = false
		void tick().then(() => {
			if (cancelled) return
			const viewport = shell.querySelector('.notes-sidebar-viewport')
			listViewportEl = viewport instanceof HTMLElement ? viewport : null
		})
		return () => {
			cancelled = true
		}
	})

	async function createNote() {
		const created = await notes.create()
		if (created) {
			await goto(resolve(`/notes/${created.id}`), { keepFocus: true, noScroll: true })
		}
	}

	function openNote(noteId: string) {
		void goto(resolve(`/notes/${noteId}`), { keepFocus: true, noScroll: true })
	}

	function handleShare(noteId: string, title: string): void {
		const note = notes.get(noteId)
		if (!note) return
		openMenuId = null
		modals.open('resource-access', { resourceType: 'note', resourceId: noteId, title })
	}

	function handleProperties(noteId: string): void {
		const note = notes.get(noteId)
		if (!note || !canEditNote(note)) return
		openMenuId = null
		modals.open('note-properties', { noteId })
	}

	function requestDelete(noteId: string): void {
		const note = notes.get(noteId)
		if (!note || !canDeleteNote(note)) return
		openMenuId = null
		deleteError = null
		deleteTargetId = noteId
	}

	async function handleNoteProjectToggle(
		note: (typeof noteList)[0],
		projectId: string,
		selected: boolean
	): Promise<void> {
		if (!canEditNote(note)) return
		const currentIds = note.projectIds
		const nextIds = selected
			? [...new Set([...currentIds, projectId])]
			: currentIds.filter((id) => id !== projectId)
		await notes.update(note.id, { projectIds: nextIds })
		projects.invalidateResourceCounts([...new Set([...currentIds, ...nextIds])])
	}

	async function confirmDelete(): Promise<void> {
		if (!deleteTargetId) return
		const noteId = deleteTargetId
		const note = notes.get(noteId)
		if (!note || !canDeleteNote(note)) return
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

<div class="flex h-full min-h-0 flex-col">
	<header
		class="{isMobile
			? 'pt-5 pb-4'
			: 'mt-(--master-detail-header-top) mb-(--spacing-island-content) h-(--master-detail-header-height) py-0'} relative z-10 flex shrink-0 items-center justify-between gap-3 px-2"
	>
		<PageTitle icon={Document} label="notes" iconColor="text-(--accent-primary)" tag="h2" />
		{#if !isMobile}
			<div class="flex items-center gap-1">
				<button
					type="button"
					bind:this={sortButtonEl}
					class="text-foreground/80 hover:text-foreground flex h-12 w-12 cursor-pointer items-center justify-center bg-transparent transition-transform duration-150 hover:scale-[1.05] active:scale-[0.97]"
					onclick={toggleSortMenu}
					aria-label="sort notes"
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
						sort notes
					</div>
					{#each sortOptions as option (option.value)}
						<MenuItem
							selected={notes.sortMode === option.value}
							onclick={() => {
								notes.sortMode = option.value
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
					onclick={createNote}
					class="text-foreground/80 hover:text-foreground flex h-12 w-12 cursor-pointer items-center justify-center bg-transparent transition-transform duration-150 hover:scale-[1.05] active:scale-[0.97]"
					aria-label="create note"
				>
					<Plus class="h-6 w-6" />
				</button>
			</div>
		{/if}
	</header>

	<nav class="flex min-h-0 flex-1 flex-col">
		{#if !notes.hydrated && notes.loading}
			<div class="flex flex-1 items-center justify-center py-8">
				<NokodoLoader className="opacity-70" expanded={false} />
			</div>
		{:else if noteList.length === 0}
			<div class="px-2">
				<EmptyState label="no notes yet" compact />
			</div>
		{:else}
			{#snippet noteItem(note: (typeof noteList)[0])}
				<div class="group/note relative px-3">
					<SidebarListItem
						selected={selectedNoteId === note.id}
						onSelect={() => openNote(note.id)}
						actionsVisibility={device.isTouch ? 'always' : 'reserve-hover'}
						showChevron={true}
						paddingClass="py-2.5 pr-3 pl-4"
					>
						<span class="flex min-w-0 flex-col">
							<span
								class="text-foreground/90 min-w-0 truncate text-[0.95rem] font-medium"
							>
								{labelForNote(note.title)}
							</span>
							<span
								class="text-foreground/55 flex min-w-0 items-center gap-1.5 text-xs"
							>
								<Timestamp
									timestamp={new Date(note.updatedAt)}
									mode="relative"
									className="shrink-0 text-xs text-foreground/55"
								/>
								<span class="text-foreground/32 shrink-0">·</span>
								<span class="shrink-0">{formatCharCount(note.content)}</span>
								{#if noteAuthorLabel(note)}
									<span class="text-foreground/32 shrink-0">·</span>
									<span class="min-w-0 truncate"
										>{byAuthor(noteAuthorLabel(note))}</span
									>
								{/if}
							</span>
						</span>

						{#snippet actions()}
							{#if note}
								<button
									type="button"
									data-note-menu
									class="text-foreground/65 hover:bg-foreground/8 hover:text-foreground flex h-8 w-8 shrink-0 cursor-pointer items-center justify-center rounded-full border-none bg-transparent transition-all"
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
							{/if}
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
						{#if note}
							<MenuItem onclick={() => handleShare(note.id, note.title ?? 'note')}>
								{#snippet icon()}<Share
										class="size-full"
										strokeWidth="2.1"
									/>{/snippet}
								share
							</MenuItem>
						{/if}
						{#if canEditNote(note)}
							<MenuItem onclick={() => handleProperties(note.id)}>
								{#snippet icon()}<InfoCircle
										variant="solid"
										class="size-full"
									/>{/snippet}
								properties
							</MenuItem>
							<ResourceProjectsMenu
								projectOptions={manageableProjectOptions}
								selectedProjectIds={note.projectIds}
								onProjectToggle={(projectId, selected) =>
									handleNoteProjectToggle(note, projectId, selected)}
							/>
						{/if}
						{#if canDeleteNote(note)}
							<div class="bg-foreground/10 my-1 h-px w-full"></div>
							<MenuItem destructive onclick={() => requestDelete(note.id)}>
								{#snippet icon()}<Trash
										class="size-full text-red-400"
										strokeWidth="2.1"
									/>{/snippet}
								delete
							</MenuItem>
						{/if}
					</PopupMenu>
				</div>
			{/snippet}

			<div
				bind:this={listShellEl}
				class="relative min-h-0 flex-1 overflow-hidden"
				style={sidebarListEdgeStyle}
			>
				<SvelteVirtualList
					items={noteRows}
					defaultEstimatedItemHeight={62}
					bufferSize={16}
					containerClass="relative h-full min-h-0 w-full overflow-hidden"
					viewportClass="notes-sidebar-viewport absolute inset-0 w-full overflow-y-auto"
					contentClass="relative min-h-full w-full"
					itemsClass="absolute top-0 left-0 flex w-full flex-col gap-1 pt-2"
				>
					{#snippet renderItem(row, rowIndex)}
						{#if row.kind === 'section'}
							<div class="px-3 {rowIndex === noteRows.length - 1 ? 'pb-5' : ''}">
								<button
									type="button"
									class="text-foreground/70 hover:text-foreground/90 flex w-full cursor-pointer items-center gap-1.5 bg-transparent px-2 py-2 text-xs font-semibold tracking-wide uppercase transition-colors duration-150"
									onclick={() => {
										if (row.id === 'my') myNotesOpen = !myNotesOpen
										else sharedNotesOpen = !sharedNotesOpen
									}}
									aria-expanded={row.open}
								>
									<ChevronDown
										class="h-3 w-3 transition-transform duration-200 {row.open
											? ''
											: '-rotate-90'}"
									/>
									{row.label}
									<span class="text-foreground/50 font-normal">({row.count})</span
									>
								</button>
							</div>
						{:else}
							<div class={rowIndex === noteRows.length - 1 ? 'pb-5' : ''}>
								{@render noteItem(row.note)}
							</div>
						{/if}
					{/snippet}
				</SvelteVirtualList>
				<ScrollTopShadow target={listViewportEl} />
				<FloatingScrollTopButton target={listViewportEl} />
			</div>
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
				class="rounded-container border-foreground/10 bg-foreground/5 text-foreground/70 border px-3 py-2 text-sm"
			>
				{deleteError}
			</div>
		{/if}

		<div class="flex items-center justify-end gap-2">
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
