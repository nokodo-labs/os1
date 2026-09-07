<script lang="ts">
	// ported from odysseus (odysseus-dev/odysseus, AGPL-3.0-or-later) static/js/theme.js `_initConstellations`
	import { startWallpaperLoop } from '$lib/components/backgrounds/wallpaperLoop'
	import { createOnceCallback } from '$lib/utils/once'
	import { onDestroy, onMount } from 'svelte'

	interface Props {
		onReady?: () => void
		color?: string
		backgroundColor?: string
		intensity?: number
		starCount?: number
		connectDistance?: number
		driftSpeed?: number
		twinkleSpeed?: number
	}

	let {
		onReady,
		color = '#64d2ff',
		backgroundColor = '#0b1a2c',
		intensity = 1,
		starCount = 50,
		connectDistance = 120,
		driftSpeed = 0.15,
		twinkleSpeed = 0.01,
	}: Props = $props()

	const signalReady = createOnceCallback(() => onReady?.())

	interface Star {
		x: number
		y: number
		vx: number
		vy: number
		r: number
		phase: number
	}

	let containerRef: HTMLDivElement
	let canvasRef: HTMLCanvasElement
	let ctx: CanvasRenderingContext2D | null = null
	let stopFrameLoop: (() => void) | null = null
	let resizeObserver: ResizeObserver | null = null
	let width = 0
	let height = 0
	let stars: Star[] = []
	let t = 0

	function makeStar(): Star {
		return {
			x: Math.random() * width,
			y: Math.random() * height,
			vx: (Math.random() - 0.5) * driftSpeed,
			vy: (Math.random() - 0.5) * driftSpeed,
			r: 0.8 + Math.random() * 0.8,
			phase: Math.random() * Math.PI * 2,
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
		// odysseus re-seeds the field on every resize so the spread stays even
		stars = []
	}

	function render(_nowMs: number, dtMs: number): void {
		if (!ctx) return
		const frameScale = Math.min(dtMs / (1000 / 60), 3)

		while (stars.length < starCount) stars.push(makeStar())
		if (stars.length > starCount) stars.length = starCount

		t += twinkleSpeed * frameScale
		ctx.clearRect(0, 0, width, height)

		// move stars gently, wrapping at the edges
		for (const s of stars) {
			s.x += s.vx * frameScale
			s.y += s.vy * frameScale
			if (s.x < 0) s.x = width
			if (s.x > width) s.x = 0
			if (s.y < 0) s.y = height
			if (s.y > height) s.y = 0
		}

		// draw connections
		ctx.strokeStyle = color
		ctx.lineWidth = 0.5
		for (let i = 0; i < stars.length; i++) {
			for (let j = i + 1; j < stars.length; j++) {
				const dx = stars[i].x - stars[j].x
				const dy = stars[i].y - stars[j].y
				const dist = Math.sqrt(dx * dx + dy * dy)
				if (dist < connectDistance) {
					ctx.globalAlpha = (1 - dist / connectDistance) * 0.15
					ctx.beginPath()
					ctx.moveTo(stars[i].x, stars[i].y)
					ctx.lineTo(stars[j].x, stars[j].y)
					ctx.stroke()
				}
			}
		}

		// draw stars with subtle twinkle
		ctx.fillStyle = color
		for (const s of stars) {
			const twinkle = 0.5 + 0.5 * Math.sin(t * 2 + s.phase)
			ctx.globalAlpha = 0.15 + twinkle * 0.25
			ctx.beginPath()
			ctx.arc(s.x, s.y, s.r, 0, Math.PI * 2)
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
		stars = []
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
