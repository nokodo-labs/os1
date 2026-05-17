<script lang="ts">
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import { SortIcon } from '$lib/components/icons'
	import Plus from '$lib/components/icons/Plus.svelte'
	import NotesSidebar from '$lib/components/notes/NotesSidebar.svelte'
	import { MenuItem, PopupMenu } from '$lib/components/primitives'
	import { useSystemChrome } from '$lib/contexts/systemChromeContext.svelte'
	import { device } from '$lib/stores/device.svelte'
	import { notes, type NotesSortMode } from '$lib/stores/notes.svelte'

	const chrome = useSystemChrome()

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

	async function createNote() {
		const created = await notes.create()
		if (created) {
			await goto(resolve(`/notes/${created.id}`), { keepFocus: true, noScroll: true })
		}
	}

	$effect(() => {
		void notes.load()
	})

	$effect(() => {
		if (device.isMobile) {
			chrome.setContextActions(islandContextActions)
			return () => chrome.setContextActions(null)
		}
	})
</script>

{#snippet islandContextActions()}
	<button
		type="button"
		bind:this={sortButtonEl}
		class="group rounded-pill flex cursor-pointer items-center justify-center border-none bg-transparent opacity-80 transition-all duration-150 hover:scale-[1.05] hover:opacity-100 active:scale-[0.97]"
		onclick={toggleSortMenu}
		aria-label="sort notes"
		aria-haspopup="menu"
		aria-expanded={isSortMenuOpen}
	>
		<SortIcon />
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
				{#snippet icon()}<SortIcon value={option.value} class="h-4 w-4" />{/snippet}
				{option.label}
			</MenuItem>
		{/each}
	</PopupMenu>

	<button
		type="button"
		class="group rounded-pill flex cursor-pointer items-center justify-center border-none bg-transparent opacity-80 transition-all duration-150 hover:scale-[1.05] hover:opacity-100 active:scale-[0.97]"
		onclick={createNote}
		aria-label="create note"
	>
		<Plus />
	</button>
{/snippet}

{#if device.isMobile}
	<div class="flex h-full min-h-0 flex-1 flex-col">
		<NotesSidebar selectedNoteId={null} isMobile={true} />
	</div>
{:else}
	<div
		class="flex h-[calc(100vh-var(--chrome-island-offset,0)-var(--spacing-island-content)-2.5rem)] items-center justify-center"
	>
		<p class="text-foreground/50 text-sm">select or create a note</p>
	</div>
{/if}
