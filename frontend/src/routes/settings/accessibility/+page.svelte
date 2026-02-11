<script lang="ts">
	import SoundHigh from '$lib/components/icons/SoundHigh.svelte'
	import SettingsSectionLayout from '$lib/components/settings/SettingsSectionLayout.svelte'
	import { preferences } from '$lib/stores/preferences.svelte'

	const hapticEnabled = $derived(preferences.data.accessibility.hapticFeedback)

	function toggleHaptic(): void {
		void preferences.update('accessibility', { hapticFeedback: !hapticEnabled })
	}
</script>

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
