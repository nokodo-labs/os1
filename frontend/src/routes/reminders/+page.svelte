<script lang="ts">
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import RemindersPanel from '$lib/components/reminders/RemindersPanel.svelte'
	import { useSystemChrome } from '$lib/contexts/systemChromeContext.svelte'
	import { device } from '$lib/stores/device.svelte'

	const chrome = useSystemChrome()
	$effect(() => {
		const openLists = async () => {
			await goto(resolve('/reminders/lists'), { keepFocus: true, noScroll: true })
		}

		chrome.setIsland({
			actions: device.isMobile
				? [
						{
							id: 'lists',
							label: '',
							ariaLabel: 'back to lists',
							icon: 'chevron-left',
							onClick: openLists,
						},
					]
				: null,
		})

		return () => chrome.setIsland({ actions: null })
	})
</script>

<RemindersPanel listId={null} showListTitle={device.isMobile} />
