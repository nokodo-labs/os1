<script lang="ts">
	import { browser } from '$app/environment'
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import ArrowsUpDown from '$lib/components/icons/ArrowsUpDown.svelte'
	import Plus from '$lib/components/icons/Plus.svelte'
	import NotesSidebar from '$lib/components/notes/NotesSidebar.svelte'
	import { useSystemChrome } from '$lib/contexts/systemChromeContext.svelte'
	import { device } from '$lib/stores/device.svelte'
	import { notes, type NotesSortMode } from '$lib/stores/notes.svelte'
	import { scale } from 'svelte/transition'

	const chrome = useSystemChrome()

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

	$effect(() => {
		if (!browser || !isSortMenuOpen) return

		const onKeyDown = (event: KeyboardEvent) => {
			if (event.key !== 'Escape') return
			event.preventDefault()
			closeSortMenu()
		}

		const onPointerDown = (event: PointerEvent) => {
			const path = event.composedPath()
			if (sortMenuEl && path.includes(sortMenuEl)) return
			if (sortButtonEl && path.includes(sortButtonEl)) return
			closeSortMenu()
		}

		window.addEventListener('keydown', onKeyDown)
		window.addEventListener('pointerdown', onPointerDown)
		return () => {
			window.removeEventListener('keydown', onKeyDown)
			window.removeEventListener('pointerdown', onPointerDown)
		}
	})
</script>

{#snippet islandContextActions()}
	<div class="relative">
		<button
			type="button"
			bind:this={sortButtonEl}
			class="group rounded-pill flex cursor-pointer items-center justify-center border-none bg-transparent opacity-80 transition-all duration-150 hover:scale-[1.05] hover:opacity-100 active:scale-[0.97]"
			onclick={toggleSortMenu}
			aria-label="sort notes"
			aria-haspopup="menu"
			aria-expanded={isSortMenuOpen}
		>
			<ArrowsUpDown variant="solid" />
		</button>

		{#if isSortMenuOpen}
			<div
				transition:scale={{ duration: 160, start: 0.96, opacity: 0 }}
				bind:this={sortMenuEl}
				role="menu"
				class="animate-popup-right rounded-container absolute top-full left-0 z-50 mt-2 w-44 border border-white/10 bg-black/70 p-2 shadow-[0_24px_48px_rgba(12,10,30,0.55)] backdrop-blur"
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
		class="group rounded-pill flex cursor-pointer items-center justify-center border-none bg-transparent opacity-80 transition-all duration-150 hover:scale-[1.05] hover:opacity-100 active:scale-[0.97]"
		onclick={createNote}
		aria-label="create note"
	>
		<Plus />
	</button>
{/snippet}

{#if device.isMobile}
	<NotesSidebar selectedNoteId={null} isMobile={true} />
{:else}
	<div
		class="flex h-[calc(100vh-var(--chrome-island-offset,0px)-var(--spacing-island-content)-2.5rem)] items-center justify-center"
	>
		<p class="text-sm text-white/50">select or create a note</p>
	</div>
{/if}
