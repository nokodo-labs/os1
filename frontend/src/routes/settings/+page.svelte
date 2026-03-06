<script lang="ts">
	import { browser } from '$app/environment'
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import { page } from '$app/state'
	import Cog6 from '$lib/components/icons/Cog6.svelte'
	import SettingsSectionLayout from '$lib/components/settings/SettingsSectionLayout.svelte'
	import SettingsSidebar from '$lib/components/settings/SettingsSidebar.svelte'
	import { appNavigation } from '$lib/stores/appNavigation.svelte'
	import { device } from '$lib/stores/device.svelte'

	$effect(() => {
		if (!browser || device.isMobile) return
		if (page.url.pathname !== '/settings') return
		const target = appNavigation.getEntryRoute('settings')
		void goto(resolve(target), { keepFocus: true, noScroll: true, replaceState: true })
	})
</script>

{#if device.isMobile}
	<SettingsSidebar selectedSection={null} isMobile={true} />
{:else}
	<SettingsSectionLayout
		icon={Cog6}
		label="settings"
		description="select a section to get started"
	>
		<div class="rounded-container flex flex-col gap-2 bg-foreground/5 p-5">
			<div class="text-sm font-semibold text-foreground/85">select a section</div>
			<div class="text-sm text-foreground/50">
				choose an item from the sidebar to view its settings
			</div>
		</div>
	</SettingsSectionLayout>
{/if}
