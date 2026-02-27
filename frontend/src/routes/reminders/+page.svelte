<script lang="ts">
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import ChevronLeft from '$lib/components/icons/ChevronLeft.svelte'
	import RemindersPanel from '$lib/components/reminders/RemindersPanel.svelte'
	import { useSystemChrome } from '$lib/contexts/systemChromeContext.svelte'
	import { device } from '$lib/stores/device.svelte'

	const chrome = useSystemChrome()

	const handleOpenLists = async () => {
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
		class="rounded-pill flex cursor-pointer items-center justify-center border-none bg-transparent transition-transform duration-150 hover:scale-[1.05] hover:text-foreground active:scale-[0.97]"
		onclick={handleOpenLists}
		aria-label="back to lists"
	>
		<ChevronLeft strokeWidth="2" />
	</button>
{/snippet}

<RemindersPanel listId={null} showListTitle={device.isMobile} />
