<script lang="ts">
	import { browser } from '$app/environment'
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import ArrowsUpDown from '$lib/components/icons/ArrowsUpDown.svelte'
	import Plus from '$lib/components/icons/Plus.svelte'
	import ReminderListsSidebar from '$lib/components/reminders/ReminderListsSidebar.svelte'
	import { useSystemChrome } from '$lib/contexts/systemChromeContext.svelte'
	import { device } from '$lib/stores/device.svelte'
	import { reminders, type ReminderListsSortMode } from '$lib/stores/reminders.svelte'
	import { scale } from 'svelte/transition'

	const chrome = useSystemChrome()

	let isLoadingLists = $state(false)
	let isSortMenuOpen = $state(false)
	let sortMenuEl: HTMLDivElement | null = $state(null)
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
		sortMenuEl = null
	}

	function toggleSortMenu() {
		isSortMenuOpen = !isSortMenuOpen
	}

	function handleCreateList() {
		window.dispatchEvent(new CustomEvent('reminders:list-add'))
	}

	$effect(() => {
		// on desktop, this route is redundant (sidebar is always visible).
		// redirect to main reminders page.
		if (!device.isMobile) {
			void goto(resolve('/reminders'), { replaceState: true })
			return
		}

		isLoadingLists = true
		void reminders.loadListsAndCounts().finally(() => {
			isLoadingLists = false
		})
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
			aria-label="sort lists"
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
							reminders.setListsSortMode(option.value)
							closeSortMenu()
						}}
					>
						{option.label}{reminders.listsSortMode === option.value ? ' ✓' : ''}
					</button>
				{/each}
			</div>
		{/if}
	</div>

	<button
		type="button"
		class="group rounded-pill flex cursor-pointer items-center justify-center border-none bg-transparent opacity-80 transition-all duration-150 hover:scale-[1.05] hover:opacity-100 active:scale-[0.97]"
		onclick={handleCreateList}
		aria-label="create list"
	>
		<Plus />
	</button>
{/snippet}

<!-- only show on mobile (layout handles desktop sidebar) -->
{#if device.isMobile}
	<ReminderListsSidebar selectedListId={undefined} isLoading={isLoadingLists} isMobile={true} />
{/if}
