<script lang="ts">
	// ported from odysseus (odysseus-dev/odysseus, AGPL-3.0-or-later) static/js/theme.js `_initPerlinFlow`
	import { startWallpaperLoop } from '$lib/components/backgrounds/wallpaperLoop'
	import { createOnceCallback } from '$lib/utils/once'
	import { onDestroy, onMount } from 'svelte'

	interface Props {
		onReady?: () => void
		color?: string
		backgroundColor?: string
		intensity?: number
		particleCount?: number
		fadeAlpha?: number
		noiseScale?: number
		timeScale?: number
		speed?: number
		dotRadius?: number
		lifeDecay?: number
	}

	let {
		onReady,
		color = '#00ff41',
		backgroundColor = '#000000',
		intensity = 0.8,
		particleCount = 200,
		fadeAlpha = 0.02,
		noiseScale = 0.004,
		timeScale = 0.0008,
		speed = 1,
		dotRadius = 1,
		lifeDecay = 0.001,
	}: Props = $props()

	const signalReady = createOnceCallback(() => onReady?.())

	interface Particle {
		x: number
		y: number
		life: number
	}

	let containerRef: HTMLDivElement
	let canvasRef: HTMLCanvasElement
	let ctx: CanvasRenderingContext2D | null = null
	let stopFrameLoop: (() => void) | null = null
	let resizeObserver: ResizeObserver | null = null
	let width = 0
	let height = 0
	let particles: Particle[] = []
	let t = 0

	function hexToRgb(hex: string): [number, number, number] {
		const m = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex)
		if (!m) return [0, 0, 0]
		return [parseInt(m[1], 16), parseInt(m[2], 16), parseInt(m[3], 16)]
	}

	// the trails come from never clearing: each frame paints the base color at a
	// very low alpha, so older dots decay into it instead of vanishing
	const fadeStyle = $derived.by(() => {
		const [r, g, b] = hexToRgb(backgroundColor)
		return `rgba(${r},${g},${b},${fadeAlpha})`
	})

	function noise2d(x: number, y: number): number {
		const n = Math.sin(x * 12.9898 + y * 78.233) * 43758.5453
		return n - Math.floor(n)
	}

	function smoothNoise(x: number, y: number): number {
		const ix = Math.floor(x)
		const iy = Math.floor(y)
		const fx = x - ix
		const fy = y - iy
		const a = noise2d(ix, iy)
		const b = noise2d(ix + 1, iy)
		const c = noise2d(ix, iy + 1)
		const d = noise2d(ix + 1, iy + 1)
		const ux = fx * fx * (3 - 2 * fx)
		const uy = fy * fy * (3 - 2 * fy)
		return a + (b - a) * ux + (c - a) * uy + (a - b - c + d) * ux * uy
	}

	function makeParticle(): Particle {
		return { x: Math.random() * width, y: Math.random() * height, life: Math.random() }
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

		while (particles.length < particleCount) particles.push(makeParticle())
		if (particles.length > particleCount) particles.length = particleCount

		ctx.fillStyle = fadeStyle
		ctx.fillRect(0, 0, width, height)

		for (const p of particles) {
			const n = smoothNoise(p.x * noiseScale + t * timeScale, p.y * noiseScale + 100)
			const angle = n * Math.PI * 6
			const step = speed * (1 + smoothNoise(p.x * 0.003, p.y * 0.003 + 50) * 1.5)
			p.x += Math.cos(angle) * step * frameScale
			p.y += Math.sin(angle) * step * frameScale
			p.life -= lifeDecay * frameScale
			if (p.life <= 0 || p.x < 0 || p.x > width || p.y < 0 || p.y > height) {
				p.x = Math.random() * width
				p.y = Math.random() * height
				p.life = 1
			}
			ctx.beginPath()
			ctx.arc(p.x, p.y, dotRadius, 0, Math.PI * 2)
			ctx.fillStyle = color
			ctx.globalAlpha = p.life * 0.15
			ctx.fill()
		}

		ctx.globalAlpha = 1
		t += frameScale
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
		particles = []
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
