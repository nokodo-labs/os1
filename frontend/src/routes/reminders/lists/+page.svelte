<script lang="ts">
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import Plus from '$lib/components/icons/Plus.svelte'
	import SortIcon from '$lib/components/icons/SortIcon.svelte'
	import { MenuItem, PopupMenu } from '$lib/components/primitives'
	import ReminderListsSidebar from '$lib/components/reminders/ReminderListsSidebar.svelte'
	import { useSystemChrome } from '$lib/contexts/systemChromeContext.svelte'
	import { device } from '$lib/stores/device.svelte'
	import { reminders, type ReminderListsSortMode } from '$lib/stores/reminders.svelte'

	const chrome = useSystemChrome()

	let isLoadingLists = $state(false)
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
</script>

{#snippet islandContextActions()}
	<button
		type="button"
		bind:this={sortButtonEl}
		class="group rounded-pill flex cursor-pointer items-center justify-center border-none bg-transparent opacity-80 transition-all duration-150 hover:scale-[1.05] hover:opacity-100 active:scale-[0.97]"
		onclick={toggleSortMenu}
		aria-label="sort lists"
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
				{#snippet icon()}<SortIcon value={option.value} class="h-4 w-4" />{/snippet}
				{option.label}
			</MenuItem>
		{/each}
	</PopupMenu>

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
	<div class="flex h-full min-h-0 flex-1 flex-col">
		<ReminderListsSidebar
			selectedListId={undefined}
			isLoading={isLoadingLists}
			isMobile={true}
		/>
	</div>
{/if}
