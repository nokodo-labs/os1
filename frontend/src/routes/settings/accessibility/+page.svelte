<script lang="ts">
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import ChevronLeft from '$lib/components/icons/ChevronLeft.svelte'
	import SoundHigh from '$lib/components/icons/SoundHigh.svelte'
	import SettingsSectionLayout from '$lib/components/settings/SettingsSectionLayout.svelte'
	import { useSystemChrome } from '$lib/contexts/systemChromeContext.svelte'
	import { device } from '$lib/stores/device.svelte'
	import { preferences } from '$lib/stores/preferences.svelte'

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

	const hapticEnabled = $derived(preferences.data.accessibility.hapticFeedback)

	function toggleHaptic(): void {
		void preferences.update('accessibility', { hapticFeedback: !hapticEnabled })
	}
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
	icon={SoundHigh}
	label="accessibility"
	description="configure haptic feedback and assistive features"
>
	<div class="space-y-4">
		<div class="rounded-container bg-white/5 p-5">
			<div class="text-sm font-semibold text-white/85">haptic feedback</div>
			<div class="mt-1 text-sm text-white/55">
				enable vibration feedback on supported devices when receiving AI responses.
			</div>
			<div class="mt-4 flex items-center justify-between">
				<span id="haptic-label" class="text-sm text-white/70"
					>vibrate on incoming messages</span
				>
				<button
					type="button"
					onclick={toggleHaptic}
					class="relative h-6 w-12 rounded-full transition-colors duration-200 {hapticEnabled
						? 'bg-(--accent-primary)'
						: 'bg-white/20'}"
					aria-checked={hapticEnabled}
					aria-labelledby="haptic-label"
					role="switch"
				>
					<span
						class="absolute top-0.5 h-5 w-5 rounded-full bg-white shadow-md transition-transform duration-200 {hapticEnabled
							? 'translate-x-6'
							: 'translate-x-0.5'}"
					></span>
				</button>
			</div>
		</div>
	</div>
</SettingsSectionLayout>
