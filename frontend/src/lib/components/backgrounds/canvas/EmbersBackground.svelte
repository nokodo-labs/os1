<script lang="ts">
	// ported from odysseus (odysseus-dev/odysseus, AGPL-3.0-or-later) static/js/theme.js `_initEmbers`
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
		fadeAlpha?: number
		sparkChance?: number
		burstChance?: number
		burstSize?: number
	}

	let {
		onReady,
		color = '#e94560',
		backgroundColor = '#1a1a2e',
		intensity = 1,
		size = 1,
		count = 60,
		fadeAlpha = 0.18,
		sparkChance = 0.003,
		burstChance = 0.015,
		burstSize = 5,
	}: Props = $props()

	const signalReady = createOnceCallback(() => onReady?.())

	interface Ember {
		x: number
		y: number
		vx: number
		vy: number
		r: number
		life: number
		maxLife: number
		wobble: number
		spark: boolean
	}

	let containerRef: HTMLDivElement
	let canvasRef: HTMLCanvasElement
	let ctx: CanvasRenderingContext2D | null = null
	let stopFrameLoop: (() => void) | null = null
	let resizeObserver: ResizeObserver | null = null
	let width = 0
	let height = 0
	let embers: Ember[] = []

	function hexToRgb(hex: string): [number, number, number] {
		const m = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex)
		if (!m) return [255, 255, 255]
		return [parseInt(m[1], 16), parseInt(m[2], 16), parseInt(m[3], 16)]
	}

	const emberRgb = $derived(hexToRgb(color))

	function rgba(rgb: [number, number, number], a: number): string {
		return `rgba(${rgb[0]},${rgb[1]},${rgb[2]},${a})`
	}

	function makeEmber(): Ember {
		return {
			x: Math.random() * width,
			y: height + Math.random() * 40,
			vx: (Math.random() - 0.5) * 0.3,
			vy: -0.3 - Math.random() * 0.8,
			r: 0.3 + Math.random() * 0.6,
			life: 0,
			maxLife: 220 + Math.random() * 220,
			wobble: Math.random() * Math.PI * 2,
			spark: false,
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
		const rgb = emberRgb

		// seed the first fill mid-flight so the column is already populated
		while (embers.length < count) {
			const e = makeEmber()
			e.y = Math.random() * height
			e.life = Math.random() * e.maxLife
			embers.push(e)
		}

		// fade the previous frame via destination-out, which keeps the canvas
		// transparent where no ember has been instead of smearing a black box
		ctx.globalCompositeOperation = 'destination-out'
		ctx.fillStyle = `rgba(0,0,0,${fadeAlpha})`
		ctx.fillRect(0, 0, width, height)
		ctx.globalCompositeOperation = 'lighter'

		for (let i = embers.length - 1; i >= 0; i--) {
			const e = embers[i]
			e.wobble += 0.03 * frameScale
			e.x += (e.vx + Math.sin(e.wobble) * 0.5) * frameScale
			e.y += e.vy * frameScale
			e.life += frameScale
			if (e.life > e.maxLife || e.y < -20) {
				embers.splice(i, 1)
				if (embers.length < count + 10) embers.push(makeEmber())
				continue
			}
			if (!e.spark && Math.random() < sparkChance * frameScale) e.spark = true

			const lifeRatio = e.life / e.maxLife
			const fade = Math.min(1, Math.min(lifeRatio * 4, (1 - lifeRatio) * 3))
			const r = e.r * (e.spark ? 2.4 : 1) * size
			const a = (e.spark ? 0.9 : 0.55) * fade

			const glow = ctx.createRadialGradient(e.x, e.y, 0, e.x, e.y, r * 4)
			glow.addColorStop(0, rgba(rgb, a))
			glow.addColorStop(0.4, rgba(rgb, a * 0.3))
			glow.addColorStop(1, rgba(rgb, 0))
			ctx.fillStyle = glow
			ctx.fillRect(e.x - r * 4, e.y - r * 4, r * 8, r * 8)

			ctx.fillStyle = `rgba(255,255,255,${a * 0.6})`
			ctx.beginPath()
			ctx.arc(e.x, e.y, r * 0.5, 0, Math.PI * 2)
			ctx.fill()

			// spark is a single-frame flash, cleared as soon as it is drawn
			e.spark = false
		}

		if (Math.random() < burstChance * frameScale) {
			const bx = Math.random() * width
			for (let i = 0; i < burstSize; i++) {
				const e = makeEmber()
				e.x = bx + (Math.random() - 0.5) * 40
				e.y = height - 10
				e.vy *= 1.5
				embers.push(e)
			}
		}
		ctx.globalCompositeOperation = 'source-over'
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
		embers = []
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
