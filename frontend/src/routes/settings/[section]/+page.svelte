<script lang="ts">
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import { page } from '$app/state'
	import SettingsSectionContent from '$lib/components/settings/SettingsSectionContent.svelte'
	import { useSystemChrome } from '$lib/contexts/systemChromeContext.svelte'
	import { device } from '$lib/stores/device.svelte'

	const chrome = useSystemChrome()
	const section = $derived(page.params.section ?? 'account')

	$effect(() => {
		const backToSections = async () => {
			await goto(resolve('/settings'), { keepFocus: true, noScroll: true })
		}

		chrome.setIsland({
			actions: device.isMobile
				? [
						{
							id: 'sections',
							label: '',
							ariaLabel: 'back to settings',
							icon: 'chevron-left',
							onClick: backToSections,
						},
					]
				: null,
		})

		return () => chrome.setIsland({ actions: null })
	})
</script>

<SettingsSectionContent {section} />
