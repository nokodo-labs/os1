<script lang="ts">
	// ported from odysseus (odysseus-dev/odysseus, AGPL-3.0-or-later) static/js/theme.js `_initSynapse`
	import { startWallpaperLoop } from '$lib/components/backgrounds/wallpaperLoop'
	import { createOnceCallback } from '$lib/utils/once'
	import { onDestroy, onMount } from 'svelte'

	interface Props {
		onReady?: () => void
		color?: string
		backgroundColor?: string
		intensity?: number
		grid?: number
		gridStrength?: number
		maxPulses?: number
		spawnChance?: number
		speedMin?: number
		speedMax?: number
		trailLength?: number
	}

	let {
		onReady,
		color = '#0ff0fc',
		backgroundColor = '#0a0a0f',
		intensity = 1,
		grid = 24,
		gridStrength = 3.5,
		maxPulses = 20,
		spawnChance = 0.12,
		speedMin = 2,
		speedMax = 22,
		trailLength = 12,
	}: Props = $props()

	const signalReady = createOnceCallback(() => onReady?.())

	// the grid itself is the CSS layer below; the canvas only carries the pulses
	const gridMix = $derived(
		`color-mix(in srgb, ${color} calc(${gridStrength}% * ${intensity}), transparent)`
	)

	interface Pulse {
		x: number
		y: number
		dx: number
		dy: number
	}

	let containerRef: HTMLDivElement
	let canvasRef: HTMLCanvasElement
	let ctx: CanvasRenderingContext2D | null = null
	let stopFrameLoop: (() => void) | null = null
	let resizeObserver: ResizeObserver | null = null
	let width = 0
	let height = 0
	let pulses: Pulse[] = []

	function resize(): void {
		if (!ctx || !containerRef || !canvasRef) return
		const dpr = Math.min(window.devicePixelRatio || 1, 2)
		const rect = containerRef.getBoundingClientRect()
		width = Math.max(1, Math.round(rect.width))
		height = Math.max(1, Math.round(rect.height))
		canvasRef.width = Math.max(1, Math.round(width * dpr))
		canvasRef.height = Math.max(1, Math.round(height * dpr))
		ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
	}

	function spawnPulse(): void {
		const speed = speedMin + Math.random() * (speedMax - speedMin)
		if (Math.random() > 0.5) {
			// horizontal - pick a grid row
			const row = Math.floor(Math.random() * (Math.ceil(height / grid) + 1))
			pulses.push({ x: -trailLength, y: row * grid, dx: speed, dy: 0 })
		} else {
			// vertical - pick a grid column
			const col = Math.floor(Math.random() * (Math.ceil(width / grid) + 1))
			pulses.push({ x: col * grid, y: -trailLength, dx: 0, dy: speed })
		}
	}

	function render(_nowMs: number, dtMs: number): void {
		if (!ctx) return
		// odysseus advances by whole pixels per animation frame; scaling by the
		// elapsed 60fps-equivalent keeps that speed on any refresh rate
		const frameScale = Math.min(dtMs / (1000 / 60), 3)

		ctx.clearRect(0, 0, width, height)

		if (pulses.length < maxPulses && Math.random() < spawnChance * frameScale) spawnPulse()

		for (let i = pulses.length - 1; i >= 0; i--) {
			const p = pulses[i]
			p.x += p.dx * frameScale
			p.y += p.dy * frameScale

			if (p.x > width + trailLength || p.y > height + trailLength) {
				pulses.splice(i, 1)
				continue
			}

			// trail - line gradient fading behind the dot
			const tx = p.x - (p.dx > 0 ? trailLength : 0)
			const ty = p.y - (p.dy > 0 ? trailLength : 0)
			const gradient = ctx.createLinearGradient(tx, ty, p.x, p.y)
			gradient.addColorStop(0, 'transparent')
			gradient.addColorStop(1, color)
			ctx.strokeStyle = gradient
			ctx.globalAlpha = 0.35
			ctx.lineWidth = 1
			ctx.beginPath()
			ctx.moveTo(tx, ty)
			ctx.lineTo(p.x, p.y)
			ctx.stroke()

			// bright dot at head
			ctx.globalAlpha = 0.55
			ctx.fillStyle = color
			ctx.beginPath()
			ctx.arc(p.x, p.y, 1.2, 0, Math.PI * 2)
			ctx.fill()
		}

		ctx.globalAlpha = 1
	}

	onMount(() => {
		const context = canvasRef.getContext('2d')
		if (!context) {
			console.error('2d canvas not supported')
			signalReady()
			return
		}

		ctx = context
		resize()
		resizeObserver = new ResizeObserver(() => resize())
		resizeObserver.observe(containerRef)

		stopFrameLoop = startWallpaperLoop(render)
		requestAnimationFrame(() => signalReady())
	})

	onDestroy(() => {
		stopFrameLoop?.()
		stopFrameLoop = null
		resizeObserver?.disconnect()
		resizeObserver = null
		pulses = []
		ctx = null
	})
</script>

<div
	class="absolute inset-0 overflow-hidden"
	style="background-color: {backgroundColor}"
	bind:this={containerRef}
>
	<div
		class="pointer-events-none absolute inset-0"
		style="background-image: linear-gradient({gridMix} 1px, transparent 1px), linear-gradient(90deg, {gridMix} 1px, transparent 1px); background-size: {grid}px {grid}px"
	></div>

	<canvas
		class="pointer-events-none absolute inset-0 block h-full w-full"
		style="opacity: {intensity}"
		bind:this={canvasRef}
	></canvas>
</div>
