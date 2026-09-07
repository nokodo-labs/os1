<script lang="ts">
	// ported from odysseus (odysseus-dev/odysseus, AGPL-3.0-or-later) static/js/theme.js `_initPetals`
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
		fallSpeed?: number
	}

	let {
		onReady,
		color = '#f5c2e7',
		backgroundColor = '#2b1b2e',
		intensity = 1,
		size = 1,
		count = 30,
		fallSpeed = 1,
	}: Props = $props()

	const signalReady = createOnceCallback(() => onReady?.())

	interface Petal {
		x: number
		y: number
		size: number
		rot: number
		vr: number
		vy: number
		drift: number
		driftSpeed: number
		wobble: number
	}

	let containerRef: HTMLDivElement
	let canvasRef: HTMLCanvasElement
	let ctx: CanvasRenderingContext2D | null = null
	let stopFrameLoop: (() => void) | null = null
	let resizeObserver: ResizeObserver | null = null
	let width = 0
	let height = 0
	let petals: Petal[] = []

	function makePetal(): Petal {
		return {
			x: Math.random() * width,
			y: -10 - Math.random() * 40,
			size: 3 + Math.random() * 5,
			rot: Math.random() * Math.PI * 2,
			vr: (Math.random() - 0.5) * 0.03,
			vy: 0.3 + Math.random() * 0.6,
			drift: Math.random() * Math.PI * 2,
			driftSpeed: 0.008 + Math.random() * 0.012,
			wobble: 0.3 + Math.random() * 0.8,
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

	function render(_nowMs: number, dtMs: number): void {
		if (!ctx) return
		const frameScale = Math.min(dtMs / (1000 / 60), 3)

		// seed the first fill spread over the full height so it never starts empty
		while (petals.length < count) {
			const p = makePetal()
			p.y = Math.random() * height
			petals.push(p)
		}
		if (petals.length > count) petals.length = count

		ctx.clearRect(0, 0, width, height)

		for (const p of petals) {
			p.y += p.vy * fallSpeed * frameScale
			p.rot += p.vr * frameScale
			p.drift += p.driftSpeed * frameScale
			p.x += Math.sin(p.drift) * p.wobble * frameScale
			if (p.y > height + 15) Object.assign(p, makePetal())

			ctx.save()
			ctx.translate(p.x, p.y)
			ctx.rotate(p.rot)
			// petal shape - two overlapping ellipses at slightly different alphas
			ctx.globalAlpha = 0.2
			ctx.fillStyle = color
			ctx.beginPath()
			ctx.ellipse(
				-p.size * 0.2 * size,
				0,
				p.size * 0.6 * size,
				p.size * 0.3 * size,
				0.3,
				0,
				Math.PI * 2
			)
			ctx.fill()
			ctx.globalAlpha = 0.15
			ctx.beginPath()
			ctx.ellipse(
				p.size * 0.2 * size,
				0,
				p.size * 0.6 * size,
				p.size * 0.3 * size,
				-0.3,
				0,
				Math.PI * 2
			)
			ctx.fill()
			ctx.restore()
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
		petals = []
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
