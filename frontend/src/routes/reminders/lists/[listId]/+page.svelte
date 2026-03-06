<script lang="ts">
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import { page } from '$app/state'
	import ChevronLeft from '$lib/components/icons/ChevronLeft.svelte'
	import RemindersPanel from '$lib/components/reminders/RemindersPanel.svelte'
	import { useSystemChrome } from '$lib/contexts/systemChromeContext.svelte'
	import { device } from '$lib/stores/device.svelte'

	const chrome = useSystemChrome()

	const selectedListId = $derived(page.params.listId ?? null)

	const handleBackToLists = async () => {
		await goto(resolve('/reminders/lists'), { keepFocus: true, noScroll: true })
	}

	$effect(() => {
		if (device.isMobile) {
			chrome.setContextActions(mobileBackAction)
			return () => chrome.setContextActions(null)
		}
	})
</script>

{#snippet mobileBackAction()}
	<button
		type="button"
		class="rounded-pill hover:text-foreground flex h-12 w-12 cursor-pointer items-center justify-center border-none bg-transparent transition-transform duration-150 hover:scale-[1.05] active:scale-[0.97]"
		onclick={handleBackToLists}
		aria-label="back to lists"
	>
		<ChevronLeft class="h-5 w-5" strokeWidth="2" />
	</button>
{/snippet}

<RemindersPanel listId={selectedListId} showListTitle={device.isMobile} />
