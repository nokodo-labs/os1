import { getCachedDisplacementMap, setCachedDisplacementMap } from './cache'
import type { SurfaceFunction } from './physics'
import { calculateDisplacement } from './physics'

export interface DisplacementMapConfig {
	width: number
	height: number
	bezelWidth: number
	thickness: number
	surfaceFn: SurfaceFunction
	cornerRadius?: number
	samples?: number
	/** normalized refraction strength for the flat interior (0-1) */
	innerRefraction?: number
	/** thickness of the flat glass body beyond the bezel (px) */
	glassThickness?: number
}

export interface DisplacementResult {
	imageDataUrl: string
	maxDisplacement: number
	scale: number
}

/**
 * signed distance from a point to the nearest edge of a rounded rectangle.
 * returns negative inside the shape, positive outside,
 * plus the outward normal direction (nx, ny) at that point.
 */
function roundedRectSDF(
	px: number,
	py: number,
	w: number,
	h: number,
	r: number
): { dist: number; nx: number; ny: number } {
	const ax = Math.abs(px - w / 2)
	const ay = Math.abs(py - h / 2)

	const bx = w / 2 - r
	const by = h / 2 - r

	const dx = Math.max(ax - bx, 0)
	const dy = Math.max(ay - by, 0)

	let dist: number
	let nx: number
	let ny: number

	if (dx > 0 && dy > 0) {
		const len = Math.sqrt(dx * dx + dy * dy)
		dist = len - r
		nx = dx / len
		ny = dy / len
	} else if (ax - bx > ay - by) {
		dist = ax - bx - r
		nx = 1
		ny = 0
	} else {
		dist = ay - by - r
		nx = 0
		ny = 1
	}

	if (px < w / 2) nx = -nx
	if (py < h / 2) ny = -ny

	return { dist, nx, ny }
}

function smootherstep(edge0: number, edge1: number, x: number): number {
	if (edge0 === edge1) return x < edge0 ? 0 : 1
	const t = Math.max(0, Math.min(1, (x - edge0) / (edge1 - edge0)))
	return t * t * t * (t * (t * 6 - 15) + 10)
}

/**
 * generate SVG displacement map from refraction calculations.
 * uses RED channel for X-axis, GREEN channel for Y-axis.
 * 128 = neutral (no displacement). values are normalized then
 * re-scaled via the feDisplacementMap `scale` attribute.
 *
 * supports rounded rectangles via cornerRadius (defaults to
 * min(width,height)/2 for a pill / circle shape).
 */
export function generateDisplacementMap(config: DisplacementMapConfig): DisplacementResult {
	const {
		width,
		height,
		bezelWidth,
		thickness,
		surfaceFn,
		samples = 127,
		innerRefraction = 0,
		glassThickness = 0,
	} = config
	const cornerRadius = config.cornerRadius ?? Math.min(width, height) / 2

	const surfaceName = surfaceFn.name || 'custom'
	const cacheKey = `${width}-${height}-${bezelWidth}-${thickness}-${cornerRadius}-${surfaceName}-${innerRefraction}-${glassThickness}`

	const cached = getCachedDisplacementMap(cacheKey)
	if (cached) {
		return {
			imageDataUrl: cached.imageDataUrl,
			maxDisplacement: cached.maxDisplacement,
			scale: cached.scale,
		}
	}

	const result = generateDisplacementMapInternal(
		width,
		height,
		bezelWidth,
		thickness,
		surfaceFn,
		cornerRadius,
		samples,
		innerRefraction,
		glassThickness
	)

	setCachedDisplacementMap(cacheKey, result)
	return result
}

function generateDisplacementMapInternal(
	width: number,
	height: number,
	bezelWidth: number,
	thickness: number,
	surfaceFn: SurfaceFunction,
	cornerRadius: number,
	samples: number,
	innerRefraction: number,
	glassThickness: number
): DisplacementResult {
	// pre-calculate displacement magnitudes along one radius
	const displacements: number[] = []
	let maxDisplacement = 0

	for (let i = 0; i <= samples; i++) {
		const distance = (i / samples) * bezelWidth
		const displacement = calculateDisplacement(
			distance,
			bezelWidth,
			surfaceFn,
			thickness,
			1.0,
			1.5,
			glassThickness
		)
		displacements.push(displacement)
		maxDisplacement = Math.max(maxDisplacement, Math.abs(displacement))
	}

	if (maxDisplacement === 0) maxDisplacement = 1

	const normalized = displacements.map((d) => d / maxDisplacement)

	const canvas = document.createElement('canvas')
	canvas.width = width
	canvas.height = height
	const ctx = canvas.getContext('2d')!
	const imageData = ctx.createImageData(width, height)

	for (let y = 0; y < height; y++) {
		for (let x = 0; x < width; x++) {
			const px = x + 0.5
			const py = y + 0.5
			const { dist, nx, ny } = roundedRectSDF(px, py, width, height, cornerRadius)
			const distFromEdge = -dist // positive inside the shape

			const idx = (y * width + x) * 4

			if (distFromEdge <= 0) {
				// outside shape: neutral
				imageData.data[idx] = 128
				imageData.data[idx + 1] = 128
				imageData.data[idx + 2] = 128
				imageData.data[idx + 3] = 255
			} else if (distFromEdge >= bezelWidth) {
				// interior (flat region) — our extra feature: subtle inner refraction
				// direction points INWARD (toward center) for lens-like magnification
				const cx = width / 2
				const cy = height / 2
				const dx = px - cx
				const dy = py - cy
				const centerLen = Math.max(1e-4, Math.sqrt(dx * dx + dy * dy))
				const centerDirX = dx / centerLen
				const centerDirY = dy / centerLen
				const innerBlend = Math.min(bezelWidth, 24)
				const innerRamp = smootherstep(0, innerBlend, distFromEdge - bezelWidth)
				const centerFalloff = Math.max(1, Math.min(width, height) / 2 - bezelWidth)
				const centerMask = 1 - smootherstep(0, centerFalloff, centerLen)

				const magnitude = innerRefraction * innerRamp * centerMask
				// negate direction: inward pull (matching bezel convention)
				const displaceX = -magnitude * centerDirX
				const displaceY = -magnitude * centerDirY

				imageData.data[idx] = Math.round(128 + displaceX * 127)
				imageData.data[idx + 1] = Math.round(128 + displaceY * 127)
				imageData.data[idx + 2] = 128
				imageData.data[idx + 3] = 255
			} else {
				const sampleIdx = Math.min(
					Math.floor((distFromEdge / bezelWidth) * samples),
					samples
				)
				const magnitude = normalized[sampleIdx]

				// displacement direction = INWARD (negated outward normal)
				// this matches the reference: -cos * distance (inward pull for convex glass)
				const displaceX = -magnitude * nx
				const displaceY = -magnitude * ny

				imageData.data[idx] = Math.round(128 + displaceX * 127)
				imageData.data[idx + 1] = Math.round(128 + displaceY * 127)
				imageData.data[idx + 2] = 128
				imageData.data[idx + 3] = 255
			}
		}
	}

	ctx.putImageData(imageData, 0, 0)

	return {
		imageDataUrl: canvas.toDataURL('image/png'),
		maxDisplacement,
		scale: maxDisplacement,
	}
}
