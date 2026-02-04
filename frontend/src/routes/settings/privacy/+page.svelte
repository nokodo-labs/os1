<script lang="ts">
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import ChevronLeft from '$lib/components/icons/ChevronLeft.svelte'
	import Lock from '$lib/components/icons/Lock.svelte'
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
	icon={Lock}
	label="privacy & security"
	description="control your data, permissions, and access settings"
>
	<div class="space-y-4">
		<div class="rounded-box bg-white/5 p-5">
			<div class="text-sm font-semibold text-white/85">data collection</div>
			<div class="mt-1 text-sm text-white/55">
				control what data is collected and how it's used.
			</div>
			<div class="mt-4 space-y-3">
				<div class="flex items-center justify-between">
					<span class="text-sm text-white/70">analytics</span>
					<div class="h-6 w-12 rounded-full bg-white/20"></div>
				</div>
				<div class="flex items-center justify-between">
					<span class="text-sm text-white/70">crash reports</span>
					<div class="h-6 w-12 rounded-full bg-white/20"></div>
				</div>
			</div>
		</div>
		<div class="rounded-box bg-white/5 p-5">
			<div class="text-sm font-semibold text-white/85">sessions</div>
			<div class="mt-1 text-sm text-white/55">
				manage active sessions and sign out of other devices.
			</div>
			<div class="rounded-pill mt-4 h-10 w-full bg-white/8"></div>
		</div>
	</div>
</SettingsSectionLayout>
