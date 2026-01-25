<script lang="ts">
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import ReminderListsSidebar from '$lib/components/reminders/ReminderListsSidebar.svelte'
	import { useSystemChrome } from '$lib/contexts/systemChromeContext.svelte'
	import { device } from '$lib/stores/device.svelte'
	import { reminders } from '$lib/stores/reminders.svelte'

	const chrome = useSystemChrome()
	let isLoadingLists = $state(false)

	$effect(() => {
		// On desktop, this route is redundant (sidebar is always visible).
		// Redirect to main reminders page.
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
		chrome.setIsland({ actions: null })
	})
</script>

<!-- Only show on mobile (layout handles desktop sidebar) -->
{#if device.isMobile}
	<ReminderListsSidebar selectedListId={undefined} isLoading={isLoadingLists} />
{/if}
