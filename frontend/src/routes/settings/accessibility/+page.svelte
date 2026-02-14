<script lang="ts">
	import SoundHigh from '$lib/components/icons/SoundHigh.svelte'
	import { Switch } from '$lib/components/primitives'
	import SettingsSectionLayout from '$lib/components/settings/SettingsSectionLayout.svelte'
	import { preferences } from '$lib/stores/preferences.svelte'

	const hapticEnabled = $derived(preferences.data.accessibility.hapticFeedback ?? false)
	const svgLiquidGlassEnabled = $derived(preferences.data.accessibility.svgLiquidGlass ?? true)

	function setHaptic(enabled: boolean): void {
		void preferences.update('accessibility', { hapticFeedback: enabled })
	}

	function setSvgLiquidGlass(enabled: boolean): void {
		void preferences.update('accessibility', { svgLiquidGlass: enabled })
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
				<Switch
					size="md"
					checked={hapticEnabled}
					onchange={setHaptic}
					ariaLabelledbyId="haptic-label"
				/>
			</div>
		</div>

		<div class="rounded-container bg-white/5 p-5">
			<div class="text-sm font-semibold text-white/85">liquid glass rendering</div>
			<div class="mt-1 text-sm text-white/55">
				use svg-based liquid glass effects when your browser supports it.
			</div>
			<div class="mt-4 flex items-center justify-between">
				<span id="svg-liquid-glass-label" class="text-sm text-white/70"
					>enable svg liquid glass</span
				>
				<Switch
					size="md"
					checked={svgLiquidGlassEnabled}
					onchange={setSvgLiquidGlass}
					ariaLabelledbyId="svg-liquid-glass-label"
				/>
			</div>
		</div>
	</div>
</SettingsSectionLayout>
