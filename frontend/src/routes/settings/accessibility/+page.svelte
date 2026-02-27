<script lang="ts">
	import SoundHigh from '$lib/components/icons/SoundHigh.svelte'
	import { Switch } from '$lib/components/primitives'
	import SettingsSectionLayout from '$lib/components/settings/SettingsSectionLayout.svelte'
	import { preferences } from '$lib/stores/preferences.svelte'

	const hapticEnabled = $derived(preferences.data.accessibility.hapticFeedback ?? false)

	function setHaptic(enabled: boolean): void {
		void preferences.update('accessibility', { hapticFeedback: enabled })
	}
</script>

<SettingsSectionLayout
	icon={SoundHigh}
	label="accessibility"
	description="configure haptic feedback and assistive features"
>
	<div class="space-y-4">
		<div class="rounded-container liquid-glass liquid-glass--frosted p-5">
			<div class="text-sm font-semibold text-white/85">haptic feedback</div>
			<div class="mt-1 text-sm text-white/55">
				enable haptic feedback on supported devices
			</div>
			<div class="mt-4 flex items-center justify-between">
				<span id="haptic-label" class="text-sm text-white/70">haptic feedback</span>
				<Switch
					size="md"
					checked={hapticEnabled}
					onchange={setHaptic}
					ariaLabelledbyId="haptic-label"
				/>
			</div>
		</div>
	</div>
</SettingsSectionLayout>
