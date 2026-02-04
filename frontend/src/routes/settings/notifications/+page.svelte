<script lang="ts">
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import AppNotification from '$lib/components/icons/AppNotification.svelte'
	import ChevronLeft from '$lib/components/icons/ChevronLeft.svelte'
	import SettingsSectionLayout from '$lib/components/settings/SettingsSectionLayout.svelte'
	import { useSystemChrome } from '$lib/contexts/systemChromeContext.svelte'
	import { device } from '$lib/stores/device.svelte'

	const chrome = useSystemChrome()

	const handleBackToSettings = async () => {
		await goto(resolve('/settings'), { keepFocus: true, noScroll: true })
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
		class="rounded-pill flex h-12 w-12 cursor-pointer items-center justify-center border-none bg-transparent transition-transform duration-150 hover:scale-[1.05] hover:text-white active:scale-[0.97]"
		onclick={handleBackToSettings}
		aria-label="back to settings"
	>
		<ChevronLeft class="h-5 w-5" strokeWidth="2" />
	</button>
{/snippet}

<SettingsSectionLayout
	icon={AppNotification}
	label="notifications"
	description="configure alerts, sounds, and reminder settings"
>
	<div class="space-y-4">
		<div class="rounded-container bg-white/5 p-5">
			<div class="text-sm font-semibold text-white/85">push notifications</div>
			<div class="mt-1 text-sm text-white/55">
				receive notifications for messages, reminders, and updates.
			</div>
			<div class="mt-4 h-6 w-12 rounded-full bg-white/20"></div>
		</div>
		<div class="rounded-container bg-white/5 p-5">
			<div class="text-sm font-semibold text-white/85">email notifications</div>
			<div class="mt-1 text-sm text-white/55">
				receive email digests and important alerts.
			</div>
			<div class="mt-4 h-6 w-12 rounded-full bg-white/10"></div>
		</div>
	</div>
</SettingsSectionLayout>
