<script lang="ts">
	// ported from odysseus (odysseus-dev/odysseus, AGPL-3.0-or-later) static/style.css `body.bg-pattern-dots`
	import { createOnceCallback } from '$lib/utils/once'
	import { onMount } from 'svelte'

	interface Props {
		onReady?: () => void
		color?: string
		backgroundColor?: string
		intensity?: number
		spacing?: number
		strength?: number
		dotSize?: number
	}

	let {
		onReady,
		color = '#5a5248',
		backgroundColor = '#f0ebe3',
		intensity = 1,
		spacing = 20,
		strength = 5,
		dotSize = 1,
	}: Props = $props()

	const signalReady = createOnceCallback(() => onReady?.())

	// odysseus folds the intensity into the color-mix percentage rather than
	// fading the whole layer, so the dot edges stay crisp as it dims
	const mixed = $derived(
		`color-mix(in srgb, ${color} calc(${strength}% * ${intensity}), transparent)`
	)

	onMount(() => signalReady())
</script>

<div
	class="absolute inset-0 overflow-hidden"
	style="background-color: {backgroundColor}; background-image: radial-gradient({mixed} {dotSize}px, transparent {dotSize}px); background-size: {spacing}px {spacing}px"
></div>
