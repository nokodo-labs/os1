<script lang="ts">
	import SettingsSectionContent from '$lib/components/settings/SettingsSectionContent.svelte'
	import SettingsSidebar from '$lib/components/settings/SettingsSidebar.svelte'
	import { useSystemChrome } from '$lib/contexts/systemChromeContext.svelte'
	import { device } from '$lib/stores/device.svelte'

	const chrome = useSystemChrome()

	$effect(() => {
		chrome.setIsland({ actions: null })
		return () => chrome.setIsland({ actions: null })
	})
</script>

{#if device.isMobile}
	<SettingsSidebar selectedSection={null} isMobile={true} />
{:else}
	<SettingsSectionContent section="account" />
{/if}
