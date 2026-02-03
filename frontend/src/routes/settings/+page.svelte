<script lang="ts">
	import SettingsSectionContent from '$lib/components/settings/SettingsSectionContent.svelte'
	import SettingsSidebar from '$lib/components/settings/SettingsSidebar.svelte'
	import { device } from '$lib/stores/device.svelte'
</script>

{#if device.isMobile}
	<SettingsSidebar selectedSection={null} isMobile={true} />
{:else}
	<SettingsSectionContent section="account" />
{/if}
