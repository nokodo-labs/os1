<script lang="ts">
	import { browser } from '$app/environment'
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import ReminderListPanel from '$lib/components/reminders/ReminderListPanel.svelte'
	import { useSystemChrome } from '$lib/contexts/systemChromeContext.svelte'
	import { device } from '$lib/stores/device.svelte'

	const chrome = useSystemChrome()
	$effect(() => {
		const addReminder = () => {
			if (!browser) return
			window.dispatchEvent(
				new CustomEvent('nokodo:reminders:add', { detail: { listId: null } })
			)
		}

		const openLists = async () => {
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
							onClick: openLists,
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

<ReminderListPanel listId={null} />
