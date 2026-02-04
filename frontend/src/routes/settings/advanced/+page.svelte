<script lang="ts">
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import ChevronLeft from '$lib/components/icons/ChevronLeft.svelte'
	import Wrench from '$lib/components/icons/Wrench.svelte'
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
	icon={Wrench}
	label="advanced"
	description="developer tools and experimental features"
>
	<div class="space-y-4">
		<div class="rounded-container bg-white/5 p-5">
			<div class="text-sm font-semibold text-white/85">developer mode</div>
			<div class="mt-1 text-sm text-white/55">
				enable developer tools and debug information.
			</div>
			<div class="mt-4 h-6 w-12 rounded-full bg-white/10"></div>
		</div>
		<div class="rounded-container bg-white/5 p-5">
			<div class="text-sm font-semibold text-white/85">experimental features</div>
			<div class="mt-1 text-sm text-white/55">
				try out new features before they're released.
			</div>
			<div class="mt-4 space-y-3">
				<div class="flex items-center justify-between">
					<span class="text-sm text-white/70">new chat UI</span>
					<div class="h-6 w-12 rounded-full bg-white/10"></div>
				</div>
				<div class="flex items-center justify-between">
					<span class="text-sm text-white/70">voice input</span>
					<div class="h-6 w-12 rounded-full bg-white/10"></div>
				</div>
			</div>
		</div>
		<div class="rounded-container border border-red-500/30 bg-red-500/5 p-5">
			<div class="text-sm font-semibold text-red-400">danger zone</div>
			<div class="mt-1 text-sm text-white/55">
				irreversible actions. proceed with caution.
			</div>
			<div class="mt-4 flex gap-3">
				<button
					type="button"
					class="rounded-pill border border-red-500/50 bg-transparent px-4 py-2 text-sm text-red-400 transition-colors hover:bg-red-500/10"
				>
					clear all data
				</button>
				<button
					type="button"
					class="rounded-pill border border-red-500/50 bg-transparent px-4 py-2 text-sm text-red-400 transition-colors hover:bg-red-500/10"
				>
					delete account
				</button>
			</div>
		</div>
	</div>
</SettingsSectionLayout>
