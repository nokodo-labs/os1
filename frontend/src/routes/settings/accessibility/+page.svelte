<script lang="ts">
	import SoundHigh from '$lib/components/icons/SoundHigh.svelte'
	import { Switch } from '$lib/components/primitives'
	import PreferenceScopeToggle from '$lib/components/settings/PreferenceScopeToggle.svelte'
	import SettingsSectionLayout from '$lib/components/settings/SettingsSectionLayout.svelte'
	import { preferences, type ClientPreferenceScope } from '$lib/stores/preferences.svelte'

	const hapticEnabled = $derived(preferences.data.accessibility.hapticFeedback ?? false)
	const hapticFeedbackScope = $derived(preferences.hapticFeedbackScope)

	function setHaptic(enabled: boolean): void {
		void preferences.updateHapticFeedback(enabled)
	}

	function setHapticFeedbackScope(scope: ClientPreferenceScope): void {
		void preferences.setHapticFeedbackScope(scope)
	}
</script>

<SettingsSectionLayout
	icon={SoundHigh}
	label="accessibility"
	description="configure haptic feedback and assistive features"
>
	<div class="space-y-4">
		<div class="rounded-container liquid-glass liquid-glass--frosted p-5">
			<div class="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
				<div>
					<div class="text-foreground/85 text-sm font-semibold">haptic feedback</div>
					<div class="text-foreground/55 mt-1 text-sm">
						enable haptic feedback on supported devices
					</div>
				</div>
				<PreferenceScopeToggle
					scope={hapticFeedbackScope}
					onchange={setHapticFeedbackScope}
				/>
			</div>
			<div class="mt-4 flex items-center justify-between">
				<span id="haptic-label" class="text-foreground/70 text-sm">haptic feedback</span>
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
