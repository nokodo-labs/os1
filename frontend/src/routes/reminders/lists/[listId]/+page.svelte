<script lang="ts">
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import { page } from '$app/state'
	import RemindersPanel from '$lib/components/reminders/RemindersPanel.svelte'
	import { useSystemChrome } from '$lib/contexts/systemChromeContext.svelte'
	import { device } from '$lib/stores/device.svelte'

	const chrome = useSystemChrome()

	const selectedListId = $derived(page.params.listId ?? null)

	$effect(() => {
		const backToLists = async () => {
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
							onClick: backToLists,
						},
					]
				: null,
		})

		return () => chrome.setIsland({ actions: null })
	})
</script>

<RemindersPanel listId={selectedListId} showListTitle={device.isMobile} />
