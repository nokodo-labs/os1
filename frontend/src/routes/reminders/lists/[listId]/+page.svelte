<script lang="ts">
	import { browser } from '$app/environment'
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import { page } from '$app/state'
	import ReminderListPanel from '$lib/components/reminders/ReminderListPanel.svelte'
	import { useSystemChrome } from '$lib/contexts/systemChromeContext.svelte'
	import { device } from '$lib/stores/device.svelte'

	const chrome = useSystemChrome()

	const selectedListId = $derived(page.params.listId ?? null)

	$effect(() => {
		const addReminder = () => {
			if (!browser) return
			window.dispatchEvent(
				new CustomEvent('nokodo:reminders:add', { detail: { listId: selectedListId } })
			)
		}

		const backToLists = async () => {
			await goto(resolve('/reminders/lists'), { keepFocus: true, noScroll: true })
		}

		chrome.setIsland({
			actions: device.isMobile
				? [
						{
							id: 'lists',
							label: 'lists',
							ariaLabel: 'lists',
							icon: 'list',
							onClick: backToLists,
						},
						{
							id: 'add',
							label: 'add',
							ariaLabel: 'add reminder',
							icon: 'plus',
							onClick: addReminder,
						},
					]
				: [
						{
							id: 'add',
							label: 'add',
							ariaLabel: 'add reminder',
							icon: 'plus',
							onClick: addReminder,
						},
					],
		})

		return () => chrome.setIsland({ actions: null })
	})
</script>

<ReminderListPanel listId={selectedListId} />
