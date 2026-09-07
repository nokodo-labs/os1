<script lang="ts">
	import SoundHigh from '$lib/components/icons/SoundHigh.svelte'
	import { Switch } from '$lib/components/primitives'
	import { accessibilityFields } from '$lib/components/settings/fields/accessibility'
	import PreferenceScopeToggle from '$lib/components/settings/PreferenceScopeToggle.svelte'
	import SettingsField from '$lib/components/settings/SettingsField.svelte'
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
		<SettingsField field={accessibilityFields.hapticFeedback} controlLayout="wrap">
			{#snippet control()}
				<PreferenceScopeToggle
					scope={hapticFeedbackScope}
					onchange={setHapticFeedbackScope}
				/>
			{/snippet}
			<div class="mt-4 flex items-center justify-between">
				<span id="haptic-label" class="text-foreground/70 text-sm">haptic feedback</span>
				<Switch
					size="md"
					checked={hapticEnabled}
					onchange={setHaptic}
					ariaLabelledbyId="haptic-label"
				/>
			</div>
		</SettingsField>
	</div>
</SettingsSectionLayout>
