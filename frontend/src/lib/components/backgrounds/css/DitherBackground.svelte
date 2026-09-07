<script lang="ts">
	// ported from hermes (nousresearch/hermes-agent, MIT) hermes_cli/dashboard_auth/login_page.py
	import { createOnceCallback } from '$lib/utils/once'
	import { onMount } from 'svelte'

	interface Props {
		onReady?: () => void
		color?: string
		accentColor?: string
		glowStrength?: number
		glowSpread?: number
		dotStrength?: number
		dotSize?: number
	}

	let {
		onReady,
		color = '#170d02',
		accentColor = '#ffac02',
		glowStrength = 6,
		glowSpread = 55,
		dotStrength = 4,
		dotSize = 3,
	}: Props = $props()

	const signalReady = createOnceCallback(() => onReady?.())

	// static surface: an elliptical glow at the top over a halftone dot grid.
	// the conic gradient tiled at `dotSize` is the hermes design-system `.dither`
	const layers = $derived(
		[
			`radial-gradient(ellipse at top, color-mix(in srgb, ${accentColor} ${glowStrength}%, transparent) 0%, transparent ${glowSpread}%)`,
			`repeating-conic-gradient(color-mix(in srgb, ${accentColor} ${dotStrength}%, transparent) 0% 25%, transparent 0% 50%)`,
		].join(', ')
	)

	onMount(() => signalReady())
</script>

<div
	class="absolute inset-0 overflow-hidden"
	style="background-color: {color}; background-image: {layers}; background-size: auto, {dotSize}px {dotSize}px"
></div>
