<script lang="ts">
	// ported from odysseus (odysseus-dev/odysseus, AGPL-3.0-or-later) static/js/theme.js `_initRain`
	import { startWallpaperLoop } from '$lib/components/backgrounds/wallpaperLoop'
	import { createOnceCallback } from '$lib/utils/once'
	import { onDestroy, onMount } from 'svelte'

	interface Props {
		onReady?: () => void
		color?: string
		backgroundColor?: string
		intensity?: number
		size?: number
		maxDrops?: number
		spawnChance?: number
	}

	let {
		onReady,
		color = '#ffffff',
		backgroundColor = '#0d1117',
		intensity = 0.5,
		size = 1,
		maxDrops = 130,
		spawnChance = 0.6,
	}: Props = $props()

	const signalReady = createOnceCallback(() => onReady?.())

	interface Drop {
		x: number
		y: number
		len: number
		speed: number
		alpha: number
	}

	let containerRef: HTMLDivElement
	let canvasRef: HTMLCanvasElement
	let ctx: CanvasRenderingContext2D | null = null
	let stopFrameLoop: (() => void) | null = null
	let resizeObserver: ResizeObserver | null = null
	let width = 0
	let height = 0
	let drops: Drop[] = []

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

	function spawn(): void {
		const len = 20 + Math.random() * 40
		const speed = 4 + Math.random() * 8
		drops.push({
			x: Math.random() * width,
			y: -len,
			len,
			speed,
			alpha: 0.32 + Math.random() * 0.28,
		})
	}

	function render(_nowMs: number, dtMs: number): void {
		if (!ctx) return
		const frameScale = Math.min(dtMs / (1000 / 60), 3)

		ctx.clearRect(0, 0, width, height)

		// intensity also controls rain speed + spawn rate (feels slower/lighter when dim)
		const speedMult = 0.35 + intensity * 0.65

		if (
			drops.length < maxDrops * intensity &&
			Math.random() < spawnChance * intensity * frameScale
		) {
			spawn()
		}

		for (let i = drops.length - 1; i >= 0; i--) {
			const d = drops[i]
			d.y += d.speed * speedMult * frameScale
			if (d.y > height + d.len * size) {
				drops.splice(i, 1)
				continue
			}

			const effLen = d.len * size
			const gradient = ctx.createLinearGradient(d.x, d.y - effLen, d.x, d.y)
			gradient.addColorStop(0, 'transparent')
			gradient.addColorStop(1, color)
			ctx.strokeStyle = gradient
			ctx.globalAlpha = d.alpha
			ctx.lineWidth = 1.3 * Math.min(2, Math.max(0.6, size))
			ctx.beginPath()
			ctx.moveTo(d.x, d.y - effLen)
			ctx.lineTo(d.x, d.y)
			ctx.stroke()
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
		drops = []
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
