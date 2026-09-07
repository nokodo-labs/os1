<script lang="ts">
	// ported from hermes (nousresearch/hermes-agent, MIT) skills/creative/pretext/templates/hello-orb-flow.html
	import { startWallpaperLoop } from '$lib/components/backgrounds/wallpaperLoop'
	import { createOnceCallback } from '$lib/utils/once'
	import { onDestroy, onMount } from 'svelte'

	interface Props {
		onReady?: () => void
		color?: string
		haloColor?: string
		backgroundColor?: string
		coreOpacity?: number
		haloOpacity?: number
		radius?: number
		followPointer?: boolean
		drift?: number
		easing?: number
	}

	let {
		onReady,
		color = '#ffc878',
		haloColor = '#ff8c50',
		backgroundColor = '#0c0d10',
		coreOpacity = 0.35,
		haloOpacity = 0.1,
		radius = 45,
		followPointer = true,
		drift = 0.06,
		easing = 4,
	}: Props = $props()

	const signalReady = createOnceCallback(() => onReady?.())

	let containerRef: HTMLDivElement
	let stopFrameLoop: (() => void) | null = null
	// normalized 0..1 orb position; smoothed toward the pointer or the idle path
	let orbX = $state(0.45)
	let orbY = $state(0.5)
	let targetX = 0.45
	let targetY = 0.5
	let pointerSeen = false

	function handlePointerMove(event: PointerEvent): void {
		if (!followPointer || !containerRef) return
		const rect = containerRef.getBoundingClientRect()
		if (rect.width === 0 || rect.height === 0) return
		targetX = (event.clientX - rect.left) / rect.width
		targetY = (event.clientY - rect.top) / rect.height
		pointerSeen = true
	}

	function render(nowMs: number, dtMs: number): void {
		const time = nowMs / 1000

		if (!followPointer || !pointerSeen) {
			// two incommensurate periods, so the idle path never repeats exactly
			targetX = 0.45 + Math.sin(time * 0.11) * drift
			targetY = 0.5 + Math.cos(time * 0.17) * drift
		}

		// framerate-independent exponential ease toward the target
		const k = 1 - Math.exp((-easing * dtMs) / 1000)
		orbX += (targetX - orbX) * k
		orbY += (targetY - orbY) * k
	}

	onMount(() => {
		stopFrameLoop = startWallpaperLoop(render)
		signalReady()
	})

	onDestroy(() => {
		stopFrameLoop?.()
		stopFrameLoop = null
	})
</script>

<svelte:window onpointermove={handlePointerMove} />

<div
	class="absolute inset-0 overflow-hidden"
	style="background-color: {backgroundColor}"
	bind:this={containerRef}
>
	<div
		class="pointer-events-none absolute inset-0"
		style="background: radial-gradient(circle {radius}vmin at {orbX * 100}% {orbY *
			100}%, color-mix(in srgb, {color} {coreOpacity *
			100}%, transparent) 0%, color-mix(in srgb, {haloColor} {haloOpacity *
			100}%, transparent) 60%, transparent 100%)"
	></div>
</div>
