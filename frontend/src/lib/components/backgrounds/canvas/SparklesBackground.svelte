<script lang="ts">
	// ported from odysseus (odysseus-dev/odysseus, AGPL-3.0-or-later) static/js/theme.js `_initSparkles`
	import { startWallpaperLoop } from '$lib/components/backgrounds/wallpaperLoop'
	import { createOnceCallback } from '$lib/utils/once'
	import { onDestroy, onMount } from 'svelte'

	interface Props {
		onReady?: () => void
		color?: string
		backgroundColor?: string
		intensity?: number
		size?: number
		count?: number
		twinkleSpeed?: number
	}

	let {
		onReady,
		color = '#ff8cb8',
		backgroundColor = '#fff0f5',
		intensity = 1,
		size = 1,
		count = 35,
		twinkleSpeed = 1,
	}: Props = $props()

	const signalReady = createOnceCallback(() => onReady?.())

	interface Sparkle {
		x: number
		y: number
		size: number
		phase: number
		speed: number
		life: number
	}

	let containerRef: HTMLDivElement
	let canvasRef: HTMLCanvasElement
	let ctx: CanvasRenderingContext2D | null = null
	let stopFrameLoop: (() => void) | null = null
	let resizeObserver: ResizeObserver | null = null
	let width = 0
	let height = 0
	let sparkles: Sparkle[] = []

	function makeSpark(): Sparkle {
		return {
			x: Math.random() * width,
			y: Math.random() * height,
			size: 2 + Math.random() * 5,
			phase: Math.random() * Math.PI * 2,
			speed: 0.015 + Math.random() * 0.03,
			life: 0.5 + Math.random() * 0.5,
		}
	}

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

	// 4-point star drawn from four quadratic curves pinched toward the centre
	function drawStar(
		context: CanvasRenderingContext2D,
		x: number,
		y: number,
		r: number,
		alpha: number
	): void {
		context.save()
		context.translate(x, y)
		context.fillStyle = color
		context.globalAlpha = alpha
		context.beginPath()
		context.moveTo(0, -r)
		context.quadraticCurveTo(r * 0.15, -r * 0.15, r, 0)
		context.quadraticCurveTo(r * 0.15, r * 0.15, 0, r)
		context.quadraticCurveTo(-r * 0.15, r * 0.15, -r, 0)
		context.quadraticCurveTo(-r * 0.15, -r * 0.15, 0, -r)
		context.fill()
		context.restore()
	}

	function render(_nowMs: number, dtMs: number): void {
		if (!ctx) return
		const frameScale = Math.min(dtMs / (1000 / 60), 3)

		while (sparkles.length < count) sparkles.push(makeSpark())
		if (sparkles.length > count) sparkles.length = count

		ctx.clearRect(0, 0, width, height)

		for (const s of sparkles) {
			s.phase += s.speed * twinkleSpeed * frameScale
			const twinkle = Math.sin(s.phase)
			const alpha = Math.max(0, twinkle) * 0.25 * s.life
			const scale = 0.5 + Math.max(0, twinkle) * 0.5
			if (alpha > 0.01) drawStar(ctx, s.x, s.y, s.size * scale * size, alpha)
			// respawn elsewhere once the twinkle cycle completes
			if (s.phase > Math.PI * 6) Object.assign(s, makeSpark())
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
		sparkles = []
		ctx = null
	})
</script>

<div
	class="absolute inset-0 overflow-hidden"
	style="background-color: {backgroundColor}"
	bind:this={containerRef}
>
	<canvas
		class="pointer-events-none absolute inset-0 block h-full w-full"
		style="opacity: {intensity}"
		bind:this={canvasRef}
	></canvas>
</div>
