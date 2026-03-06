import { getCachedDisplacementMap, setCachedDisplacementMap } from './cache'
import { calculateDisplacement, type SurfaceFunction } from './physics'

export interface DisplacementMapConfig {
	width: number
	height: number
	bezelWidth: number
	thickness: number
	surfaceFn: SurfaceFunction
	cornerRadius?: number
	samples?: number
	mirrorDepth?: number
}

export interface DisplacementResult {
	imageDataUrl: string
	maxDisplacement: number
	scale: number
}

export function generateDisplacementMap(config: DisplacementMapConfig): DisplacementResult {
	const {
		width,
		height,
		bezelWidth,
		thickness,
		surfaceFn,
		samples = 127,
		mirrorDepth = 26,
	} = config
	const cornerRadius = config.cornerRadius ?? Math.min(width, height) / 2

	const surfaceName = surfaceFn.name || 'custom'
	const cacheKey = `${width}-${height}-${bezelWidth}-${thickness}-${cornerRadius}-${surfaceName}-${mirrorDepth}`
	const cached = getCachedDisplacementMap(cacheKey)
	if (cached) {
		return {
			imageDataUrl: cached.imageDataUrl,
			maxDisplacement: cached.maxDisplacement,
			scale: cached.scale,
		}
	}

	const profile: number[] = []
	for (let i = 0; i <= samples; i++) {
		const distance = (i / samples) * bezelWidth
		const displacement = calculateDisplacement(
			distance,
			bezelWidth,
			surfaceFn,
			thickness,
			1.0,
			1.55,
			mirrorDepth
		)
		profile.push(displacement)
	}

	let maxDisplacement = 0
	for (const d of profile) {
		maxDisplacement = Math.max(maxDisplacement, Math.abs(d))
	}
	if (maxDisplacement === 0) maxDisplacement = 1
	const normProfile = profile.map((d) => d / maxDisplacement)

	const canvas = document.createElement('canvas')
	canvas.width = width
	canvas.height = height
	const ctx = canvas.getContext('2d')!
	const imageData = ctx.createImageData(width, height)

	const halfW = width / 2
	const halfH = height / 2
	const bx = halfW - cornerRadius
	const by = halfH - cornerRadius

	let idx = 0
	for (let y = 0; y < height; y++) {
		const py = y + 0.5
		const ay = Math.abs(py - halfH)
		const dy = Math.max(ay - by, 0)
		const isTop = py < halfH

		for (let x = 0; x < width; x++) {
			const px = x + 0.5
			const ax = Math.abs(px - halfW)
			const dx = Math.max(ax - bx, 0)
			const isLeft = px < halfW

			let dist: number
			let nx: number
			let ny: number

			if (dx > 0 && dy > 0) {
				const len = Math.sqrt(dx * dx + dy * dy)
				dist = len - cornerRadius
				nx = dx / len
				ny = dy / len
			} else if (ax - bx > ay - by) {
				dist = ax - bx - cornerRadius
				nx = 1
				ny = 0
			} else {
				dist = ay - by - cornerRadius
				nx = 0
				ny = 1
			}

			if (isLeft) nx = -nx
			if (isTop) ny = -ny

			const distFromEdge = -dist
			if (distFromEdge <= 0 || distFromEdge >= bezelWidth) {
				imageData.data[idx++] = 128
				imageData.data[idx++] = 128
				imageData.data[idx++] = 128
				imageData.data[idx++] = 255
				continue
			}

			const si = Math.min(Math.floor((distFromEdge / bezelWidth) * samples), samples)
			const magnitude = normProfile[si]
			const displaceX = -magnitude * nx
			const displaceY = -magnitude * ny

			imageData.data[idx++] = Math.round(Math.max(0, Math.min(255, 128 + displaceX * 127)))
			imageData.data[idx++] = Math.round(Math.max(0, Math.min(255, 128 + displaceY * 127)))
			imageData.data[idx++] = 128
			imageData.data[idx++] = 255
		}
	}

	ctx.putImageData(imageData, 0, 0)

	const result = {
		imageDataUrl: canvas.toDataURL('image/png'),
		maxDisplacement,
		scale: maxDisplacement,
	}

	setCachedDisplacementMap(cacheKey, result)
	return result
}
