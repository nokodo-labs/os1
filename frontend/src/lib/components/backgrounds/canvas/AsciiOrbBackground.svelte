<script lang="ts">
	// ported from hermes (nousresearch/hermes-agent, MIT) skills/creative/pretext/templates/donut-orbit.html
	import { startWallpaperLoop } from '$lib/components/backgrounds/wallpaperLoop'
	import { createOnceCallback } from '$lib/utils/once'
	import { onDestroy, onMount, untrack } from 'svelte'

	export type AsciiOrbShape = 'sphere' | 'cube'

	interface Props {
		onReady?: () => void
		color?: string
		backgroundColor?: string
		fontSize?: number
		radius?: number
		zoom?: number
		spin?: number
		tilt?: number
		wire?: number
		latitudes?: number
		longitudes?: number
		shape?: AsciiOrbShape
		cubeScale?: number
		morphDuration?: number
		buildDuration?: number
	}

	let {
		onReady,
		color = '#ffe6cb',
		backgroundColor = '#041c1c',
		fontSize = 8,
		radius = 0.135,
		zoom = 3,
		spin = 0.18,
		tilt = 0.55,
		wire = 0.2,
		latitudes = 19,
		longitudes = 30,
		shape = 'sphere',
		cubeScale = 1.8,
		morphDuration = 0.65,
		buildDuration = 1.45,
	}: Props = $props()

	const signalReady = createOnceCallback(() => onReady?.())

	// glyph ramp, darkest to densest - the whole orb is drawn out of these
	const CHARS = ' ·:;+=░▒▓█'
	const CHARS_LAST = CHARS.length - 1

	const CUBE_VERTS: readonly (readonly [number, number, number])[] = [
		[-1, -1, -1],
		[1, -1, -1],
		[1, 1, -1],
		[-1, 1, -1],
		[-1, -1, 1],
		[1, -1, 1],
		[1, 1, 1],
		[-1, 1, 1],
	]
	const CUBE_EDGES: readonly (readonly [number, number])[] = [
		[0, 1],
		[1, 2],
		[2, 3],
		[3, 0],
		[4, 5],
		[5, 6],
		[6, 7],
		[7, 4],
		[0, 4],
		[1, 5],
		[2, 6],
		[3, 7],
	]

	// the ascii grid is coarse, so a full 60fps buys nothing but battery drain
	const MAX_FPS = 30

	interface ProjectedVertex {
		x: number
		y: number
		d: number
	}

	type AtlasSurface = OffscreenCanvas | HTMLCanvasElement
	type AtlasContext = OffscreenCanvasRenderingContext2D | CanvasRenderingContext2D

	interface Atlas {
		surface: AtlasSurface
		context: AtlasContext
	}

	let containerRef: HTMLDivElement
	let canvasRef: HTMLCanvasElement
	let ctx: CanvasRenderingContext2D | null = null
	let stopFrameLoop: (() => void) | null = null
	let resizeObserver: ResizeObserver | null = null

	let width = 0
	let height = 0
	let dpr = 1
	let cellWidth = 4.8
	let cellHeight = 8
	let cols = 0
	let rows = 0
	let glyphs = new Uint8Array(0)
	// eased sphere <-> cube blend, driven per frame instead of a tween library.
	// seeded from the initial shape so mounting on 'cube' does not morph in
	let morph = untrack(() => (shape === 'cube' ? 1 : 0))

	// every ramp glyph is rasterized once into an offscreen strip, so the frame
	// loop blits cells instead of paying for text shaping on each of them
	let atlas: Atlas | null = null
	let atlasKey = ''
	let tileWidth = 0
	let tileHeight = 0
	// top-left device pixel of the tile that lands on each column/row
	let colOffsets = new Int32Array(0)
	let rowOffsets = new Int32Array(0)

	function hash(x: number, y: number): number {
		const n = Math.sin(x * 127.1 + y * 311.7) * 43758.5453
		return n - Math.floor(n)
	}

	/** distance from `v` to the nearest multiple of `step` - draws the wire grid */
	function gridDist(v: number, step: number): number {
		return Math.abs(v / step - Math.round(v / step)) * step
	}

	function rot(a: number, b: number, angle: number): [number, number] {
		const c = Math.cos(angle)
		const s = Math.sin(angle)
		return [a * c - b * s, a * s + b * c]
	}

	function rotateVec(
		vx: number,
		vy: number,
		vz: number,
		orbitX: number,
		orbitY: number
	): [number, number, number] {
		const [ry, rz] = rot(vy, vz, orbitX)
		const [rx, rz2] = rot(vx, rz, orbitY)
		return [rx, ry, rz2]
	}

	function paint(index: number, value: number): void {
		// a non-positive value can never beat the zeroed cell, so blanks stay blank
		if (value > glyphs[index]) glyphs[index] = value
	}

	function measure(): void {
		if (!ctx) return
		ctx.font = `${fontSize}px monospace`
		cellWidth = ctx.measureText('M').width || cellWidth
		cellHeight = fontSize
	}

	function createAtlas(): Atlas | null {
		if (typeof OffscreenCanvas !== 'undefined') {
			const surface = new OffscreenCanvas(1, 1)
			const context = surface.getContext('2d')
			return context ? { surface, context } : null
		}
		if (typeof document === 'undefined') return null
		const surface = document.createElement('canvas')
		const context = surface.getContext('2d')
		return context ? { surface, context } : null
	}

	/** ink extent from `measureText`, ignoring the values older engines omit */
	function inkExtent(value: number): number {
		return Number.isFinite(value) && value > 0 ? value : 0
	}

	function atlasSignature(): string {
		return `${fontSize}|${dpr}|${color}`
	}

	function buildAtlas(): void {
		atlas ??= createAtlas()
		if (!atlas) return

		const { surface, context } = atlas
		const fontPx = Math.max(1, fontSize * dpr)
		const font = `${fontPx}px monospace`

		context.font = font
		context.textAlign = 'center'
		context.textBaseline = 'middle'

		// size tiles from real ink extents: the block glyphs overflow their cell,
		// and that overflow is what makes dense areas read as solid
		let halfWidth = cellWidth * dpr * 0.5
		let halfHeight = fontPx * 0.5
		for (let i = 1; i < CHARS.length; i++) {
			const metrics = context.measureText(CHARS[i])
			halfWidth = Math.max(
				halfWidth,
				inkExtent(metrics.actualBoundingBoxLeft),
				inkExtent(metrics.actualBoundingBoxRight)
			)
			halfHeight = Math.max(
				halfHeight,
				inkExtent(metrics.actualBoundingBoxAscent),
				inkExtent(metrics.actualBoundingBoxDescent)
			)
		}

		// even dimensions keep the glyph anchor on the exact tile centre
		tileWidth = Math.ceil(halfWidth) * 2 + 2
		tileHeight = Math.ceil(halfHeight) * 2 + 2

		const stripWidth = tileWidth * CHARS.length
		if (surface.width !== stripWidth || surface.height !== tileHeight) {
			surface.width = stripWidth
			surface.height = tileHeight
		}
		context.clearRect(0, 0, stripWidth, tileHeight)
		context.font = font
		context.textAlign = 'center'
		context.textBaseline = 'middle'
		context.fillStyle = color

		const centerY = tileHeight * 0.5
		for (let i = 1; i < CHARS.length; i++) {
			context.fillText(CHARS[i], i * tileWidth + tileWidth * 0.5, centerY)
		}
	}

	function updateCellOffsets(): void {
		if (colOffsets.length !== cols) colOffsets = new Int32Array(cols)
		if (rowOffsets.length !== rows) rowOffsets = new Int32Array(rows)

		const halfTileWidth = tileWidth * 0.5
		const halfTileHeight = tileHeight * 0.5
		for (let c = 0; c < cols; c++) {
			colOffsets[c] = Math.round((c * cellWidth + cellWidth * 0.5) * dpr - halfTileWidth)
		}
		for (let r = 0; r < rows; r++) {
			rowOffsets[r] = Math.round((r * cellHeight + cellHeight * 0.5) * dpr - halfTileHeight)
		}
	}

	function resize(): void {
		if (!ctx || !containerRef || !canvasRef) return

		dpr = Math.min(window.devicePixelRatio || 1, 2)
		const rect = containerRef.getBoundingClientRect()
		const nextWidth = Math.max(1, Math.floor(rect.width))
		const nextHeight = Math.max(1, Math.floor(rect.height))
		const canvasWidth = Math.floor(nextWidth * dpr)
		const canvasHeight = Math.floor(nextHeight * dpr)

		if (canvasRef.width !== canvasWidth || canvasRef.height !== canvasHeight) {
			canvasRef.width = canvasWidth
			canvasRef.height = canvasHeight
		}

		width = nextWidth
		height = nextHeight
		// cells are laid out in css pixels but blitted in device pixels, so the
		// context itself stays untransformed
		ctx.setTransform(1, 0, 0, 1, 0, 0)
		measure()

		cols = Math.ceil(width / cellWidth)
		rows = Math.ceil(height / cellHeight)
		const cells = cols * rows
		if (glyphs.length !== cells) glyphs = new Uint8Array(cells)

		const key = atlasSignature()
		if (atlasKey !== key) {
			atlasKey = key
			buildAtlas()
		}
		updateCellOffsets()
	}

	function projectCube(
		centerX: number,
		centerY: number,
		radiusPx: number,
		orbitX: number,
		orbitY: number,
		scale: number
	): ProjectedVertex[] {
		const camZ = 3.3
		const projScale = radiusPx * 1.34 * scale
		return CUBE_VERTS.map(([vx, vy, vz]) => {
			const [rx, ry, rz] = rotateVec(vx, vy, vz, orbitX, orbitY)
			const inv = 1 / (camZ + rz)
			return {
				x: centerX + rx * projScale * inv,
				y: centerY + ry * projScale * inv,
				d: (rz + 1) * 0.5,
			}
		})
	}

	function rasterizeCube(
		centerX: number,
		centerY: number,
		radiusPx: number,
		buildPhase: number,
		orbitX: number,
		orbitY: number,
		weight: number
	): void {
		const unit = Math.max(1, Math.min(cellWidth, cellHeight))
		const wirePx = Math.max(1, wire * radiusPx * 0.17)
		const brush = Math.max(0, Math.ceil((wirePx - unit * 0.45) / unit))
		const projected = projectCube(centerX, centerY, radiusPx, orbitX, orbitY, cubeScale)

		for (let ei = 0; ei < CUBE_EDGES.length; ei++) {
			const [a, b] = CUBE_EDGES[ei]
			const p0 = projected[a]
			const p1 = projected[b]
			const dx = p1.x - p0.x
			const dy = p1.y - p0.y
			const len = Math.hypot(dx, dy)
			const steps = Math.max(2, Math.ceil(len / Math.max(1, unit * 0.45)))

			for (let s = 0; s <= steps; s++) {
				const t = s / steps
				const depth = p0.d + (p1.d - p0.d) * t
				const col = Math.floor((p0.x + dx * t) / cellWidth)
				const row = Math.floor((p0.y + dy * t) / cellHeight)

				for (let oy = -brush; oy <= brush; oy++) {
					for (let ox = -brush; ox <= brush; ox++) {
						if (brush > 0 && ox * ox + oy * oy > brush * brush + 0.25) continue
						const cc = col + ox
						const rr = row + oy
						if (rr < 0 || rr >= rows || cc < 0 || cc >= cols) continue

						const reveal = buildPhase * 1.45 - hash(cc + ei * 13, rr + ei * 17) * 0.5
						if (buildPhase < 1 && reveal <= 0) continue

						const value =
							buildPhase < 1
								? Math.min(CHARS_LAST, Math.floor(reveal * CHARS_LAST))
								: Math.min(
										CHARS_LAST,
										Math.floor((0.45 + depth * 0.55) * CHARS_LAST)
									)
						paint(rr * cols + cc, Math.min(CHARS_LAST, Math.floor(value * weight)))
					}
				}
			}
		}
	}

	function rasterizeSphere(
		centerX: number,
		centerY: number,
		radiusPx: number,
		radiusNorm: number,
		buildPhase: number,
		orbitX: number,
		orbitY: number,
		weight: number
	): void {
		const latStep = Math.PI / Math.max(1, latitudes)
		const lonStep = (Math.PI * 2) / Math.max(1, longitudes)
		const pad = 15.5
		const rMin = Math.max(0, Math.floor((centerY - radiusPx - pad) / cellHeight))
		const rMax = Math.min(rows - 1, Math.ceil((centerY + radiusPx + pad) / cellHeight))
		const cMin = Math.max(0, Math.floor((centerX - radiusPx - pad) / cellWidth))
		const cMax = Math.min(cols - 1, Math.ceil((centerX + radiusPx + pad) / cellWidth))
		const aspect = width / height

		for (let r = rMin; r <= rMax; r++) {
			const y = r * cellHeight + cellHeight * 0.5
			const py = y / height - 0.5

			for (let c = cMin; c <= cMax; c++) {
				const x = c * cellWidth + cellWidth * 0.5
				// px normalizes on width then re-applies aspect, which is what keeps
				// the sphere circular on screen rather than stretched by the cell grid
				const px = (x / width - 0.5) * aspect
				const d2 = px * px + py * py
				if (d2 > radiusNorm * radiusNorm) continue

				const pz = Math.sqrt(radiusNorm * radiusNorm - d2)
				const depth = (pz / radiusNorm) * 0.5 + 0.5
				const [sx, sy, sz] = rotateVec(
					px / radiusNorm,
					py / radiusNorm,
					pz / radiusNorm,
					orbitX,
					orbitY
				)

				const latD = gridDist(
					Math.asin(Math.max(-1, Math.min(1, sy))) + Math.PI / 2,
					latStep
				)
				const lonD = gridDist(Math.atan2(sz, sx) + Math.PI, lonStep)
				const lineWidth = wire * (0.3 + depth * 0.7)
				const minD = Math.min(latD, lonD)
				if (minD > lineWidth) continue

				const reveal = buildPhase * 1.5 - hash(c, r) * 0.5
				if (buildPhase < 1 && reveal <= 0) continue

				const edge = 1 - minD / lineWidth
				const value =
					buildPhase < 1
						? Math.min(CHARS_LAST, Math.floor(reveal * CHARS_LAST))
						: Math.min(
								CHARS_LAST,
								Math.floor(edge * (0.4 + depth * 0.6) * CHARS.length)
							)
				paint(r * cols + c, Math.min(CHARS_LAST, Math.floor(value * weight)))
			}
		}
	}

	function render(nowMs: number, dtMs: number): void {
		if (!ctx) return
		if (atlasKey !== atlasSignature()) resize()
		if (cols === 0 || rows === 0) return

		const time = nowMs / 1000
		const target = shape === 'cube' ? 1 : 0
		const step = dtMs / Math.max(1, morphDuration * 1000)
		morph += Math.sign(target - morph) * Math.min(step, Math.abs(target - morph))
		const mix = morph * morph * (3 - 2 * morph)

		glyphs.fill(0)

		const centerX = width * 0.5
		const centerY = height * 0.5
		const radiusNorm = radius * zoom
		const radiusPx = radiusNorm * height
		const buildPhase = Math.min(1, Math.max(0, time / Math.max(0.001, buildDuration)))

		if (mix > 0.001) {
			rasterizeCube(
				centerX,
				centerY,
				radiusPx,
				buildPhase,
				tilt + time * spin * 0.72,
				time * spin * 1.35,
				mix
			)
		}
		if (mix < 0.999) {
			rasterizeSphere(
				centerX,
				centerY,
				radiusPx,
				radiusNorm,
				buildPhase,
				tilt,
				time * spin,
				1 - mix
			)
		}

		ctx.fillStyle = backgroundColor
		ctx.fillRect(0, 0, canvasRef.width, canvasRef.height)
		if (!atlas) return

		const surface = atlas.surface
		for (let r = 0; r < rows; r++) {
			const base = r * cols
			const y = rowOffsets[r]
			for (let c = 0; c < cols; c++) {
				const glyph = glyphs[base + c]
				// index 0 is the ramp's blank - the cleared background already is it
				if (glyph === 0) continue
				ctx.drawImage(
					surface,
					glyph * tileWidth,
					0,
					tileWidth,
					tileHeight,
					colOffsets[c],
					y,
					tileWidth,
					tileHeight
				)
			}
		}
	}

	onMount(() => {
		const context = canvasRef.getContext('2d')
		if (!context) {
			signalReady()
			return
		}

		ctx = context
		resize()

		resizeObserver = new ResizeObserver(() => resize())
		resizeObserver.observe(containerRef)

		stopFrameLoop = startWallpaperLoop(render, { maxFps: MAX_FPS })
		requestAnimationFrame(() => signalReady())
	})

	onDestroy(() => {
		stopFrameLoop?.()
		stopFrameLoop = null
		resizeObserver?.disconnect()
		resizeObserver = null
		atlas = null
	})
</script>

<div class="absolute inset-0 overflow-hidden" bind:this={containerRef}>
	<canvas
		class="pointer-events-none absolute inset-0 block h-full w-full"
		style="background-color: {backgroundColor}"
		bind:this={canvasRef}
	></canvas>
</div>
